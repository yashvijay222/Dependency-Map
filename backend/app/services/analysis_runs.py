"""Shared persistence helpers for gated analysis runs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from supabase import Client

from app.config import settings


def create_analysis_plan(
    sb: Client,
    *,
    analysis_id: str,
    repo_id: str,
    analysis_mode: str,
    task_graph: dict[str, Any],
    reason_json: dict[str, Any],
    disabled_subtasks: list[dict[str, Any]],
) -> dict[str, Any]:
    res = (
        sb.table("analysis_plans")
        .upsert(
            {
                "run_id": analysis_id,
                "repo_id": repo_id,
                "analysis_mode": analysis_mode,
                "task_graph_json": task_graph,
                "reason_json": reason_json,
                "disabled_subtasks": disabled_subtasks,
            },
            on_conflict="run_id",
        )
        .execute()
    )
    row = (res.data or [{}])[0]
    if row.get("id"):
        sb.table("pr_analyses").update(
            {
                "plan_id": row["id"],
                "mode": analysis_mode,
                "task_graph_state": task_graph,
            }
        ).eq("id", analysis_id).execute()
    return row


def update_task_status(
    sb: Client,
    *,
    analysis_id: str,
    task_graph: dict[str, Any],
    task_id: str,
    status: str,
) -> dict[str, Any]:
    nodes = list(task_graph.get("nodes") or [])
    for node in nodes:
        if str(node.get("id")) == task_id:
            node["status"] = status
            break
    updated = {"nodes": nodes, "edges": list(task_graph.get("edges") or [])}
    sb.table("pr_analyses").update({"task_graph_state": updated}).eq("id", analysis_id).execute()
    sb.table("analysis_plans").update({"task_graph_json": updated}).eq(
        "run_id", analysis_id
    ).execute()
    return updated


def append_run_event(
    sb: Client,
    *,
    analysis_id: str,
    repo_id: str,
    task_id: str,
    event_type: str,
    attempt: int = 1,
    gate: str | None = None,
    error_code: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    sb.table("analysis_run_events").insert(
        {
            "run_id": analysis_id,
            "repo_id": repo_id,
            "task_id": task_id,
            "event_type": event_type,
            "gate": gate,
            "attempt": attempt,
            "error_code": error_code,
            "metadata_json": metadata or {},
        }
    ).execute()


def record_graph_artifact(
    sb: Client,
    *,
    analysis_id: str,
    repo_id: str,
    kind: str,
    commit_sha: str | None,
    content: bytes | None = None,
    preview: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    object_key = None
    byte_size = None
    content_sha256 = None
    bucket = None
    if content:
        byte_size = len(content)
        content_sha256 = hashlib.sha256(content).hexdigest()
        bucket = settings.analysis_artifact_bucket
        object_key = f"{repo_id}/{analysis_id}/{kind}-{content_sha256[:12]}.json"
        try:
            sb.storage.from_(bucket).upload(
                object_key,
                content,
                {"content-type": "application/json", "upsert": "true"},
            )
        except Exception:
            object_key = None
            bucket = None
    res = (
        sb.table("graph_artifacts")
        .insert(
            {
                "analysis_id": analysis_id,
                "repo_id": repo_id,
                "commit_sha": commit_sha,
                "kind": kind,
                "storage_bucket": bucket,
                "object_key": object_key,
                "content_sha256": content_sha256,
                "byte_size": byte_size,
                "compression": "none",
                "preview_jsonb": preview or {},
                "metadata_json": metadata or {},
            }
        )
        .execute()
    )
    return (res.data or [{}])[0]


def signed_graph_artifact_metadata(artifact: dict[str, Any], sb: Client) -> dict[str, Any]:
    bucket = artifact.get("storage_bucket")
    object_key = artifact.get("object_key")
    download_url = None
    expires_at = None
    if bucket and object_key:
        try:
            ttl = int(settings.analysis_signed_url_ttl_seconds)
            signed = sb.storage.from_(bucket).create_signed_url(object_key, ttl)
            if isinstance(signed, dict):
                download_url = signed.get("signedURL") or signed.get("signed_url")
            elif hasattr(signed, "get"):
                download_url = signed.get("signedURL") or signed.get("signed_url")
            if download_url:
                expires_at = (
                    datetime.now(UTC) + timedelta(seconds=ttl)
                ).isoformat()
        except Exception:
            download_url = None
            expires_at = None
    return {
        "id": artifact.get("id"),
        "kind": artifact.get("kind"),
        "commit_sha": artifact.get("commit_sha"),
        "byte_size": artifact.get("byte_size"),
        "compression": artifact.get("compression"),
        "preview_jsonb": artifact.get("preview_jsonb") or {},
        "download_url": download_url,
        "download_url_expires_at": expires_at,
        "metadata_json": artifact.get("metadata_json") or {},
        "created_at": artifact.get("created_at"),
    }


def summarize_task_graph(task_graph: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
        "blocked": 0,
        "skipped": 0,
    }
    for node in task_graph.get("nodes") or []:
        status = str(node.get("status") or "pending")
        counts[status] = counts.get(status, 0) + 1
    return counts


def mark_superseded_for_verdict_change(
    sb: Client,
    *,
    repo_id: str,
    current_analysis_id: str,
    finding_key: Any,
    new_outcome: str | None,
) -> None:
    """Mark older findings superseded when the same key gets a new verifier outcome."""
    if finding_key is None or not new_outcome:
        return
    fk = str(finding_key)
    prev_rows = (
        sb.table("findings")
        .select("id, verification_json")
        .eq("repo_id", repo_id)
        .eq("finding_key", fk)
        .neq("analysis_id", current_analysis_id)
        .in_("status", ["verified", "withheld"])
        .execute()
    )
    new_v = str(new_outcome)
    for row in prev_rows.data or []:
        old_v = str(dict(row.get("verification_json") or {}).get("outcome") or "")
        if old_v and old_v != new_v:
            sb.table("findings").update({"status": "superseded"}).eq("id", row["id"]).execute()


def persist_findings_and_audits(
    sb: Client,
    *,
    analysis_id: str,
    repo_id: str,
    audit_rows: list[dict[str, Any]],
    graph_artifact_ids: list[str],
    org_settings: dict[str, Any] | None = None,
) -> dict[str, int]:
    from app.services.finding_presenter import should_suppress_finding

    rules = list((org_settings or {}).get("finding_suppressions") or [])
    verified = 0
    withheld = 0
    for audit in audit_rows:
        if rules and should_suppress_finding(audit, rules):
            continue
        verification = dict(audit.get("verification") or {})
        surfaced = bool(verification.get("surfaced"))
        status = "verified" if surfaced else "withheld"
        if surfaced:
            verified += 1
        else:
            withheld += 1
        mark_superseded_for_verdict_change(
            sb,
            repo_id=repo_id,
            current_analysis_id=analysis_id,
            finding_key=audit.get("finding_id"),
            new_outcome=str(verification.get("outcome") or "") or None,
        )
        finding_payload = {
            "analysis_id": analysis_id,
            "repo_id": repo_id,
            "finding_key": audit.get("finding_id"),
            "invariant_id": audit.get("invariant_id"),
            "severity": audit.get("severity") or "medium",
            "status": status,
            "withhold_reason": None if surfaced else verification.get("outcome") or "withheld",
            "rank_score": audit.get("rank_score"),
            "rank_phase": audit.get("rank_phase"),
            "candidate_json": audit.get("candidate") or {},
            "verification_json": verification,
            "reasoner_json": {
                "status": audit.get("reasoner_status"),
                "confidence": audit.get("reasoner_confidence"),
                "output": audit.get("reasoner_output"),
            },
            "provenance": ["cpg_mining", "path_miner", "deterministic_verifier"],
            "summary_json": {
                "outcome": verification.get("outcome"),
                "caveats": verification.get("caveats") or [],
            },
            "surfaced_at": datetime.now(UTC).isoformat() if surfaced else None,
        }
        inserted = (
            sb.table("findings")
            .upsert(finding_payload, on_conflict="analysis_id,finding_key")
            .execute()
        )
        finding_id = (inserted.data or [{}])[0].get("id")
        if not finding_id:
            continue
        checks = list(verification.get("checks") or [])
        sb.table("verifier_audits").insert(
            {
                "analysis_id": analysis_id,
                "repo_id": repo_id,
                "finding_id": finding_id,
                "checks_run_json": checks,
                "passed_checks_json": [c for c in checks if c.get("passed")],
                "failed_checks_json": [c for c in checks if not c.get("passed")],
                "graph_artifact_ids": graph_artifact_ids,
                "audit_json": audit,
            }
        ).execute()
    sb.table("pr_analyses").update(
        {
            "verified_count": verified,
            "withheld_count": withheld,
        }
    ).eq("id", analysis_id).execute()
    return {"verified": verified, "withheld": withheld}


def coerce_json_text(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
