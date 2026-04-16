from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_supabase_admin, parse_uuid, verify_user_or_api_key
from app.supabase_utils import execute_with_schema_check

router = APIRouter(prefix="/v1/orgs", tags=["organizations"])


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
