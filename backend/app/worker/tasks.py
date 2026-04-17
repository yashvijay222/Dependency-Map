"""Analysis agent loop orchestration and task execution."""

from __future__ import annotations

import logging
import tempfile
import traceback
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks
from supabase import Client, create_client

from app.config import settings
from app.services.analysis_planner import build_analysis_plan
from app.services.analysis_runs import (
    append_run_event,
    coerce_json_text,
    create_analysis_plan,
    persist_findings_and_audits,
    record_graph_artifact,
    summarize_task_graph,
    update_task_status,
)
from app.services.blast_radius import (
    compute_blast_radius,
    compute_cross_repo_blast_radius,
    stub_blast_summary,
)
from app.services.codeowners import suggested_reviewers_from_codeowners
from app.services.github_client import (
    changed_files_from_compare,
    compare_commits,
    fetch_codeowners_text,
    fetch_tarball_to_dir,
    get_installation_token,
    github_configured,
)
from app.services.graph_builder import build_dependency_graph
from app.services.intelligent_scorer import run_intelligent_scoring
from app.services.verifier_service import evaluate_offline_finding
from app.worker.cross_repo_tasks import org_settings

log = logging.getLogger(__name__)


def schedule_analysis_job(
    analysis_id: str,
    background: BackgroundTasks | None = None,
) -> None:
    """Run via Celery when configured; otherwise FastAPI BackgroundTasks or inline."""
    if settings.use_celery:
        try:
            from app.celery_app import run_analysis_task

            run_analysis_task.delay(analysis_id)
        except Exception:
            log.exception("Celery enqueue failed; running inline")
            run_analysis_job(analysis_id)
        return
    if background is not None:
        background.add_task(run_analysis_job, analysis_id)
    else:
        run_analysis_job(analysis_id)


def run_analysis_job(analysis_id: str) -> None:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        log.warning("Supabase not configured; skip analysis %s", analysis_id)
        return
    sb = create_client(settings.supabase_url, settings.supabase_service_role_key)
    try:
        _run_analysis_orchestrator(sb, analysis_id)
    except Exception:
        log.exception("Analysis job failed %s", analysis_id)
        sb.table("pr_analyses").update(
            {
                "status": "failed",
                "outcome": "failed",
                "error": traceback.format_exc()[:8000],
            },
        ).eq("id", analysis_id).execute()


def _run_analysis_orchestrator(sb: Client, analysis_id: str) -> None:
    row = _load_analysis(sb, analysis_id)
    if not row:
        log.error("Analysis %s not found", analysis_id)
        return
    repo = _load_repo(sb, str(row["repo_id"]))
    if not repo:
        raise RuntimeError("Repository not found for analysis")

    repo_id = str(repo["id"])
    org_id = str(repo["org_id"])
    full_name = str(repo["full_name"])
    base_sha = str(row.get("base_sha") or "")
    head_sha = str(row.get("head_sha") or "")
    want_cross = bool(row.get("cross_repo"))
    installation_id = _load_installation_id(sb, org_id)
    oset = org_settings(sb, org_id)

    sb.table("pr_analyses").update(
        {
            "status": "running",
            "outcome": None,
            "error": None,
            "summary_json": {},
            "partial_outputs": [],
        }
    ).eq("id", analysis_id).execute()

    summary: dict[str, Any] = {}
    partial_outputs: list[dict[str, Any]] = []
    task_graph: dict[str, Any] = {"nodes": [], "edges": []}
    state: dict[str, Any] = {
        "summary": summary,
        "partial_outputs": partial_outputs,
        "audit_rows": [],
        "artifact_ids": [],
        "repo": repo,
        "org_settings": oset,
        "run_cross": want_cross,
        "repo_id": repo_id,
        "org_id": org_id,
        "full_name": full_name,
        "base_sha": base_sha,
        "head_sha": head_sha,
    }

    append_run_event(
        sb,
        analysis_id=analysis_id,
        repo_id=repo_id,
        task_id="fetch_repo_context",
        event_type="started",
    )

    with tempfile.TemporaryDirectory() as tmp:
        _prepare_repo_context(
            sb,
            analysis_id,
            repo_id,
            installation_id,
            state,
            tmp_root=Path(tmp),
        )
        append_run_event(
            sb,
            analysis_id=analysis_id,
            repo_id=repo_id,
            task_id="fetch_repo_context",
            event_type="completed",
            metadata={"changed_files": len(state.get("changed_files") or [])},
        )

        plan = build_analysis_plan(
            list(state.get("changed_files") or []),
            org_settings=oset,
        )
        state["summary"]["analysis_mode"] = plan["analysis_mode"]
        task_graph = create_analysis_plan(
            sb,
            analysis_id=analysis_id,
            repo_id=repo_id,
            analysis_mode=str(plan["analysis_mode"]),
            task_graph=plan["task_graph"],
            reason_json=dict(plan["reason_json"]),
            disabled_subtasks=list(plan["disabled_subtasks"]),
        ).get("task_graph_json") or dict(plan["task_graph"])
        task_graph = update_task_status(
            sb,
            analysis_id=analysis_id,
            task_graph=task_graph,
            task_id="fetch_repo_context",
            status="completed",
        )
        task_graph = update_task_status(
            sb,
            analysis_id=analysis_id,
            task_graph=task_graph,
            task_id="intake_scope",
            status="completed",
        )
        sb.table("pr_analyses").update({"mode": plan["analysis_mode"]}).eq("id", analysis_id).execute()

        task_graph = _execute_task_graph(sb, analysis_id, repo_id, task_graph, state)

    summary = dict(state.get("summary") or {})
    partial_outputs = list(state.get("partial_outputs") or [])
    counts = summarize_task_graph(task_graph)
    failed_like = counts.get("failed", 0) + counts.get("blocked", 0)
    outcome = "completed_degraded" if failed_like else "completed_ok"
    status = "completed"

    if state.get("audit_rows"):
        persisted = persist_findings_and_audits(
            sb,
            analysis_id=analysis_id,
            repo_id=repo_id,
            audit_rows=list(state["audit_rows"]),
            graph_artifact_ids=list(state.get("artifact_ids") or []),
        )
        summary["verified_findings"] = persisted["verified"]
        summary["withheld_findings"] = persisted["withheld"]

    summary["task_counts"] = counts
    summary["analysis_mode"] = (
        summary.get("analysis_mode") or state.get("org_settings", {}).get("analysis_mode") or row.get("mode")
    )
    summary["outcome"] = outcome
    sb.table("pr_analyses").update(
        {
            "status": status,
            "outcome": outcome,
            "summary_json": summary,
            "partial_outputs": partial_outputs,
            "error": None,
        }
    ).eq("id", analysis_id).execute()


def _prepare_repo_context(
    sb: Client,
    analysis_id: str,
    repo_id: str,
    installation_id: int | None,
    state: dict[str, Any],
    *,
    tmp_root: Path,
) -> None:
    full_name = str(state["full_name"])
    base_sha = str(state["base_sha"])
    head_sha = str(state["head_sha"])
    if github_configured() and installation_id is not None and base_sha and head_sha:
        token = get_installation_token(installation_id)
        base_root = tmp_root / "base"
        head_root = tmp_root / "head"
        root_b = fetch_tarball_to_dir(full_name, base_sha, token, base_root)
        root_h = fetch_tarball_to_dir(full_name, head_sha, token, head_root)
        compare_js = compare_commits(full_name, base_sha, head_sha, token)
        changed = changed_files_from_compare(compare_js)
        state.update(
            {
                "token": token,
                "base_root": root_b,
                "head_root": root_h,
                "compare_js": compare_js,
                "changed_files": changed,
            }
        )
        artifact = record_graph_artifact(
            sb,
            analysis_id=analysis_id,
            repo_id=repo_id,
            kind="compare_payload",
            commit_sha=head_sha,
            content=coerce_json_text(compare_js),
            preview={"changed_files": len(changed)},
            metadata={"source": "github_compare"},
        )
        if artifact.get("id"):
            state["artifact_ids"].append(artifact["id"])
        return

    stub = stub_blast_summary()
    stub["schema_version"] = 1
    stub["risks"] = [
        *(stub.get("risks") or []),
        "GitHub App or installation not configured, or SHAs missing; using degraded stub context.",
    ]
    state["summary"].update(stub)
    state["changed_files"] = []
    state["degraded_context"] = True
    state["partial_outputs"].append(
        {"task_id": "fetch_repo_context", "reason": "github_context_unavailable"}
    )


def _execute_task_graph(
    sb: Client,
    analysis_id: str,
    repo_id: str,
    task_graph: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    handlers = {
        "build_dependency_graph": _task_build_dependency_graph,
        "route_extraction": _task_route_extraction,
        "schema_extraction": _task_schema_extraction,
        "frontend_backend_stitch": _task_frontend_backend_stitch,
        "cpg_mining": _task_cpg_mining,
        "path_miner": _task_path_miner,
        "ranker": _task_ranker,
        "route_binding_verifier": _task_route_binding_verifier,
        "schema_reference_verifier": _task_schema_reference_verifier,
        "async_task_binding_verifier": _task_async_task_binding_verifier,
        "surface": _task_surface,
    }
    progressed = True
    while progressed:
        progressed = False
        nodes = list(task_graph.get("nodes") or [])
        for node in nodes:
            task_id = str(node.get("id"))
            status = str(node.get("status") or "pending")
            if status != "pending":
                continue
            deps = [str(dep) for dep in node.get("deps") or []]
            dep_status = {dep: _node_status(task_graph, dep) for dep in deps}
            if any(value in {"failed", "blocked"} for value in dep_status.values()):
                task_graph = update_task_status(
                    sb,
                    analysis_id=analysis_id,
                    task_graph=task_graph,
                    task_id=task_id,
                    status="blocked",
                )
                append_run_event(
                    sb,
                    analysis_id=analysis_id,
                    repo_id=repo_id,
                    task_id=task_id,
                    event_type="withheld",
                    error_code="blocked",
                    metadata={"deps": dep_status},
                )
                state["partial_outputs"].append({"task_id": task_id, "reason": "blocked"})
                progressed = True
                continue
            if any(value != "completed" for value in dep_status.values()):
                continue

            task_graph = update_task_status(
                sb,
                analysis_id=analysis_id,
                task_graph=task_graph,
                task_id=task_id,
                status="in_progress",
            )
            append_run_event(
                sb,
                analysis_id=analysis_id,
                repo_id=repo_id,
                task_id=task_id,
                event_type="started",
            )
            try:
                handler = handlers.get(task_id)
                if handler is not None:
                    handler(sb, analysis_id, repo_id, state)
                task_graph = update_task_status(
                    sb,
                    analysis_id=analysis_id,
                    task_graph=task_graph,
                    task_id=task_id,
                    status="completed",
                )
                append_run_event(
                    sb,
                    analysis_id=analysis_id,
                    repo_id=repo_id,
                    task_id=task_id,
                    event_type="completed",
                )
            except Exception as exc:
                log.exception("Task %s failed for analysis %s", task_id, analysis_id)
                task_graph = update_task_status(
                    sb,
                    analysis_id=analysis_id,
                    task_graph=task_graph,
                    task_id=task_id,
                    status="failed",
                )
                append_run_event(
                    sb,
                    analysis_id=analysis_id,
                    repo_id=repo_id,
                    task_id=task_id,
                    event_type="failed",
                    error_code=type(exc).__name__,
                    metadata={"message": str(exc)},
                )
                state["partial_outputs"].append({"task_id": task_id, "reason": str(exc)})
            progressed = True
    return task_graph


def _task_build_dependency_graph(
    sb: Client,
    analysis_id: str,
    repo_id: str,
    state: dict[str, Any],
) -> None:
    if state.get("degraded_context"):
        return
    root_b = Path(state["base_root"])
    root_h = Path(state["head_root"])
    g_base = build_dependency_graph(root_b)
    g_head = build_dependency_graph(root_h)
    changed = list(state.get("changed_files") or [])
    intel = run_intelligent_scoring(
        str(state["org_id"]),
        str(state["repo_id"]),
        str(state["full_name"]),
        g_head,
        g_base,
        changed,
        head_repo_root=root_h,
        head_sha=str(state["head_sha"]),
    )
    blast = intel.get("blast") or compute_blast_radius(g_head, changed, g_base)
    token = state.get("token")
    reviewers: list[str] = []
    if token:
        co_text = fetch_codeowners_text(str(state["full_name"]), str(state["head_sha"]), token)
        impacted = blast.get("impacted_modules", [])
        reviewers = suggested_reviewers_from_codeowners(
            co_text,
            list(dict.fromkeys([*impacted, *changed])),
        )
    summary = state["summary"]
    summary.update(
        {
            "schema_version": int(intel.get("schema_version") or 2),
            "changed_files": changed,
            "changed_dependency_edges": blast.get("changed_dependency_edges", []),
            "impacted_modules": blast.get("impacted_modules", []),
            "blast_radius_score": blast.get("blast_radius_score", 0),
            "confidence": blast.get("confidence", "medium"),
            "suggested_reviewers": reviewers,
            "risks": blast.get("risks", []),
        }
    )
    if intel.get("ml_metadata"):
        summary["ml_metadata"] = intel["ml_metadata"]
    if intel.get("changed_nodes") is not None:
        summary["changed_nodes"] = intel["changed_nodes"]
    if intel.get("risk_anomalies") is not None:
        summary["risk_anomalies"] = intel["risk_anomalies"]
    state["g_base"] = g_base
    state["g_head"] = g_head
    state["blast"] = blast

    preview = {
        "node_count": len(g_head.get("nodes") or []),
        "edge_count": len(g_head.get("edges") or []),
        "changed_files": len(changed),
    }
    artifact = record_graph_artifact(
        sb,
        analysis_id=analysis_id,
        repo_id=repo_id,
        kind="base_dependency_graph",
        commit_sha=str(state["head_sha"]),
        content=coerce_json_text(g_head),
        preview=preview,
        metadata={"analysis_mode": summary.get("analysis_mode")},
    )
    if artifact.get("id"):
        state["artifact_ids"].append(artifact["id"])

    if state.get("run_cross"):
        _apply_cross_repo_blast(sb, state)


def _task_route_extraction(_sb: Client, _analysis_id: str, _repo_id: str, state: dict[str, Any]) -> None:
    changed = list(state.get("changed_files") or [])
    state["route_files"] = [
        path for path in changed if "/routers/" in path.replace("\\", "/") or "router" in path.lower()
    ]
    state["summary"]["route_files_changed"] = state["route_files"]


def _task_schema_extraction(_sb: Client, _analysis_id: str, _repo_id: str, state: dict[str, Any]) -> None:
    changed = list(state.get("changed_files") or [])
    state["migration_files"] = [
        path
        for path in changed
        if "migrations/" in path.replace("\\", "/") or path.lower().endswith(".sql")
    ]
    state["summary"]["migration_files_changed"] = state["migration_files"]


def _task_frontend_backend_stitch(
    _sb: Client,
    _analysis_id: str,
    _repo_id: str,
    state: dict[str, Any],
) -> None:
    changed = list(state.get("changed_files") or [])
    frontend = [path for path in changed if path.replace("\\", "/").startswith("frontend/app/")]
    backend = list(state.get("route_files") or [])
    state["summary"]["stitch_overview"] = {
        "frontend_candidates": frontend[:20],
        "backend_candidates": backend[:20],
        "enabled": bool(frontend and backend),
    }


def _task_cpg_mining(sb: Client, analysis_id: str, repo_id: str, state: dict[str, Any]) -> None:
    if not settings.enable_cpg_bridge:
        raise RuntimeError("CPG bridge disabled")
    head_root = state.get("head_root")
    if head_root is None:
        raise RuntimeError("Head checkout unavailable for CPG")
    from cpg_builder.scorer import score_repository

    out_dir = Path(head_root).parent / "cpg-artifacts"
    artifacts = score_repository(Path(head_root), out_dir)
    state["cpg_artifacts"] = artifacts
    state["audit_rows"] = list(artifacts.verifier_audit)
    preview = {
        "candidate_count": artifacts.run_metadata.get("candidate_count"),
        "surfaced_count": artifacts.run_metadata.get("surfaced_count"),
        "run_id": artifacts.run_id,
    }
    artifact = record_graph_artifact(
        sb,
        analysis_id=analysis_id,
        repo_id=repo_id,
        kind="base_cpg",
        commit_sha=str(state["head_sha"]),
        content=coerce_json_text(
            {
                "run_metadata": artifacts.run_metadata,
                "violations": artifacts.violations,
                "audit": artifacts.verifier_audit,
            }
        ),
        preview=preview,
        metadata={"run_id": artifacts.run_id},
    )
    if artifact.get("id"):
        state["artifact_ids"].append(artifact["id"])


def _task_path_miner(_sb: Client, _analysis_id: str, _repo_id: str, state: dict[str, Any]) -> None:
    artifacts = state.get("cpg_artifacts")
    if artifacts is None:
        raise RuntimeError("CPG artifacts missing")
    state["summary"]["cpg_candidate_count"] = artifacts.run_metadata.get("candidate_count", 0)


def _task_ranker(_sb: Client, _analysis_id: str, _repo_id: str, state: dict[str, Any]) -> None:
    artifacts = state.get("cpg_artifacts")
    if artifacts is None:
        raise RuntimeError("CPG artifacts missing")
    state["summary"]["cpg_surfaced_count"] = artifacts.run_metadata.get("surfaced_count", 0)


def _task_route_binding_verifier(
    _sb: Client,
    _analysis_id: str,
    _repo_id: str,
    state: dict[str, Any],
) -> None:
    route_findings = [
        evaluate_offline_finding(finding).as_dict()
        for finding in list(state.get("audit_rows") or [])
        if finding.get("invariant_id") == "frontend_route_binding"
    ]
    state["summary"]["route_binding_verifier"] = {
        "count": len(route_findings),
        "verified": sum(1 for row in route_findings if row["status"] == "verified"),
    }


def _task_schema_reference_verifier(
    _sb: Client,
    _analysis_id: str,
    _repo_id: str,
    state: dict[str, Any],
) -> None:
    schema_findings = [
        evaluate_offline_finding(finding).as_dict()
        for finding in list(state.get("audit_rows") or [])
        if finding.get("invariant_id") == "schema_entity_still_referenced"
    ]
    state["summary"]["schema_reference_verifier"] = {
        "count": len(schema_findings),
        "verified": sum(1 for row in schema_findings if row["status"] == "verified"),
    }


def _task_async_task_binding_verifier(
    _sb: Client,
    _analysis_id: str,
    _repo_id: str,
    state: dict[str, Any],
) -> None:
    task_findings = [
        evaluate_offline_finding(finding).as_dict()
        for finding in list(state.get("audit_rows") or [])
        if finding.get("invariant_id") == "celery_task_binding"
    ]
    state["summary"]["async_task_binding_verifier"] = {
        "count": len(task_findings),
        "verified": sum(1 for row in task_findings if row["status"] == "verified"),
    }


def _task_surface(_sb: Client, _analysis_id: str, _repo_id: str, state: dict[str, Any]) -> None:
    if not state.get("audit_rows"):
        state["summary"]["verified_findings"] = 0
        state["summary"]["withheld_findings"] = 0
        return
    audits = [evaluate_offline_finding(row) for row in list(state["audit_rows"])]
    state["summary"]["verified_findings"] = sum(1 for audit in audits if audit.status == "verified")
    state["summary"]["withheld_findings"] = sum(1 for audit in audits if audit.status == "withheld")


def _apply_cross_repo_blast(sb: Client, state: dict[str, Any]) -> None:
    repo_id = str(state["repo_id"])
    org_id = str(state["org_id"])
    edges_res = (
        sb.table("cross_repo_edges")
        .select("*")
        .eq("org_id", org_id)
        .eq("target_repo_id", repo_id)
        .execute()
    )
    cross_edges = edges_res.data or []
    if not cross_edges:
        state["summary"]["cross_repo_impacts"] = []
        state["summary"]["aggregate_cross_repo_score"] = 0
        state["summary"]["cross_repo_truncated"] = False
        return
    max_consumers = int(state["org_settings"].get("max_consumer_repos") or settings.max_consumer_repos)
    consumers: dict[str, tuple[str, dict[str, Any]]] = {}
    for edge in cross_edges:
        sid = str(edge.get("source_repo_id") or "")
        if sid == repo_id or sid in consumers:
            continue
        repo_res = (
            sb.table("repositories")
            .select("full_name, default_branch")
            .eq("id", sid)
            .limit(1)
            .execute()
        )
        if not repo_res.data:
            continue
        row = repo_res.data[0]
        default_branch = str(row.get("default_branch") or "main")
        snap = (
            sb.table("dependency_snapshots")
            .select("graph_json")
            .eq("repo_id", sid)
            .eq("branch", default_branch)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if snap.data:
            consumers[sid] = (str(row["full_name"]), snap.data[0].get("graph_json") or {})
    xb = compute_cross_repo_blast_radius(
        str(state["full_name"]),
        repo_id,
        state["g_head"],
        list(state.get("changed_files") or []),
        cross_edges,
        consumers,
        max_consumer_repos=max_consumers,
        max_super_nodes=settings.super_graph_max_nodes,
    )
    state["summary"]["cross_repo_impacts"] = xb.get("cross_repo_impacts", [])
    state["summary"]["aggregate_cross_repo_score"] = xb.get("aggregate_cross_repo_score", 0)
    state["summary"]["cross_repo_truncated"] = xb.get("cross_repo_truncated", False)


def _node_status(task_graph: dict[str, Any], task_id: str) -> str:
    for node in task_graph.get("nodes") or []:
        if str(node.get("id")) == task_id:
            return str(node.get("status") or "pending")
    return "pending"


def _load_analysis(sb: Client, analysis_id: str) -> dict[str, Any] | None:
    res = sb.table("pr_analyses").select("*").eq("id", analysis_id).limit(1).execute()
    return res.data[0] if res.data else None


def _load_repo(sb: Client, repo_id: str) -> dict[str, Any] | None:
    res = sb.table("repositories").select("*").eq("id", repo_id).limit(1).execute()
    return res.data[0] if res.data else None


def _load_installation_id(sb: Client, org_id: str) -> int | None:
    res = (
        sb.table("github_installations")
        .select("installation_id")
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    return int(res.data[0]["installation_id"]) if res.data else None
