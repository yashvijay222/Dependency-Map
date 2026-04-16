from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.deps import get_supabase_admin, parse_uuid, verify_user_or_api_key
from app.limiter import limiter
from app.supabase_utils import execute_with_schema_check

router = APIRouter(prefix="/v1/orgs", tags=["cross-repo"])


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


class GraphBuildBody(BaseModel):
    branch: str | None = None


@router.post("/{org_id}/graph/build", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("30/minute")
def trigger_org_graph_build(
    request: Request,
    org_id: str,
    body: GraphBuildBody,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    oid = parse_uuid(org_id)
    _assert_org_access(actor, str(oid), supabase)
    try:
        from app.celery_app import build_org_graph_task

        async_result = build_org_graph_task.delay(str(oid), body.branch)
        return {"task_id": async_result.id, "status": "queued"}
    except Exception:
        from app.worker.cross_repo_tasks import build_org_graph

        build_org_graph(str(oid), body.branch)
        return {"task_id": None, "status": "completed_inline"}


@router.get("/{org_id}/graph")
def get_org_graph(
    org_id: str,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    oid = parse_uuid(org_id)
    _assert_org_access(actor, str(oid), supabase)
    res = supabase.table("cross_repo_edges").select("*").eq("org_id", str(oid)).execute()
    return {"edges": res.data or []}


@router.get("/{org_id}/graph/repos/{repo_id}/consumers")
def list_consumers(
    org_id: str,
    repo_id: str,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    oid = parse_uuid(org_id)
    rid = parse_uuid(repo_id)
    _assert_org_access(actor, str(oid), supabase)
    res = (
        supabase.table("cross_repo_edges")
        .select("*")
        .eq("org_id", str(oid))
        .eq("target_repo_id", str(rid))
        .execute()
    )
    return {"edges": res.data or []}


@router.get("/{org_id}/graph/repos/{repo_id}/dependencies")
def list_dependencies(
    org_id: str,
    repo_id: str,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    oid = parse_uuid(org_id)
    rid = parse_uuid(repo_id)
    _assert_org_access(actor, str(oid), supabase)
    res = (
        supabase.table("cross_repo_edges")
        .select("*")
        .eq("org_id", str(oid))
        .eq("source_repo_id", str(rid))
        .execute()
    )
    return {"edges": res.data or []}
