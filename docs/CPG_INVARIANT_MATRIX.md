# Hosted CPG invariant matrix (Phase 1C)

This table documents which **hosted** gates relate to which **CPG / verifier** surfaces. Source code: [backend/app/services/analysis_planner.py](backend/app/services/analysis_planner.py), [backend/cpg_builder/invariants.py](backend/cpg_builder/invariants.py), [backend/app/worker/tasks.py](backend/app/worker/tasks.py).

| Invariant / surface | Hosted planner trigger | Notes |
|---------------------|------------------------|--------|
| `frontend_route_binding` | CPG chain when `cpg_contract_analysis` allows and mining runs | Diff seeds from git workspace, tarball `.git`, or synthetic changed files |
| `schema_entity_still_referenced` | Migration files changed → schema tasks | Also CPG path when mining runs |
| `missing_guard_or_rls_gap` | RLS-related paths in diff | Heuristic path globs |
| `celery_task_binding` | Worker/async paths + org `async_checks_enabled` | |

Keep this file updated when adding invariants or changing `PlannedTask` gates.
