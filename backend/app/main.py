from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from supabase import Client

from app.config import settings
from app.deps import get_supabase_admin, verify_supabase_jwt
from app.limiter import limiter
from app.routers import (
    analyses,
    api_keys,
    ast,
    branches,
    cross_repo,
    feedback,
    health,
    orgs,
    repo_lookup,
    webhooks,
)
from app.supabase_utils import execute_with_schema_check


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(
    title="Dependency Map API",
    version="0.1.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(webhooks.router)
app.include_router(repo_lookup.router)
app.include_router(analyses.router)
app.include_router(ast.router)
app.include_router(branches.router)
app.include_router(cross_repo.router)
app.include_router(feedback.router)
app.include_router(orgs.router)
app.include_router(api_keys.router)


@app.get("/v1/dashboard")
def dashboard(
    user: dict = Depends(verify_supabase_jwt),
    sb: Client = Depends(get_supabase_admin),
) -> dict:
    uid = str(user["sub"])
    memberships = (
        sb.table("organization_members")
        .select("org_id, role")
        .eq("user_id", uid)
    )
    memberships = execute_with_schema_check(memberships)
    rows = memberships.data or []
    org_ids = [r["org_id"] for r in rows]
    organizations: list[dict] = []
    if org_ids:
        ores = execute_with_schema_check(
            sb.table("organizations").select("id, name, slug").in_("id", org_ids),
        )
        organizations = ores.data or []
    return {
        "user_id": uid,
        "email": user.get("email"),
        "organizations": organizations,
        "memberships": rows,
    }
