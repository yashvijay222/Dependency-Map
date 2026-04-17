from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import get_supabase_admin, parse_uuid, verify_user_or_api_key
from app.supabase_utils import execute_with_schema_check

router = APIRouter(prefix="/v1/repos", tags=["repositories"])


def _actor_can_access_repo(actor: dict[str, Any], repo: dict[str, Any], supabase: Any) -> bool:
    repo_org_id = str(repo["org_id"])
    if actor.get("auth") == "api_key":
        return actor.get("org_id") == repo_org_id
    uid = str(actor["sub"])
    membership = (
        supabase.table("organization_members")
        .select("role")
        .eq("org_id", repo_org_id)
        .eq("user_id", uid)
        .limit(1)
    )
    membership = execute_with_schema_check(membership)
    return bool(membership.data)


@router.get("/lookup")
def lookup_repository(
    name: str = Query(..., min_length=1),
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    search_term = name.strip()
    repos = (
        supabase.table("repositories")
        .select("id, org_id, full_name, default_branch")
        .ilike("full_name", f"%{search_term}")
        .limit(20)
        .execute()
    )
    for repo in repos.data or []:
        if _actor_can_access_repo(actor, repo, supabase):
            return {"repository": repo}
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No accessible repository matched that name.",
    )


@router.get("/{repo_id}")
def get_repository(
    repo_id: str,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    rid = parse_uuid(repo_id)
    res = (
        supabase.table("repositories")
        .select("id, org_id, full_name, default_branch, github_repo_id")
        .eq("id", str(rid))
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    repo = res.data[0]
    if not _actor_can_access_repo(actor, repo, supabase):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return {"repository": repo}
