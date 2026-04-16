import secrets
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.deps import get_supabase_admin, hash_api_key, parse_uuid, verify_supabase_jwt
from app.supabase_utils import execute_with_schema_check

router = APIRouter(prefix="/v1/orgs", tags=["api-keys"])


class CreateApiKeyBody(BaseModel):
    name: str


def _require_org_member(supabase: Any, org_uuid: UUID, user_id: str) -> None:
    m = (
        supabase.table("organization_members")
        .select("role")
        .eq("org_id", str(org_uuid))
        .eq("user_id", user_id)
        .limit(1)
    )
    m = execute_with_schema_check(m)
    if not m.data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an org member")


@router.post("/{org_id}/api-keys", status_code=status.HTTP_201_CREATED)
def create_api_key(
    org_id: str,
    body: CreateApiKeyBody,
    user: dict[str, Any] = Depends(verify_supabase_jwt),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    oid = parse_uuid(org_id)
    user_id = str(user["sub"])
    _require_org_member(supabase, oid, user_id)
    raw = "dm_" + secrets.token_urlsafe(24)
    prefix = raw[:16]
    digest = hash_api_key(raw)
    row = {
        "org_id": str(oid),
        "name": body.name,
        "key_prefix": prefix,
        "key_hash": digest,
    }
    res = supabase.table("api_keys").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create API key")
    created = res.data[0]
    return {
        "id": created["id"],
        "name": created["name"],
        "key_prefix": prefix,
        "key": raw,
        "message": "Store this key securely; it will not be shown again.",
    }


@router.get("/{org_id}/api-keys")
def list_api_keys(
    org_id: str,
    user: dict[str, Any] = Depends(verify_supabase_jwt),
    supabase=Depends(get_supabase_admin),
) -> dict[str, Any]:
    oid = parse_uuid(org_id)
    user_id = str(user["sub"])
    _require_org_member(supabase, oid, user_id)
    res = (
        supabase.table("api_keys")
        .select("id, name, key_prefix, created_at, last_used_at")
        .eq("org_id", str(oid))
        .execute()
    )
    return {"keys": res.data or []}


@router.delete("/{org_id}/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_api_key(
    org_id: str,
    key_id: str,
    user: dict[str, Any] = Depends(verify_supabase_jwt),
    supabase=Depends(get_supabase_admin),
) -> Response:
    oid = parse_uuid(org_id)
    kid = parse_uuid(key_id)
    user_id = str(user["sub"])
    _require_org_member(supabase, oid, user_id)
    supabase.table("api_keys").delete().eq("id", str(kid)).eq("org_id", str(oid)).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
