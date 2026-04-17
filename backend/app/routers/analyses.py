from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.services.analysis_runs import signed_graph_artifact_metadata
from app.deps import get_supabase_admin, parse_uuid, verify_user_or_api_key
from app.limiter import limiter
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
    return {
        "analysis_id": str(aid),
        "verified": [row for row in rows if row.get("status") == "verified"],
        "withheld": [row for row in rows if row.get("status") == "withheld"],
        "all": rows,
    }


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
