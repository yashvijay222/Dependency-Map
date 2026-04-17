"""Stable DTO for findings shown in UI (Phase 2)."""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Any

from app.config import settings


def present_finding(row: dict[str, Any]) -> dict[str, Any]:
    """Map a ``findings`` row to a human-oriented payload."""
    cand = dict(row.get("candidate_json") or {})
    ver = dict(row.get("verification_json") or {})
    summary = dict(row.get("summary_json") or {})
    facts = dict(cand.get("facts") or {})
    file_hints: list[str] = []
    for key in ("file_path", "entity_name", "route_pattern", "task_name"):
        v = facts.get(key) or cand.get(key)
        if isinstance(v, str) and v:
            file_hints.append(v)
    witness_nodes = [str(n) for n in (cand.get("node_ids") or []) if n is not None][:24]
    evidence_links: list[dict[str, str]] = []
    rid = row.get("repo_id")
    aid = row.get("analysis_id")
    if rid and aid:
        base = settings.app_base_url.rstrip("/")
        evidence_links.append(
            {
                "label": "Analysis in Dependency Map",
                "url": f"{base}/repos/{rid}/analyses/{aid}",
            },
        )
    return {
        "id": row.get("id"),
        "finding_key": row.get("finding_key"),
        "invariant_id": row.get("invariant_id"),
        "severity": row.get("severity"),
        "status": row.get("status"),
        "title": _title_for_invariant(str(row.get("invariant_id") or "")),
        "verdict": ver.get("outcome") or row.get("withhold_reason") or row.get("status"),
        "caveats": list(summary.get("caveats") or ver.get("caveats") or []),
        "file_anchors": file_hints[:12],
        "witness_nodes": witness_nodes,
        "witness": {
            "node_ids": cand.get("node_ids") or [],
            "seam_type": cand.get("seam_type"),
        },
        "evidence_links": evidence_links,
        "rank_score": row.get("rank_score"),
        "rank_phase": row.get("rank_phase"),
    }


def _title_for_invariant(invariant_id: str) -> str:
    mapping = {
        "frontend_route_binding": "Frontend / API route binding",
        "schema_entity_still_referenced": "Schema entity still referenced",
        "missing_guard_or_rls_gap": "RLS / guard coverage",
        "celery_task_binding": "Celery task binding",
    }
    return mapping.get(invariant_id, invariant_id.replace("_", " ").title() or "Contract finding")


def should_suppress_finding(
    audit_row: dict[str, Any],
    rules: list[dict[str, Any]],
) -> bool:
    """Return True if org suppression rules filter this audit before persistence."""
    from datetime import UTC, datetime

    if not rules:
        return False
    inv = str(audit_row.get("invariant_id") or "")
    cand = dict(audit_row.get("candidate") or {})
    facts = dict(cand.get("facts") or {})
    paths: list[str] = []
    for key in ("file_path",):
        v = facts.get(key)
        if isinstance(v, str):
            paths.append(v.replace("\\", "/"))
    fp = str(cand.get("file_path") or "")
    if fp:
        paths.append(fp.replace("\\", "/"))
    for rule in rules:
        if str(rule.get("invariant_id") or "") != inv:
            continue
        exp = rule.get("expires_at")
        if exp:
            try:
                exp_s = str(exp).replace("Z", "+00:00")
                if datetime.fromisoformat(exp_s) < datetime.now(UTC):
                    continue
            except (TypeError, ValueError):
                pass
        glob = str(rule.get("path_glob") or "*")
        for p in paths or [""]:
            if fnmatch(p, glob.replace("\\", "/")) or fnmatch(p or "", glob):
                return True
    return False
