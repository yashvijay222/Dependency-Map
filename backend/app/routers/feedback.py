from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.deps import get_supabase_admin, parse_uuid, verify_user_or_api_key
from app.services.feedback_engine import maybe_update_org_weights, record_feedback
from app.supabase_utils import execute_with_schema_check

router = APIRouter(prefix="/v1/orgs", tags=["feedback"])


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


class FeedbackBody(BaseModel):
    analysis_id: str | None = None
    comment_node_id: str
    comment_type: str
    action: str


@router.post("/{org_id}/feedback")
def submit_feedback(
    org_id: str,
    body: FeedbackBody,
    actor: dict[str, Any] = Depends(verify_user_or_api_key),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    oid = parse_uuid(org_id)
    _assert_org_access(actor, str(oid), supabase)
    record_feedback(
        str(oid),
        body.analysis_id,
        body.comment_node_id,
        body.comment_type,
        body.action,
    )
    stats = maybe_update_org_weights(str(oid))
    return {"status": "ok", "training": stats}
