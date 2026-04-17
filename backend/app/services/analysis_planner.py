"""Plan-first analysis task graph builder."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any

FRONTEND_STITCH_GLOB_DEFAULT = "frontend/app/**"
BACKEND_ROUTERS_STITCH_GLOB_DEFAULT = "backend/app/routers/**"


@dataclass(slots=True)
class PlannedTask:
    id: str
    kind: str
    deps: list[str]
    status: str = "pending"
    reason: str = ""
    optional: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "deps": list(self.deps),
            "status": self.status,
            "reason": self.reason,
            "optional": self.optional,
        }


def build_analysis_plan(
    changed_files: list[str],
    *,
    org_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = dict(org_settings or {})
    frontend_globs = [FRONTEND_STITCH_GLOB_DEFAULT, *list(settings.get("frontend_stitch_globs") or [])]
    backend_globs = [
        BACKEND_ROUTERS_STITCH_GLOB_DEFAULT,
        *list(settings.get("backend_router_stitch_globs") or []),
    ]
    async_enabled = bool(settings.get("async_checks_enabled", False))
    focused_limit = int(settings.get("focused_contract_scan_max_changed_files") or 15)

    migration_changed = _matches_any(
        changed_files,
        ["supabase/migrations/**", "**/migrations/**/*.sql"],
    )
    route_changed = _matches_any(
        changed_files,
        ["backend/**/routers/**", "**/api/routes/**", "**/*router*.py"],
    )
    frontend_changed = _matches_any(changed_files, frontend_globs)
    backend_router_changed = _matches_any(changed_files, backend_globs)
    stitch_enabled = frontend_changed and backend_router_changed
    async_changed = _matches_any(changed_files, ["**/celery*.py", "**/tasks.py", "**/worker/**"])
    rls_touched = _matches_any(changed_files, ["**/policies/**", "**/*rls*", "supabase/**/*.sql"])

    if len(changed_files) <= focused_limit and not migration_changed:
        analysis_mode = "focused_contract_scan"
    elif len(changed_files) > max(focused_limit * 3, 45):
        analysis_mode = "full"
    else:
        analysis_mode = "standard"

    tasks: list[PlannedTask] = [
        PlannedTask("intake_scope", "orchestrator", [], reason="initialize run context"),
        PlannedTask("fetch_repo_context", "context", ["intake_scope"], reason="fetch tarballs and compare"),
        PlannedTask("build_dependency_graph", "graph", ["fetch_repo_context"], reason="baseline dependency graph"),
        PlannedTask("surface", "surface", ["build_dependency_graph"], reason="finalize run outputs"),
    ]
    reasons: dict[str, Any] = {
        "migration_files_changed": migration_changed,
        "route_files_changed": route_changed,
        "frontend_changed": frontend_changed,
        "backend_router_changed": backend_router_changed,
        "rls_touched": rls_touched,
        "analysis_mode": analysis_mode,
    }
    disabled_subtasks: list[dict[str, Any]] = []

    if route_changed:
        tasks.extend(
            [
                PlannedTask(
                    "route_extraction",
                    "extractor",
                    ["fetch_repo_context"],
                    reason="route-like files changed",
                ),
                PlannedTask(
                    "route_binding_verifier",
                    "verifier",
                    ["route_extraction", "build_dependency_graph"],
                    reason="P0 route/API seam verifier",
                ),
            ]
        )
        _add_surface_dep(tasks, "route_binding_verifier")
    else:
        disabled_subtasks.append(
            {"task_id": "route_extraction", "reason": "route_files_not_changed"}
        )

    if migration_changed:
        tasks.extend(
            [
                PlannedTask(
                    "schema_extraction",
                    "extractor",
                    ["fetch_repo_context"],
                    reason="migration files changed",
                ),
                PlannedTask(
                    "schema_reference_verifier",
                    "verifier",
                    ["schema_extraction", "build_dependency_graph"],
                    reason="P1 schema reference verifier",
                ),
            ]
        )
        _add_surface_dep(tasks, "schema_reference_verifier")
    else:
        disabled_subtasks.append(
            {"task_id": "schema_extraction", "reason": "no_migration_files_changed"}
        )

    if stitch_enabled:
        tasks.extend(
            [
                PlannedTask(
                    "frontend_backend_stitch",
                    "extractor",
                    ["route_extraction", "build_dependency_graph"],
                    reason="frontend and backend router changes overlap",
                ),
                PlannedTask(
                    "cpg_mining",
                    "cpg",
                    ["fetch_repo_context"],
                    reason="CPG contract analysis behind task graph",
                    optional=True,
                ),
                PlannedTask(
                    "path_miner",
                    "cpg",
                    ["cpg_mining", "frontend_backend_stitch"],
                    reason="mine candidate paths for stitched seams",
                    optional=True,
                ),
                PlannedTask(
                    "ranker",
                    "cpg",
                    ["path_miner"],
                    reason="GraphCodeBERT/heuristic prioritization",
                    optional=True,
                ),
            ]
        )
        _add_surface_dep(tasks, "ranker")
    else:
        disabled_subtasks.append(
            {"task_id": "frontend_backend_stitch", "reason": "missing_frontend_or_router_changes"}
        )

    if async_changed and async_enabled:
        tasks.append(
            PlannedTask(
                "async_task_binding_verifier",
                "verifier",
                ["build_dependency_graph"],
                reason="org enabled async checks",
            )
        )
        _add_surface_dep(tasks, "async_task_binding_verifier")
    elif async_changed:
        disabled_subtasks.append(
            {"task_id": "async_task_binding_verifier", "reason": "org_async_checks_disabled"}
        )

    nodes = [task.as_dict() for task in tasks]
    edges = [
        {"from": task_dep, "to": task.id}
        for task in tasks
        for task_dep in task.deps
    ]
    return {
        "plan_type": "gated_pr_risk_v1",
        "analysis_mode": analysis_mode,
        "task_graph": {"nodes": nodes, "edges": edges},
        "reason_json": reasons,
        "disabled_subtasks": disabled_subtasks,
        "planner_limitations": [
            "v1 uses file-path heuristics only.",
            "focused_contract_scan vs standard is scope control, not a risk score.",
            "verifier audits and feedback are the intended future training signal for a smarter planner.",
        ],
    }


def _matches_any(paths: list[str], patterns: list[str]) -> bool:
    normalized = [path.replace("\\", "/") for path in paths]
    for path in normalized:
        for pattern in patterns:
            if fnmatch(path, pattern.replace("\\", "/")):
                return True
    return False


def _add_surface_dep(tasks: list[PlannedTask], dep_id: str) -> None:
    for task in tasks:
        if task.id == "surface" and dep_id not in task.deps:
            task.deps.append(dep_id)
            return
