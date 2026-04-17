# Product Spec: Gated Analysis

## Goal

Dependency Map should run PR risk analysis as an analysis agent loop:

1. intake and scope
2. build a task graph plan
3. dispatch isolated subtasks
4. run deterministic verification
5. surface verified and withheld findings with audit history

This spec is the implementation contract for Phase 1.

## Analysis Agent Loop

- The orchestrator owns run state and task-graph progression.
- Subtasks are treated as tool calls with explicit success or failure.
- A subtask timeout or exception is a task result error, not an undefined pipeline crash.
- Verified findings require deterministic verification.
- Withheld findings remain visible with reason and provenance.

## Persistence

### `pr_analyses`

- Summary row for one run.
- `status`: `pending`, `running`, `completed`, `failed`
- `outcome`: `completed_ok`, `completed_degraded`, `failed`
- `mode`: planner-selected analysis mode
- `plan_id`
- `task_graph_state`
- `verified_count`
- `withheld_count`
- `partial_outputs`
- `rerun_of_analysis_id`

### `analysis_plans`

- One row per run.
- Stores `task_graph_json`, `reason_json`, `analysis_mode`, `disabled_subtasks`.

### `analysis_run_events`

- Append-only audit log.
- Stores `run_id`, `task_id`, `event_type`, `attempt`, `error_code`, `metadata_json`, `created_at`.
- Never updated in place.

### `findings`

- Lifecycle states: `candidate`, `verified`, `withheld`, `dismissed`, `superseded`
- Carries `provenance` and normalized summary fields.

### `verifier_audits`

- One or more rows per finding.
- Stores checks run, passed, failed, and `graph_artifact_ids`.

### `graph_artifacts`

- Metadata row for graph-like artifacts.
- Large payloads default to private Supabase Storage.
- API returns signed URL metadata when available.

## Planner V1

Planner module: `backend/app/services/analysis_planner.py`

Constants:

- `FRONTEND_STITCH_GLOB_DEFAULT = "frontend/app/**"`
- `BACKEND_ROUTERS_STITCH_GLOB_DEFAULT = "backend/app/routers/**"`

Rules:

- Migration changes enable schema extraction and schema verifier path.
- Router-like changes enable route extraction and route binding verifier path.
- Both frontend and router changes enable frontend-backend stitch path.
- Async checks require matching files and `async_checks_enabled`.
- Small changed-file sets without migrations use `focused_contract_scan`.

Planner limitations:

- V1 uses file-path heuristics only.
- The file-count threshold is cost control, not a risk score.
- Verifier audits and user feedback are the intended training signal for future planner improvements.

## Orchestrator and Subtasks

The orchestrator lives in `backend/app/worker/tasks.py`.

Current task IDs:

- `intake_scope`
- `fetch_repo_context`
- `build_dependency_graph`
- `route_extraction`
- `schema_extraction`
- `frontend_backend_stitch`
- `cpg_mining`
- `path_miner`
- `ranker`
- `route_binding_verifier`
- `schema_reference_verifier`
- `async_task_binding_verifier`
- `surface`

Each task has its own status in the persisted task graph:

- `pending`
- `in_progress`
- `completed`
- `failed`
- `blocked`

## Degraded Mode

### `completed_ok`

- All planned subtasks completed successfully.
- Surfaced primary findings have deterministic verifier support.

### `completed_degraded`

- Run finished, but one or more planned subtasks failed or were blocked.
- The API and UI must show which task IDs failed and why.

### `failed`

- Intake, planning, or orchestration could not produce an auditable run.

Failure semantics:

- Failed task => dependents become `blocked`.
- Findings depending on failed tasks are withheld or omitted.
- Partial outputs are persisted for audit.
- Auto-retries stay on the same analysis row.
- User rerun creates a new row and sets `rerun_of_analysis_id`.

## Verification

Verifier service: `backend/app/services/verifier_service.py`

Principles:

- ML never establishes final truth.
- Deterministic checks are the trust boundary.
- Findings are surfaced only after deterministic verification.
- Withheld findings retain verifier evidence and reasons.

Phase 1 verification priorities:

1. route/API seam checks
2. schema reference checks
3. auth guard heuristics
4. migration-order checks
5. RLS sufficiency
6. async task contract checks

## API

Repo-scoped analysis endpoints:

- `GET /v1/repos/{repo_id}/analyses/{id}`
- `GET /v1/repos/{repo_id}/analyses/{id}/plan`
- `GET /v1/repos/{repo_id}/analyses/{id}/findings`
- `GET /v1/repos/{repo_id}/analyses/{id}/audit`
- `GET /v1/repos/{repo_id}/analyses/{id}/graph`
- `POST /v1/repos/{repo_id}/analyses/{id}/rerun`

`GET /graph` returns metadata and, when available:

- `download_url`
- `download_url_expires_at`

## UI

The analysis dashboard should show:

- PR overview
- plan and task graph
- verified findings
- withheld findings with reasons
- audit events
- graph artifact metadata

## ML Contract

- GraphCodeBERT remains a ranking helper only.
- Optional GNN enrichment remains advisory.
- Surface layer enforces deterministic trust boundaries.
