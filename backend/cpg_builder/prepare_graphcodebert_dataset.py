from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .utils import stable_id


def prepare_graphcodebert_dataset(
    labels_path: Path,
    out_dir: Path,
    *,
    val_ratio: float = 0.2,
) -> dict[str, Any]:
    labels = _load_jsonl(labels_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    examples = []
    skipped_unclear = 0
    skipped_unusable = 0
    for row in labels:
        example = _to_training_example(row)
        if example is None:
            if str(row.get("review_label") or "") == "unclear":
                skipped_unclear += 1
            else:
                skipped_unusable += 1
            continue
        examples.append(example)

    train_rows, val_rows = _split_examples(examples, val_ratio=val_ratio)
    train_path = out_dir / "graphcodebert-train.jsonl"
    val_path = out_dir / "graphcodebert-val.jsonl"
    summary_path = out_dir / "graphcodebert-dataset-summary.json"

    _write_jsonl(train_path, train_rows)
    _write_jsonl(val_path, val_rows)

    summary = {
        "source_labels": str(labels_path.resolve()),
        "train_out": str(train_path.resolve()),
        "val_out": str(val_path.resolve()),
        "total_rows": len(labels),
        "usable_rows": len(examples),
        "train_rows": len(train_rows),
        "val_rows": len(val_rows),
        "positive_rows": sum(1 for item in examples if int(item["label"]) == 1),
        "negative_rows": sum(1 for item in examples if int(item["label"]) == 0),
        "skipped_unclear": skipped_unclear,
        "skipped_unusable": skipped_unusable,
        "val_ratio": val_ratio,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _to_training_example(row: dict[str, Any]) -> dict[str, Any] | None:
    review_label = str(row.get("review_label") or "").strip().lower()
    if review_label == "unclear":
        return None

    bucket = str(row.get("bucket") or "")
    preferred_high_priority = _preferred_high_priority(bucket, review_label)
    if preferred_high_priority is None:
        return None

    candidate = row.get("graphcodebert_candidate") or row.get("heuristic_candidate") or {}
    finding_id = str(row.get("example_id") or candidate.get("finding_id") or "")
    if not finding_id:
        return None

    serialized = _serialize_candidate_for_training(row, candidate)
    return {
        "example_id": finding_id,
        "label": 1 if preferred_high_priority else 0,
        "label_text": "high_priority" if preferred_high_priority else "low_priority",
        "label_source": "reviewed_ranker_labels",
        "label_strength": "hard",
        "input_text": serialized,
        "metadata": {
            "bucket": bucket,
            "review_label": review_label,
            "invariant_id": row.get("invariant_id"),
            "heuristic_rank": row.get("heuristic_rank"),
            "graphcodebert_rank": row.get("graphcodebert_rank"),
            "rank_delta": row.get("rank_delta"),
            "heuristic_outcome": row.get("heuristic_outcome"),
            "graphcodebert_outcome": row.get("graphcodebert_outcome"),
            "seam_type": candidate.get("seam_type"),
            "severity": candidate.get("severity"),
            "verification_outcome": candidate.get("verification_outcome"),
        },
    }


def _preferred_high_priority(bucket: str, review_label: str) -> bool | None:
    if bucket == "top_promotions":
        if review_label in {"better", "expected_better"}:
            return True
        if review_label in {"worse", "noisy_promotion"}:
            return False
    if bucket == "top_drops":
        if review_label == "worse":
            return True
        if review_label in {"better", "expected_better", "noisy_promotion"}:
            return False
    return None


def _serialize_candidate_for_training(
    row: dict[str, Any],
    candidate: dict[str, Any],
) -> str:
    facts = candidate.get("facts") or {}
    caveats = candidate.get("verification_caveats") or []
    facts_str = ", ".join(f"{key}={facts[key]!r}" for key in sorted(facts.keys())) or "none"
    caveats_str = ", ".join(str(item) for item in caveats) or "none"
    return "\n".join(
        [
            f"invariant: {row.get('invariant_id')}",
            f"bucket: {row.get('bucket')}",
            f"heuristic_rank: {row.get('heuristic_rank')}",
            f"graphcodebert_rank: {row.get('graphcodebert_rank')}",
            f"rank_delta: {row.get('rank_delta')}",
            f"heuristic_outcome: {row.get('heuristic_outcome')}",
            f"graphcodebert_outcome: {row.get('graphcodebert_outcome')}",
            f"severity: {candidate.get('severity')}",
            f"seam_type: {candidate.get('seam_type')}",
            f"verification_outcome: {candidate.get('verification_outcome')}",
            f"verification_caveats: {caveats_str}",
            f"facts: {facts_str}",
            f"review_notes: {row.get('review_notes') or ''}",
        ]
    )


def _split_examples(
    examples: list[dict[str, Any]],
    *,
    val_ratio: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train_rows: list[dict[str, Any]] = []
    val_rows: list[dict[str, Any]] = []
    threshold = max(0, min(100, int(round(val_ratio * 100))))
    for example in sorted(examples, key=lambda item: str(item["example_id"])):
        bucket = _bucket_for_split(str(example["example_id"]))
        if bucket < threshold:
            val_rows.append(example)
        else:
            train_rows.append(example)
    return train_rows, val_rows


def _bucket_for_split(example_id: str) -> int:
    token = stable_id("graphcodebert-split", example_id)
    return int(token[:8], 16) % 100


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
