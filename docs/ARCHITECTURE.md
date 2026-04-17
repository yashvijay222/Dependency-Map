# Dependency Map Architecture

This document explains how the application is structured, how requests move through the system, and how the major services collaborate.

## Purpose

Dependency Map is a monorepo application that helps teams understand:

- what code changed in a repository
- what files and modules are impacted by those changes
- how a branch differs from another branch
- how one repository affects other repositories in the same organization
- how user feedback and optional ML layers can refine scoring over time

The repository is split into three main surfaces:

- `frontend/`: Next.js application for authentication and dashboards
- `backend/`: FastAPI service, orchestration logic, and worker code
- `supabase/`: SQL migrations for auth-linked data, RLS, analytics, and artifacts

## High-Level Topology

```text
Browser
  -> Next.js frontend
     -> Supabase Auth
     -> FastAPI backend
        -> Supabase PostgREST / database
        -> GitHub APIs
        -> Redis / Celery workers
        -> Optional ML and embedding services
```

## Major Components

### Frontend

The frontend is a Next.js app that:

- handles user-facing routes
- reads the authenticated Supabase user session
- calls the FastAPI API for protected data
- renders dashboard, organization, and repository views

The dashboard entry point is [frontend/app/(dashboard)/dashboard/page.tsx](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/frontend/app/(dashboard)/dashboard/page.tsx). It fetches the signed-in user from Supabase and then calls `/v1/dashboard` through the backend.

### Backend API

The FastAPI app is assembled in [backend/app/main.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/main.py). It configures:

- app startup and lifespan
- CORS
- rate limiting
- router registration
- the `GET /v1/dashboard` endpoint

Core API route groups:

- `health`: health check endpoint
- `webhooks`: GitHub webhook entrypoint
- `analyses`: create and retrieve PR/change analyses
- `branches`: branch snapshot and drift endpoints
- `cross_repo`: organization graph build and query endpoints
- `feedback`: feedback ingestion for scoring refinement
- `orgs`: repository listing within an organization
- `api_keys`: service-style org-scoped API key management

### Supabase

Supabase provides two different roles in this system:

- authentication and JWT issuance
- Postgres storage exposed through PostgREST

The schema is defined by the SQL files under `supabase/migrations/`. These create:

- identity-adjacent data like `profiles`
- organization data like `organizations` and `organization_members`
- repository metadata like `repositories` and `github_installations`
- analysis artifacts like `pr_analyses`, `dependency_snapshots`, `dependency_edges`, `risk_hotspots`
- cross-repo structures like `repo_packages`, `cross_repo_edges`, `cross_repo_edges_staging`
- ML and feedback artifacts like `review_feedback`, `model_artifacts`, `ast_graph_snapshots`, `node_embeddings`

If these migrations are not applied to the target Supabase project, the app can start but protected endpoints will fail when they first query expected tables.

### GitHub Integration

GitHub is used for:

- webhook-triggered PR and push events
- comparing commits
- fetching CODEOWNERS
- resolving GitHub App installation tokens
- downloading tarballs for repository snapshots and analyses

The webhook handler lives in [backend/app/routers/webhooks.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/routers/webhooks.py).

### Background Execution

The app supports two execution modes:

- inline or FastAPI `BackgroundTasks` for lightweight/local operation
- Celery workers backed by Redis for real asynchronous processing

Celery configuration is in [backend/app/celery_app.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/celery_app.py).

Queues and scheduled tasks include:

- analysis execution
- branch snapshots
- org graph rebuilds
- branch drift checks
- deleted branch cleanup
- nightly ML training
- backfill jobs for persisted schema versions

### CPG bridge, analysis planner, and Celery

PR analysis builds a **task graph** in [backend/app/services/analysis_planner.py](backend/app/services/analysis_planner.py) and executes it in [backend/app/worker/tasks.py](backend/app/worker/tasks.py) (`run_analysis_job` / `_execute_task_graph`). The same graph runs **inline** (FastAPI `BackgroundTasks` or synchronous fallback) when `USE_CELERY` is false, or is **enqueued on Celery** when `USE_CELERY` is true.

**Global kill-switch:** `enable_cpg_bridge` in [backend/app/config.py](backend/app/config.py) (environment-driven). When false, the planner behaves as if `cpg_contract_analysis` is `off` and hosted workers will not run `cpg_mining`.

**Server feature flags** (same module): `feature_git_workspace_clone`, `feature_github_check_runs`, `feature_github_pr_comments`, `feature_in_app_finding_labels`, `feature_onboarding_wizard`. Defaults favor safe rollout (`feature_github_*` off until GitHub integrations are configured).

**Pipeline logging:** JSON-shaped events from [backend/app/observability.py](backend/app/observability.py) under logger `dm.pipeline`; counters exposed at `GET /health/metrics`.

**Org-level settings:** `organizations.settings` JSON (see cross-repo migration) supports:

- `cpg_contract_analysis`: `off` | `stitch_gate` (default) | `always` | `on_migration_or_routes`
  - `stitch_gate`: CPG tasks only when both frontend and backend router globs match the diff (legacy behavior).
  - `always`: schedule CPG mining for every analysis (path miner does not depend on the stitch extractor unless the stitch task is also present).
  - `on_migration_or_routes`: schedule CPG when the stitch gate matches **or** migration / route heuristics fire.
- `cpg_use_git_workspace`: boolean — prefer clone-based git diff for CPG when GitHub token + SHAs are available (default follows server `feature_git_workspace_clone`).
- `finding_suppressions`: list of `{ "invariant_id", "path_glob", "expires_at"?(ISO8601) }` — evaluated before findings persist.
- `max_consumer_repos`, `reasoner_max_packs_per_run`, `reasoner_monthly_token_budget` — cost and cross-repo caps (see `PATCH /v1/orgs/{id}/settings`).
- `frontend_stitch_globs`: extra glob strings merged into the analysis planner’s frontend coverage list.
- Other existing keys (`async_checks_enabled`, etc.) are unchanged.

**Optional tasks:** Nodes marked `optional` in the plan that raise during execution are stored as `skipped` (not `failed`) so downstream tasks can still complete; see `partial_outputs` and `summary_json.cpg_status` on `pr_analyses`.

**Celery-only helper:** `dm.run_cpg_contract_score` in [backend/app/celery_app.py](backend/app/celery_app.py) runs the offline scorer on a worker-local checkout path. It is separate from the main PR task graph but uses the same [backend/cpg_builder/scorer.py](backend/cpg_builder/scorer.py) entrypoint.

**Tarball checkouts:** GitHub archives usually lack `.git`. The worker passes `synthetic_changed_files` (from the GitHub compare file list) into `score_repository` so the path miner still receives a diff-shaped payload without a local git ref.

## Authentication and Authorization

Authentication is implemented in [backend/app/deps.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/deps.py).

The backend supports two caller types:

- Supabase-authenticated users with bearer JWTs
- org-scoped raw API keys prefixed with `dm_`

Authorization generally follows this pattern:

1. verify the token or API key
2. determine the caller identity or org scope
3. query `organization_members` when the caller is a user
4. reject access if the caller is not a member of the target organization

The backend uses the Supabase service role key for server-side queries. Row-level security still matters for product design and direct client access patterns, but the server’s own data access is performed through trusted service credentials.

## Request Lifecycle

### Example: Dashboard

```text
Browser -> Next.js dashboard page
        -> Supabase session lookup
        -> FastAPI GET /v1/dashboard
        -> JWT verification
        -> query organization_members
        -> query organizations
        -> JSON response
        -> UI render
```

The dashboard endpoint is intentionally simple. It proves that:

- auth is working
- the backend can verify the JWT
- the API can reach Supabase
- the base organization schema exists

### Example: Trigger analysis

```text
Client -> POST /v1/repos/{repo_id}/analyze
       -> actor validation
       -> org membership check
       -> insert pr_analyses row
       -> enqueue or run analysis worker
       -> return analysis_id
```

The heavy lifting happens later in worker code, not inside the request handler itself.

## Data Model by Responsibility

### Identity and tenancy

- `profiles`
- `organizations`
- `organization_members`

These establish the organization boundary used by almost all protected endpoints.

### Repository registration

- `github_installations`
- `repositories`

These connect an organization to a GitHub App installation and the repositories the app should analyze.

### Analysis artifacts

- `pr_analyses`
- `dependency_snapshots`
- `dependency_edges`
- `branch_drift_signals`
- `risk_hotspots`

These tables store the outputs of analysis and monitoring jobs.

### Cross-repo intelligence

- `repo_packages`
- `cross_repo_edges`
- `cross_repo_edges_staging`

These describe relationships between repositories at the package/import layer.

### Feedback and ML

- `review_feedback`
- `model_artifacts`
- `ast_graph_snapshots`
- `node_embeddings`

These enable refinement beyond simple graph traversal.

## Service Layer Overview

Important backend services include:

- `graph_builder.py`: parses TS/JS modules and produces file/package dependency graphs
- `blast_radius.py`: computes reverse dependency impact and cross-repo impact
- `intelligent_scorer.py`: chooses between heuristic fallback and optional GNN-assisted inference
- `feedback_engine.py`: aggregates review feedback into org-specific scoring weights
- `github_client.py`: GitHub API and tarball operations
- `package_resolver.py`: resolves published/workspace package relationships across repos
- `branch_monitor.py`: computes drift signals between snapshots

## Fallback Strategy

A recurring design pattern in this app is graceful degradation:

- if Celery is unavailable, work may run inline
- if GitHub App configuration is missing, the system can emit stub summaries
- if GNN models are unavailable, the scorer falls back to uniform graph traversal
- if some optional tables are absent, routes should prefer actionable errors over opaque stack traces

This is important for local development, partial deployments, and incremental rollout of ML-heavy features.

## Scheduled Maintenance and Refresh

With Celery Beat enabled, the app can periodically:

- enqueue snapshots for all orgs
- compute branch drift checks on a schedule
- backfill schema version fields for historical analyses
- train org-specific GNN models nightly

This turns the app from a purely on-demand API into a continuously refreshed dependency intelligence system.

## Known Operational Dependencies

The system behaves best when these are configured together:

- Supabase migrations applied in full
- GitHub App credentials configured
- Redis reachable
- Celery worker and Beat running when async execution is desired
- optional OpenAI and ML dependencies present when embeddings or advanced inference are used

Without those pieces, the app can still boot and serve some routes, but the deeper pipeline becomes partial or stubbed.

## Recommended Reading Order

If you are new to the codebase, this order works well:

1. [README.md](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/README.md)
2. [docs/PIPELINE.md](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/docs/PIPELINE.md)
3. [backend/app/main.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/main.py)
4. [backend/app/routers/webhooks.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/routers/webhooks.py)
5. [backend/app/worker/tasks.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/worker/tasks.py)
6. [backend/app/worker/cross_repo_tasks.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/worker/cross_repo_tasks.py)
