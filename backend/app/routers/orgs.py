from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.deps import get_supabase_admin, parse_uuid, verify_user_or_api_key
from app.supabase_utils import execute_with_schema_check

router = APIRouter(prefix="/v1/orgs", tags=["organizations"])

_ORG_SETTINGS_MERGE_KEYS = frozenset(
    {
        "max_consumer_repos",
        "reasoner_max_packs_per_run",
        "cpg_use_git_workspace",
        "finding_suppressions",
        "frontend_stitch_globs",
        "cpg_contract_analysis",
    },
)


class OrgSettingsPatchBody(BaseModel):
    settings: dict[str, Any]


def _assert_org_admin(actor: dict[str, Any], org_id: str, supabase: Any) -> None:
    if actor.get("auth") == "api_key":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Use a user session to change organization settings",
        )
    uid = str(actor["sub"])
    m = (
        supabase.table("organization_members")
        .select("role")
        .eq("org_id", org_id)
        .eq("user_id", uid)
        .limit(1)
    )
    m = execute_with_schema_check(m)
    role = str((m.data or [{}])[0].get("role") or "")
    if role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only org owners or admins can update settings",
        )


def _assert_org_access(actor: dict[str, Any], org_id: str, supabase: Any) -> None:
    oid = str(org_id)
    if actor.get("auth") == "api_key":
        if actor.get("org_id") != oid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key scope mismatch",
            )
        return
    uid = str(actor["sub"])
    m = (
        supabase.table("organization_members")
        .select("role")
        .eq("org_id", oid)
        .eq("user_id", uid)
        .limit(1)
    )
    m = execute_with_schema_check(m)
    if not m.data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an org member")


@router.get("/{org_id}/repositories")
def list_org_repositories(
    org_id: str,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    oid = parse_uuid(org_id)
    _assert_org_access(actor, str(oid), supabase)
    res = supabase.table("repositories").select("*").eq("org_id", str(oid)).execute()
    return {"repositories": res.data or []}


@router.get("/{org_id}/eval-summary")
def org_eval_summary(
    org_id: str,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    """Aggregate finding review labels for repositories in this org (Phase 5)."""
    oid = parse_uuid(org_id)
    _assert_org_access(actor, str(oid), supabase)
    repos = supabase.table("repositories").select("id").eq("org_id", str(oid)).execute()
    repo_ids = [str(r["id"]) for r in (repos.data or [])]
    if not repo_ids:
        return {"org_id": str(oid), "counts": {}, "total": 0}
    findings = (
        supabase.table("findings")
        .select("id")
        .in_("repo_id", repo_ids)
        .limit(5000)
        .execute()
    )
    fids = [str(f["id"]) for f in (findings.data or [])]
    if not fids:
        return {"org_id": str(oid), "counts": {}, "total": 0}
    reviews = (
        supabase.table("finding_reviews")
        .select("label")
        .in_("finding_id", fids)
        .execute()
    )
    counts: dict[str, int] = {}
    for row in reviews.data or []:
        lab = str(row.get("label") or "")
        counts[lab] = counts.get(lab, 0) + 1
    return {"org_id": str(oid), "counts": counts, "total": sum(counts.values())}


@router.patch("/{org_id}/settings")
def patch_org_settings(
    org_id: str,
    body: OrgSettingsPatchBody,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    oid = parse_uuid(org_id)
    oid_s = str(oid)
    _assert_org_access(actor, oid_s, supabase)
    _assert_org_admin(actor, oid_s, supabase)
    bad = set(body.settings.keys()) - _ORG_SETTINGS_MERGE_KEYS
    if bad:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported settings keys: {sorted(bad)}",
        )
    cur = (
        supabase.table("organizations")
        .select("settings")
        .eq("id", oid_s)
        .limit(1)
        .execute()
    )
    if not cur.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    row0 = cur.data[0]
    if not isinstance(row0, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid org row",
        )
    merged = dict(row0.get("settings") or {})
    merged.update(body.settings)
    supabase.table("organizations").update({"settings": merged}).eq("id", oid_s).execute()
    return {"org_id": oid_s, "settings": merged}
