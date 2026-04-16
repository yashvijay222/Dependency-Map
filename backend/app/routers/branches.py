from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.deps import get_supabase_admin, parse_uuid, verify_user_or_api_key
from app.limiter import limiter
from app.supabase_utils import execute_with_schema_check

router = APIRouter(prefix="/v1/repos", tags=["branches"])


def _assert_repo_org_access(actor: dict[str, Any], repo_org_id: str, supabase: Any) -> None:
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


class SnapshotBody(BaseModel):
    branch: str
    sha: str | None = None


class DriftBody(BaseModel):
    branch_a: str
    branch_b: str


@router.post("/{repo_id}/branches/snapshot", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("60/minute")
def trigger_branch_snapshot(
    request: Request,
    repo_id: str,
    body: SnapshotBody,
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
    org_id = str(rres.data[0]["org_id"])
    _assert_repo_org_access(actor, org_id, supabase)
    try:
        from app.celery_app import snapshot_repo_branch_task

        ar = snapshot_repo_branch_task.delay(str(rid), body.branch, body.sha)
        return {"task_id": ar.id, "status": "queued"}
    except Exception:
        from app.worker.cross_repo_tasks import snapshot_repo_branch

        snapshot_repo_branch(str(rid), body.branch, body.sha)
        return {"task_id": None, "status": "completed_inline"}


@router.post("/{repo_id}/branches/drift", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("60/minute")
def trigger_branch_drift(
    request: Request,
    repo_id: str,
    body: DriftBody,
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
    org_id = str(rres.data[0]["org_id"])
    _assert_repo_org_access(actor, org_id, supabase)
    try:
        from app.celery_app import compute_branch_drift_task

        ar = compute_branch_drift_task.delay(str(rid), body.branch_a, body.branch_b)
        return {"task_id": ar.id, "status": "queued"}
    except Exception:
        from app.worker.cross_repo_tasks import compute_branch_drift

        compute_branch_drift(str(rid), body.branch_a, body.branch_b)
        return {"task_id": None, "status": "completed_inline"}


@router.get("/{repo_id}/branches/drift")
def list_branch_drift(
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
        supabase.table("branch_drift_signals")
        .select("*")
        .eq("repo_id", str(rid))
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return {"signals": res.data or []}


@router.get("/{repo_id}/branches/{branch}/graph")
def get_branch_graph(
    repo_id: str,
    branch: str,
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
        supabase.table("dependency_snapshots")
        .select("*")
        .eq("repo_id", str(rid))
        .eq("branch", branch)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No snapshot for branch")
    return res.data[0]
