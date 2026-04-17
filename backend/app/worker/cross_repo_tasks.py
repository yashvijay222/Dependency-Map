"""Cross-repo snapshot, org graph, branch drift Celery tasks."""

from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Any

from supabase import create_client

from app.config import settings
from app.observability import emit_pipeline_event
from app.services.ast_parser import build_ast_graph
from app.services.branch_monitor import compute_drift_signals
from app.services.github_client import (
    fetch_tarball_to_dir,
    get_branch_head_sha,
    get_installation_token,
    github_configured,
)
from app.services.graph_builder import build_dependency_graph
from app.services.package_resolver import (
    build_package_registry,
    extract_published_packages,
    resolve_cross_repo_edges,
)

log = logging.getLogger(__name__)


def _sb():
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def org_settings(sb: Any, org_id: str) -> dict[str, Any]:
    res = sb.table("organizations").select("settings").eq("id", org_id).limit(1).execute()
    if not res.data:
        return {}
    raw = res.data[0].get("settings")
    return raw if isinstance(raw, dict) else {}


def snapshot_repo_branch(repo_id: str, branch: str, sha: str | None = None) -> None:
    """Download tarball, build graph, persist snapshot + packages + edges."""
    sb = _sb()
    if sb is None:
        log.warning("snapshot_repo_branch: no supabase")
        return
    emit_pipeline_event(
        "snapshot_repo_branch_started",
        repo_id=repo_id,
        task_id="snapshot_repo_branch",
        extra={"branch": branch, "sha": sha},
    )
    if not github_configured():
        log.warning("snapshot_repo_branch: GitHub not configured")
        return

    rres = (
        sb.table("repositories")
        .select("id, full_name, org_id, default_branch")
        .eq("id", repo_id)
        .limit(1)
        .execute()
    )
    if not rres.data:
        log.error("snapshot_repo_branch: repo %s not found", repo_id)
        return
    repo = rres.data[0]
    full_name = str(repo["full_name"])
    org_id = str(repo["org_id"])
    inst = (
        sb.table("github_installations")
        .select("installation_id")
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not inst.data:
        log.error("snapshot_repo_branch: no installation for org %s", org_id)
        return
    token = get_installation_token(int(inst.data[0]["installation_id"]))
    commit_sha = sha or get_branch_head_sha(full_name, branch, token)

    with tempfile.TemporaryDirectory() as tmp:
        root = fetch_tarball_to_dir(full_name, commit_sha, token, Path(tmp) / "src")
        graph = build_dependency_graph(root)
        ast_graph = build_ast_graph(root)
        packages = extract_published_packages(root, branch=branch)

    snap = {
        "repo_id": repo_id,
        "branch": branch,
        "commit_sha": commit_sha,
        "graph_json": graph,
        "ast_graph_json": ast_graph,
    }
    sb.table("dependency_snapshots").upsert(snap, on_conflict="repo_id,branch,commit_sha").execute()
    sb.table("ast_graph_snapshots").upsert(
        {
            "repo_id": repo_id,
            "branch": branch,
            "commit_sha": commit_sha,
            "ast_graph_json": ast_graph,
        },
        on_conflict="repo_id,branch,commit_sha",
    ).execute()

    for p in packages:
        row = {
            "repo_id": repo_id,
            "branch": branch,
            "package_name": p["name"],
            "package_version": p.get("version") or "",
            "workspace_path": p.get("workspace_path"),
        }
        sb.table("repo_packages").upsert(
            row,
            on_conflict="repo_id,branch,package_name",
        ).execute()

    sb.table("dependency_edges").delete().eq("repo_id", repo_id).eq("commit_sha", commit_sha).eq(
        "branch",
        branch,
    ).execute()
    edge_rows: list[dict[str, Any]] = []
    for e in graph.get("edges", []) or []:
        if not isinstance(e, dict):
            continue
        s, t = str(e.get("source", "")), str(e.get("target", ""))
        et = str(e.get("type", "import"))
        edge_rows.append(
            {
                "repo_id": repo_id,
                "commit_sha": commit_sha,
                "branch": branch,
                "source_path": s,
                "target_path": t,
                "edge_type": et,
            },
        )
    batch = 500
    for i in range(0, len(edge_rows), batch):
        sb.table("dependency_edges").insert(edge_rows[i : i + batch]).execute()

    emit_pipeline_event(
        "snapshot_repo_branch_finished",
        org_id=org_id,
        repo_id=repo_id,
        task_id="snapshot_repo_branch",
        extra={"branch": branch, "commit_sha": commit_sha},
    )


def build_repo_ast_snapshot(
    repo_id: str,
    branch: str | None = None,
    sha: str | None = None,
) -> dict[str, Any] | None:
    sb = _sb()
    if sb is None:
        log.warning("build_repo_ast_snapshot: no supabase")
        return None
    if not github_configured():
        log.warning("build_repo_ast_snapshot: GitHub not configured")
        return None

    rres = (
        sb.table("repositories")
        .select("id, full_name, org_id, default_branch")
        .eq("id", repo_id)
        .limit(1)
        .execute()
    )
    if not rres.data:
        log.error("build_repo_ast_snapshot: repo %s not found", repo_id)
        return None
    repo = rres.data[0]
    full_name = str(repo["full_name"])
    org_id = str(repo["org_id"])
    branch_name = branch or str(repo.get("default_branch") or "main")
    inst = (
        sb.table("github_installations")
        .select("installation_id")
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not inst.data:
        log.error("build_repo_ast_snapshot: no installation for org %s", org_id)
        return None
    token = get_installation_token(int(inst.data[0]["installation_id"]))
    commit_sha = sha or get_branch_head_sha(full_name, branch_name, token)

    with tempfile.TemporaryDirectory() as tmp:
        root = fetch_tarball_to_dir(full_name, commit_sha, token, Path(tmp) / "src")
        ast_graph = build_ast_graph(root)

    snapshot = {
        "repo_id": repo_id,
        "branch": branch_name,
        "commit_sha": commit_sha,
        "ast_graph_json": ast_graph,
    }
    sb.table("ast_graph_snapshots").upsert(
        snapshot,
        on_conflict="repo_id,branch,commit_sha",
    ).execute()
    try:
        sb.table("dependency_snapshots").update({"ast_graph_json": ast_graph}).eq(
            "repo_id",
            repo_id,
        ).eq("branch", branch_name).eq("commit_sha", commit_sha).execute()
    except Exception:
        log.debug("dependency_snapshots ast_graph_json update skipped", exc_info=True)
    return snapshot


def build_org_graph(org_id: str, branch: str | None = None) -> None:
    """Rebuild cross_repo_edges from latest snapshots + repo_packages."""
    sb = _sb()
    if sb is None:
        return
    emit_pipeline_event(
        "build_org_graph_started",
        org_id=org_id,
        task_id="build_org_graph",
        extra={"branch": branch},
    )
    repos = (
        sb.table("repositories")
        .select("id, full_name, default_branch, org_id")
        .eq("org_id", org_id)
        .execute()
    )
    if not repos.data:
        emit_pipeline_event(
            "build_org_graph_finished",
            org_id=org_id,
            task_id="build_org_graph",
            extra={"skipped": True, "reason": "no_repos"},
        )
        return
    repo_list = [r for r in repos.data if str(r.get("org_id")) == org_id]
    repo_graphs: dict[str, dict[str, Any]] = {}
    repo_meta: dict[str, dict[str, Any]] = {}
    default_branches: dict[str, str] = {}

    for r in repo_list:
        rid = str(r["id"])
        br = branch or str(r.get("default_branch") or "main")
        default_branches[rid] = br
        snap = (
            sb.table("dependency_snapshots")
            .select("graph_json, commit_sha")
            .eq("repo_id", rid)
            .eq("branch", br)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not snap.data:
            continue
        repo_graphs[rid] = snap.data[0].get("graph_json") or {}
        repo_meta[rid] = {"id": rid, "full_name": str(r["full_name"]), "org_id": org_id}

    registry_rows: list[dict[str, Any]] = []
    for rid in repo_meta:
        br = branch or default_branches.get(rid, "main")
        pr = sb.table("repo_packages").select("*").eq("repo_id", rid).eq("branch", br).execute()
        registry_rows.extend(pr.data or [])
    registry = build_package_registry(registry_rows)

    br_used = branch or (
        str(repo_list[0].get("default_branch") or "main") if repo_list else "main"
    )

    cross = resolve_cross_repo_edges(org_id, repo_graphs, repo_meta, registry, branch=br_used)
    sb.table("cross_repo_edges_staging").delete().eq("org_id", org_id).execute()
    if cross:
        for i in range(0, len(cross), 200):
            sb.table("cross_repo_edges_staging").insert(cross[i : i + 200]).execute()
    sb.rpc("dm_swap_cross_repo_edges", {"p_org_id": org_id}).execute()
    emit_pipeline_event(
        "build_org_graph_finished",
        org_id=org_id,
        task_id="build_org_graph",
        extra={"branch": br_used, "edge_count": len(cross)},
    )


def compute_branch_drift(repo_id: str, branch_a: str, branch_b: str) -> None:
    sb = _sb()
    if sb is None:
        return
    emit_pipeline_event(
        "compute_branch_drift_started",
        repo_id=repo_id,
        task_id="compute_branch_drift",
        extra={"branch_a": branch_a, "branch_b": branch_b},
    )

    def load_graph(br: str) -> tuple[dict[str, Any], str]:
        res = (
            sb.table("dependency_snapshots")
            .select("graph_json, commit_sha")
            .eq("repo_id", repo_id)
            .eq("branch", br)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not res.data:
            return {}, ""
        return res.data[0].get("graph_json") or {}, str(res.data[0].get("commit_sha") or "")

    ga, sha_a = load_graph(branch_a)
    gb, sha_b = load_graph(branch_b)
    if not sha_a or not sha_b:
        log.warning("compute_branch_drift: missing snapshot for %s / %s", branch_a, branch_b)
        return

    sig = compute_drift_signals(ga, gb, base_sha=sha_a, head_sha=sha_b)
    drift_type = str(sig.get("drift_type") or "")
    overlap = float(sig.get("overlap_score") or 0.0)
    signal_body = {k: v for k, v in sig.items() if k not in ("base_sha", "head_sha", "drift_type")}
    row = {
        "repo_id": repo_id,
        "branch_a": branch_a,
        "branch_b": branch_b,
        "overlap_score": overlap,
        "signal_json": signal_body,
        "base_sha": sha_a,
        "head_sha": sha_b,
        "drift_type": drift_type,
    }
    sb.table("branch_drift_signals").insert(row).execute()
    emit_pipeline_event(
        "compute_branch_drift_finished",
        repo_id=repo_id,
        task_id="compute_branch_drift",
        extra={"branch_a": branch_a, "branch_b": branch_b, "drift_type": drift_type},
    )

    for path in sig.get("conflicting_files") or []:
        if not isinstance(path, str):
            continue
        score = 1.0 - overlap
        sb.table("risk_hotspots").insert(
            {"repo_id": repo_id, "file_path": path, "score": score, "reason": "branch_drift"},
        ).execute()


def enqueue_org_snapshots(org_id: str) -> None:
    """Enqueue snapshot_repo_branch in batches with stagger (called from beat)."""
    from app.celery_app import celery_app

    sb = _sb()
    if sb is None:
        return
    cfg = org_settings(sb, org_id)
    batch = int(cfg.get("snapshot_batch_size") or settings.snapshot_batch_size)
    repos = sb.table("repositories").select("id, default_branch").eq("org_id", org_id).execute()
    if not repos.data:
        return
    delay = 0
    chunk: list[str] = []
    for r in repos.data:
        rid = str(r["id"])
        br = str(r.get("default_branch") or "main")
        chunk.append((rid, br))
        if len(chunk) >= batch:
            for i, (repo_id, br) in enumerate(chunk):
                celery_app.send_task(
                    "dm.snapshot_repo_branch",
                    args=[repo_id, br, None],
                    countdown=delay + i * 2,
                )
            delay += 15
            chunk = []
    for i, (repo_id, br) in enumerate(chunk):
        celery_app.send_task(
            "dm.snapshot_repo_branch",
            args=[repo_id, br, None],
            countdown=delay + i * 2,
        )


def cleanup_deleted_branch(repo_id: str, branch: str) -> None:
    """Remove DB rows for a deleted Git branch and refresh org cross-repo edges."""
    sb = _sb()
    if sb is None:
        return
    rres = (
        sb.table("repositories")
        .select("org_id")
        .eq("id", repo_id)
        .limit(1)
        .execute()
    )
    if not rres.data:
        log.warning("cleanup_deleted_branch: repo %s not found", repo_id)
        return
    org_id = str(rres.data[0]["org_id"])
    sb.table("dependency_snapshots").delete().eq("repo_id", repo_id).eq("branch", branch).execute()
    sb.table("repo_packages").delete().eq("repo_id", repo_id).eq("branch", branch).execute()
    sb.table("dependency_edges").delete().eq("repo_id", repo_id).eq("branch", branch).execute()
    try:
        (
            sb.table("ast_graph_snapshots")
            .delete()
            .eq("repo_id", repo_id)
            .eq("branch", branch)
            .execute()
        )
    except Exception:
        log.debug("ast_graph_snapshots delete skipped", exc_info=True)
    (
        sb.table("branch_drift_signals")
        .delete()
        .eq("repo_id", repo_id)
        .eq("branch_a", branch)
        .execute()
    )
    (
        sb.table("branch_drift_signals")
        .delete()
        .eq("repo_id", repo_id)
        .eq("branch_b", branch)
        .execute()
    )
    log.info("cleanup_deleted_branch: repo=%s branch=%s", repo_id, branch)
    try:
        from app.celery_app import build_org_graph_task

        build_org_graph_task.apply_async(args=[org_id, None], countdown=5)
    except Exception:
        try:
            build_org_graph(org_id, None)
        except Exception:
            log.exception("build_org_graph after branch delete failed")


def enqueue_org_drift_checks(org_id: str) -> None:
    """Bounded drift refresh: default vs each non-default branch that has a snapshot."""
    from app.celery_app import celery_app

    sb = _sb()
    if sb is None:
        return
    cfg = org_settings(sb, org_id)
    cap = int(
        cfg.get("drift_check_max_branches_per_repo") or settings.drift_check_max_branches_per_repo,
    )
    cap = max(1, min(cap, 50))
    repos = sb.table("repositories").select("id, default_branch").eq("org_id", org_id).execute()
    delay = 0
    for r in repos.data or []:
        rid = str(r["id"])
        dbr = str(r.get("default_branch") or "main")
        snap = sb.table("dependency_snapshots").select("branch").eq("repo_id", rid).execute()
        branches = sorted({str(row["branch"]) for row in (snap.data or []) if row.get("branch")})
        others = [b for b in branches if b != dbr][:cap]
        for i, br in enumerate(others):
            celery_app.send_task(
                "dm.compute_branch_drift",
                args=[rid, dbr, br],
                countdown=delay + i * 3,
            )
        delay += len(others) * 3 + 8


def backfill_pr_analysis_schema_versions() -> None:
    """Set schema_version=1 where summary_json has no schema_version."""
    sb = _sb()
    if sb is None:
        return
    res = (
        sb.table("pr_analyses")
        .select("id, summary_json")
        .order("created_at", desc=True)
        .limit(500)
        .execute()
    )
    for row in res.data or []:
        sj = row.get("summary_json")
        if not isinstance(sj, dict) or sj.get("schema_version") is not None:
            continue
        sj = {**sj, "schema_version": 1}
        sb.table("pr_analyses").update({"summary_json": sj}).eq("id", str(row["id"])).execute()


def _org_jitter_seconds(org_id: str, modulo: int = 3600) -> int:
    h = int(hashlib.sha256(org_id.encode()).hexdigest()[:8], 16)
    return h % modulo
