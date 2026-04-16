from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.deps import get_supabase_admin, parse_uuid, verify_user_or_api_key
from app.supabase_utils import execute_with_schema_check
from app.worker.cross_repo_tasks import build_repo_ast_snapshot

router = APIRouter(prefix="/v1/repos", tags=["ast"])


def _assert_repo_org_access(actor: dict[str, Any], repo_org_id: str, supabase: Any) -> None:
    if actor.get("auth") == "api_key":
        if actor.get("org_id") != repo_org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key scope mismatch",
            )
        return
    uid = str(actor["sub"])
    membership = (
        supabase.table("organization_members")
        .select("role")
        .eq("org_id", repo_org_id)
        .eq("user_id", uid)
        .limit(1)
    )
    membership = execute_with_schema_check(membership)
    if not membership.data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an org member")


def _load_repo(repo_id: str, supabase: Any) -> dict[str, Any]:
    res = (
        supabase.table("repositories")
        .select("id, org_id, default_branch")
        .eq("id", repo_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return res.data[0]


class BuildAstBody(BaseModel):
    branch: str | None = None
    sha: str | None = None


@router.get("/{repo_id}/ast")
def get_latest_ast_snapshot(
    repo_id: str,
    branch: str | None = None,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    rid = str(parse_uuid(repo_id))
    repo = _load_repo(rid, supabase)
    _assert_repo_org_access(actor, str(repo["org_id"]), supabase)

    query = (
        supabase.table("ast_graph_snapshots")
        .select("*")
        .eq("repo_id", rid)
        .order("created_at", desc=True)
        .limit(1)
    )
    if branch:
        query = query.eq("branch", branch)

    res = query.execute()
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No AST snapshot found")
    return {"snapshot": res.data[0]}


@router.post("/{repo_id}/ast/build")
def build_ast_snapshot(
    repo_id: str,
    body: BuildAstBody,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    rid = str(parse_uuid(repo_id))
    repo = _load_repo(rid, supabase)
    _assert_repo_org_access(actor, str(repo["org_id"]), supabase)
    snapshot = build_repo_ast_snapshot(rid, branch=body.branch or None, sha=body.sha or None)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not build AST snapshot. Check GitHub App and Supabase configuration.",
        )
    return {"snapshot": snapshot}
