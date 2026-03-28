from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWTError
from supabase import Client, create_client

from app.config import settings

security = HTTPBearer(auto_error=False)

# Supabase Auth user access tokens may be HS256 (legacy JWT secret) or asymmetric (JWKS).
_JWKS_CLIENTS: dict[str, PyJWKClient] = {}
_ALLOWED_ASYMMETRIC_ALGS = frozenset(
    {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "EdDSA"},
)


def _supabase_public_url() -> str:
    return settings.supabase_url.strip().rstrip("/")


def _jwks_client(jwks_uri: str) -> PyJWKClient:
    if jwks_uri not in _JWKS_CLIENTS:
        _JWKS_CLIENTS[jwks_uri] = PyJWKClient(jwks_uri)
    return _JWKS_CLIENTS[jwks_uri]


def get_supabase_admin() -> Client:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase is not configured",
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def verify_supabase_jwt(
    creds: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(security),
    ],
) -> dict:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = creds.credentials
    try:
        header = jwt.get_unverified_header(token)
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    alg = header.get("alg") or "HS256"

    try:
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="JWT verification is not configured",
                )
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        else:
            base = _supabase_public_url()
            if not base:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Supabase is not configured",
                )
            if alg not in _ALLOWED_ASYMMETRIC_ALGS:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                )
            jwks_uri = f"{base}/auth/v1/.well-known/jwks.json"
            signing_key = _jwks_client(jwks_uri).get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience="authenticated",
                issuer=f"{base}/auth/v1",
            )
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return {"sub": sub, "email": payload.get("email"), "payload": payload}


def parse_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID",
        ) from exc


async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        yield client
