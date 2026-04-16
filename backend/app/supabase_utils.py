from typing import Any

from fastapi import HTTPException, status
from postgrest.exceptions import APIError


def execute_with_schema_check(request_builder: Any) -> Any:
    try:
        return request_builder.execute()
    except APIError as exc:
        payload = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {}
        code = payload.get("code")
        message = str(payload.get("message", ""))
        if code == "PGRST205":
            missing_table = "a required table"
            if "public.organization_members" in message:
                missing_table = "public.organization_members"
            elif "public.organizations" in message:
                missing_table = "public.organizations"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Supabase schema is not initialized. "
                    f"Missing {missing_table}. "
                    "Apply the migrations in supabase/migrations/ and refresh the PostgREST schema cache."
                ),
            ) from exc
        raise
