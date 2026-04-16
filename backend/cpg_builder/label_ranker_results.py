from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def generate_ranker_label_file(
    compare_dir: Path,
    out_path: Path | None = None,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    compare_dir = compare_dir.resolve()
    comparison = json.loads((compare_dir / "ranker-comparison.json").read_text(encoding="utf-8"))
    heuristic_audit = _load_audit(compare_dir / "heuristic" / "verifier_audit.json")
    graph_audit = _load_audit(compare_dir / "graphcodebert" / "verifier_audit.json")

    rows = _build_label_rows(comparison, heuristic_audit, graph_audit, limit=limit)
    destination = out_path.resolve() if out_path else compare_dir / "ranker-labels.jsonl"
    payload = "".join(json.dumps(row) + "\n" for row in rows)
    destination.write_text(payload, encoding="utf-8")
    return {
        "out": str(destination),
        "count": len(rows),
    }


def _load_audit(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(item["finding_id"]): item
        for item in payload.get("audit", [])
    }


def _build_label_rows(
    comparison: dict[str, Any],
    heuristic_audit: dict[str, dict[str, Any]],
    graph_audit: dict[str, dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket_name in ("top_promotions", "top_drops"):
        for item in comparison.get(bucket_name, [])[:limit]:
            example_id = str(item["example_id"])
            if example_id in seen:
                continue
            seen.add(example_id)
            rows.append(
                {
                    "example_id": example_id,
                    "bucket": bucket_name,
                    "review_label": None,
                    "review_notes": "",
                    "invariant_id": item["invariant_id"],
                    "heuristic_rank": item["heuristic_rank"],
                    "graphcodebert_rank": item["graphcodebert_rank"],
                    "rank_delta": item["rank_delta"],
                    "heuristic_score": item["heuristic_score"],
                    "graphcodebert_score": item["graphcodebert_score"],
                    "heuristic_outcome": item.get("heuristic_outcome"),
                    "graphcodebert_outcome": item.get("graphcodebert_outcome"),
                    "heuristic_candidate": _candidate_summary(heuristic_audit.get(example_id)),
                    "graphcodebert_candidate": _candidate_summary(graph_audit.get(example_id)),
                }
            )
    return rows


def _candidate_summary(audit_item: dict[str, Any] | None) -> dict[str, Any]:
    if not audit_item:
        return {}
    candidate = dict(audit_item.get("candidate") or {})
    verification = dict(audit_item.get("verification") or {})
    return {
        "finding_id": audit_item.get("finding_id"),
        "severity": audit_item.get("severity"),
        "rank_score": audit_item.get("rank_score"),
        "rank_phase": audit_item.get("rank_phase"),
        "reasoner_status": audit_item.get("reasoner_status"),
        "verification_outcome": verification.get("outcome"),
        "verification_caveats": verification.get("caveats") or [],
        "seam_type": candidate.get("seam_type"),
        "changed_anchors": candidate.get("changed_anchors") or [],
        "facts": candidate.get("facts") or {},
    }
