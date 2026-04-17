from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.deps import get_supabase_admin, parse_uuid, verify_user_or_api_key
from app.limiter import limiter
from app.services.analysis_runs import signed_graph_artifact_metadata
from app.services.finding_presenter import present_finding
from app.supabase_utils import execute_with_schema_check
from app.worker.tasks import schedule_analysis_job

router = APIRouter(prefix="/v1/repos", tags=["analyses"])


class AnalyzeBody(BaseModel):
    pr_number: int | None = None
    base_sha: str | None = None
    head_sha: str | None = None
    cross_repo: bool = False


class RerunBody(BaseModel):
    cross_repo: bool | None = None
    base_sha: str | None = None
    head_sha: str | None = None


class FindingDismissBody(BaseModel):
    status: str = "dismissed"
    reason: str | None = None


class FindingReviewBody(BaseModel):
    label: str
    notes: str | None = None


def _assert_repo_org_access(
    actor: dict[str, Any],
    repo_org_id: str,
    supabase: Any,
) -> None:
    if actor.get("auth") == "api_key":
        if actor.get("org_id") != repo_org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key scope mismatch",
            )
        return
    uid = str(actor["sub"])
    m = (
        supabase.table("organization_members")
        .select("role")
        .eq("org_id", repo_org_id)
        .eq("user_id", uid)
        .limit(1)
    )
    m = execute_with_schema_check(m)
    if not m.data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an org member")


@router.post("/{repo_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("60/minute")
def trigger_analyze(
    request: Request,
    repo_id: str,
    body: AnalyzeBody,
    background: BackgroundTasks,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    rid = parse_uuid(repo_id)
    if body.pr_number is None and (not body.base_sha or not body.head_sha):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide pr_number or both base_sha and head_sha",
        )
    rres = (
        supabase.table("repositories")
        .select("org_id")
        .eq("id", str(rid))
        .limit(1)
        .execute()
    )
    if not rres.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    repo_org = str(rres.data[0]["org_id"])
    _assert_repo_org_access(actor, repo_org, supabase)
    row = {
        "repo_id": str(rid),
        "pr_number": body.pr_number,
        "base_sha": body.base_sha,
        "head_sha": body.head_sha,
        "cross_repo": body.cross_repo,
        "status": "pending",
        "summary_json": {},
    }
    res = supabase.table("pr_analyses").insert(row).execute()
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create analysis",
        )
    analysis_id = res.data[0]["id"]
    schedule_analysis_job(str(analysis_id), background)
    return {"analysis_id": analysis_id, "status": "pending"}


@router.get("/{repo_id}/analyses/latest")
def get_latest_analysis(
    repo_id: str,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    rid = parse_uuid(repo_id)
    rres = (
        supabase.table("repositories")
        .select("org_id")
        .eq("id", str(rid))
        .limit(1)
        .execute()
    )
    if not rres.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    _assert_repo_org_access(actor, str(rres.data[0]["org_id"]), supabase)
    res = (
        supabase.table("pr_analyses")
        .select("*")
        .eq("repo_id", str(rid))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No analyses")
    return res.data[0]


@router.get("/{repo_id}/analyses/{analysis_id}")
def get_analysis(
    repo_id: str,
    analysis_id: str,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    rid = parse_uuid(repo_id)
    aid = parse_uuid(analysis_id)
    rres = (
        supabase.table("repositories")
        .select("org_id")
        .eq("id", str(rid))
        .limit(1)
        .execute()
    )
    if not rres.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    _assert_repo_org_access(actor, str(rres.data[0]["org_id"]), supabase)
    res = (
        supabase.table("pr_analyses")
        .select("*")
        .eq("id", str(aid))
        .eq("repo_id", str(rid))
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return res.data[0]


@router.get("/{repo_id}/analyses/{analysis_id}/plan")
def get_analysis_plan(
    repo_id: str,
    analysis_id: str,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    rid = parse_uuid(repo_id)
    aid = parse_uuid(analysis_id)
    _assert_analysis_access(supabase, actor, str(rid), str(aid))
    res = (
        supabase.table("analysis_plans")
        .select("*")
        .eq("run_id", str(aid))
        .eq("repo_id", str(rid))
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return res.data[0]


@router.get("/{repo_id}/analyses/{analysis_id}/findings")
def get_analysis_findings(
    repo_id: str,
    analysis_id: str,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    rid = parse_uuid(repo_id)
    aid = parse_uuid(analysis_id)
    _assert_analysis_access(supabase, actor, str(rid), str(aid))
    res = (
        supabase.table("findings")
        .select("*")
        .eq("analysis_id", str(aid))
        .eq("repo_id", str(rid))
        .order("created_at", desc=False)
        .execute()
    )
    rows = res.data or []
    presented = [present_finding(dict(row)) for row in rows]
    return {
        "analysis_id": str(aid),
        "verified": [row for row in rows if row.get("status") == "verified"],
        "withheld": [row for row in rows if row.get("status") == "withheld"],
        "all": rows,
        "presented": presented,
    }


@router.get("/{repo_id}/findings/{finding_id}")
def get_finding(
    repo_id: str,
    finding_id: str,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    rid = parse_uuid(repo_id)
    fid = parse_uuid(finding_id)
    rres = (
        supabase.table("repositories")
        .select("org_id")
        .eq("id", str(rid))
        .limit(1)
        .execute()
    )
    if not rres.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    _assert_repo_org_access(actor, str(rres.data[0]["org_id"]), supabase)
    fres = (
        supabase.table("findings")
        .select("*")
        .eq("id", str(fid))
        .eq("repo_id", str(rid))
        .limit(1)
        .execute()
    )
    if not fres.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    row = fres.data[0]
    return {"finding": row, "presented": present_finding(dict(row))}


@router.get("/{repo_id}/pulls/{pr_number}/analyses")
def list_analyses_for_pr(
    repo_id: str,
    pr_number: int,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    rid = parse_uuid(repo_id)
    rres = (
        supabase.table("repositories")
        .select("org_id")
        .eq("id", str(rid))
        .limit(1)
        .execute()
    )
    if not rres.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    _assert_repo_org_access(actor, str(rres.data[0]["org_id"]), supabase)
    res = (
        supabase.table("pr_analyses")
        .select("*")
        .eq("repo_id", str(rid))
        .eq("pr_number", pr_number)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return {"repo_id": str(rid), "pr_number": pr_number, "analyses": res.data or []}


@router.patch("/{repo_id}/findings/{finding_id}")
def dismiss_finding(
    repo_id: str,
    finding_id: str,
    body: FindingDismissBody,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    if actor.get("auth") == "api_key":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dismiss findings with a user session",
        )
    rid = parse_uuid(repo_id)
    fid = parse_uuid(finding_id)
    rres = (
        supabase.table("repositories")
        .select("org_id")
        .eq("id", str(rid))
        .limit(1)
        .execute()
    )
    if not rres.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    org_id = str(rres.data[0]["org_id"])
    _assert_repo_org_access(actor, org_id, supabase)
    uid = str(actor["sub"])
    role_res = (
        supabase.table("organization_members")
        .select("role")
        .eq("org_id", org_id)
        .eq("user_id", uid)
        .limit(1)
        .execute()
    )
    role = str((role_res.data or [{}])[0].get("role") or "")
    if role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only org owners or admins can dismiss findings",
        )
    if body.status not in ("dismissed",):
        raise HTTPException(status_code=400, detail="Only dismissed supported")
    fres = (
        supabase.table("findings")
        .select("id, repo_id, summary_json")
        .eq("id", str(fid))
        .eq("repo_id", str(rid))
        .limit(1)
        .execute()
    )
    if not fres.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    prev_summary = dict(fres.data[0].get("summary_json") or {})
    merged = {
        **prev_summary,
        "dismissed": True,
        "dismissed_reason": body.reason,
        "dismissed_by_user_id": uid,
        "dismissed_at": datetime.now(UTC).isoformat(),
    }
    supabase.table("findings").update(
        {
            "status": "dismissed",
            "withhold_reason": body.reason or "dismissed_by_user",
            "summary_json": merged,
        },
    ).eq("id", str(fid)).execute()
    return {"finding_id": str(fid), "status": "dismissed"}


@router.post("/{repo_id}/findings/{finding_id}/reviews")
def review_finding(
    repo_id: str,
    finding_id: str,
    body: FindingReviewBody,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    if actor.get("auth") == "api_key":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Use user session for reviews",
        )
    if body.label not in ("helpful", "wrong", "noisy"):
        raise HTTPException(status_code=400, detail="Invalid label")
    rid = parse_uuid(repo_id)
    fid = parse_uuid(finding_id)
    uid = str(actor["sub"])
    rres = (
        supabase.table("repositories")
        .select("org_id")
        .eq("id", str(rid))
        .limit(1)
        .execute()
    )
    if not rres.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    _assert_repo_org_access(actor, str(rres.data[0]["org_id"]), supabase)
    fres = (
        supabase.table("findings")
        .select("id")
        .eq("id", str(fid))
        .eq("repo_id", str(rid))
        .limit(1)
        .execute()
    )
    if not fres.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    ins = (
        supabase.table("finding_reviews")
        .upsert(
            {
                "finding_id": str(fid),
                "user_id": uid,
                "label": body.label,
                "notes": body.notes,
            },
            on_conflict="finding_id,user_id",
        )
        .execute()
    )
    return {"ok": True, "data": ins.data or []}


@router.get("/{repo_id}/analyses/{analysis_id}/audit")
def get_analysis_audit(
    repo_id: str,
    analysis_id: str,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    rid = parse_uuid(repo_id)
    aid = parse_uuid(analysis_id)
    _assert_analysis_access(supabase, actor, str(rid), str(aid))
    events = (
        supabase.table("analysis_run_events")
        .select("*")
        .eq("run_id", str(aid))
        .eq("repo_id", str(rid))
        .order("created_at", desc=False)
        .execute()
    )
    audits = (
        supabase.table("verifier_audits")
        .select("*")
        .eq("analysis_id", str(aid))
        .eq("repo_id", str(rid))
        .order("created_at", desc=False)
        .execute()
    )
    return {
        "analysis_id": str(aid),
        "events": events.data or [],
        "verifier_audits": audits.data or [],
    }


@router.get("/{repo_id}/analyses/{analysis_id}/graph")
def get_analysis_graph(
    repo_id: str,
    analysis_id: str,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    rid = parse_uuid(repo_id)
    aid = parse_uuid(analysis_id)
    _assert_analysis_access(supabase, actor, str(rid), str(aid))
    res = (
        supabase.table("graph_artifacts")
        .select("*")
        .eq("analysis_id", str(aid))
        .eq("repo_id", str(rid))
        .order("created_at", desc=False)
        .execute()
    )
    rows = [signed_graph_artifact_metadata(row, supabase) for row in (res.data or [])]
    return {"analysis_id": str(aid), "artifacts": rows}


@router.post("/{repo_id}/analyses/{analysis_id}/rerun", status_code=status.HTTP_202_ACCEPTED)
def rerun_analysis(
    request: Request,
    repo_id: str,
    analysis_id: str,
    body: RerunBody,
    background: BackgroundTasks,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    rid = parse_uuid(repo_id)
    aid = parse_uuid(analysis_id)
    existing = _assert_analysis_access(supabase, actor, str(rid), str(aid))
    row = {
        "repo_id": str(rid),
        "pr_number": existing.get("pr_number"),
        "base_sha": body.base_sha or existing.get("base_sha"),
        "head_sha": body.head_sha or existing.get("head_sha"),
        "cross_repo": existing.get("cross_repo") if body.cross_repo is None else body.cross_repo,
        "status": "pending",
        "summary_json": {},
        "rerun_of_analysis_id": str(aid),
    }
    res = supabase.table("pr_analyses").insert(row).execute()
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create rerun",
        )
    new_id = str(res.data[0]["id"])
    schedule_analysis_job(new_id, background)
    return {"analysis_id": new_id, "status": "pending", "rerun_of_analysis_id": str(aid)}


def _assert_analysis_access(
    supabase: Any,
    actor: dict[str, Any],
    repo_id: str,
    analysis_id: str,
) -> dict[str, Any]:
    rres = (
        supabase.table("repositories")
        .select("org_id")
        .eq("id", repo_id)
        .limit(1)
        .execute()
    )
    if not rres.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    _assert_repo_org_access(actor, str(rres.data[0]["org_id"]), supabase)
    res = (
        supabase.table("pr_analyses")
        .select("*")
        .eq("id", analysis_id)
        .eq("repo_id", repo_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return res.data[0]
