from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .scorer import ScoreArtifacts, score_repository


@contextmanager
def _temporary_env(key: str, value: str) -> Iterator[None]:
    previous = os.environ.get(key)
    os.environ[key] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


def compare_ranker_runs(
    repo_root: Path,
    out_dir: Path,
    *,
    base: str | None = None,
    head: str | None = None,
    cpg_json: Path | None = None,
    diff_json: Path | None = None,
    top_k: int = 20,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    heuristic_dir = out_dir / "heuristic"
    graphcodebert_dir = out_dir / "graphcodebert"

    with _temporary_env("CPG_RANKER_BACKEND", "heuristic"):
        heuristic = score_repository(
            repo_root,
            heuristic_dir,
            base=base,
            head=head,
            cpg_json=cpg_json,
            diff_json=diff_json,
        )
    with _temporary_env("CPG_RANKER_BACKEND", "graphcodebert"):
        graphcodebert = score_repository(
            repo_root,
            graphcodebert_dir,
            base=base,
            head=head,
            cpg_json=cpg_json,
            diff_json=diff_json,
        )

    comparison = _build_comparison_payload(heuristic, graphcodebert, top_k=top_k)
    (out_dir / "ranker-comparison.json").write_text(
        json.dumps(comparison, indent=2),
        encoding="utf-8",
    )
    (out_dir / "ranker-comparison.md").write_text(
        _render_comparison_report(comparison),
        encoding="utf-8",
    )
    return comparison


def _build_comparison_payload(
    heuristic: ScoreArtifacts,
    graphcodebert: ScoreArtifacts,
    *,
    top_k: int,
) -> dict[str, Any]:
    heuristic_ranked = _index_ranker_examples(heuristic.ranker_examples)
    graph_ranked = _index_ranker_examples(graphcodebert.ranker_examples)
    heuristic_outcomes = _index_verifier_outcomes(heuristic.verifier_audit)
    graph_outcomes = _index_verifier_outcomes(graphcodebert.verifier_audit)

    shared_ids = sorted(set(heuristic_ranked) & set(graph_ranked))
    moved = []
    for example_id in shared_ids:
        heuristic_item = heuristic_ranked[example_id]
        graph_item = graph_ranked[example_id]
        heuristic_rank = int(heuristic_item["rank"])
        graph_rank = int(graph_item["rank"])
        delta = heuristic_rank - graph_rank
        moved.append(
            {
                "example_id": example_id,
                "invariant_id": graph_item["invariant_id"],
                "heuristic_rank": heuristic_rank,
                "graphcodebert_rank": graph_rank,
                "rank_delta": delta,
                "heuristic_score": heuristic_item["score"],
                "graphcodebert_score": graph_item["score"],
                "heuristic_phase": heuristic_item["phase"],
                "graphcodebert_phase": graph_item["phase"],
                "heuristic_outcome": heuristic_outcomes.get(example_id),
                "graphcodebert_outcome": graph_outcomes.get(example_id),
            }
        )

    upward = sorted(moved, key=lambda item: (-item["rank_delta"], item["graphcodebert_rank"]))
    downward = sorted(moved, key=lambda item: (item["rank_delta"], item["graphcodebert_rank"]))
    summary = {
        "heuristic": {
            "run_id": heuristic.run_id,
            "candidate_count": heuristic.run_metadata["candidate_count"],
            "surfaced_count": heuristic.run_metadata["surfaced_count"],
        },
        "graphcodebert": {
            "run_id": graphcodebert.run_id,
            "candidate_count": graphcodebert.run_metadata["candidate_count"],
            "surfaced_count": graphcodebert.run_metadata["surfaced_count"],
        },
        "shared_candidates": len(shared_ids),
        "top_k": top_k,
        "top_k_overlap": len(
            set(_top_ids(heuristic_ranked, top_k)) & set(_top_ids(graph_ranked, top_k))
        ),
    }
    return {
        "summary": summary,
        "top_promotions": upward[:top_k],
        "top_drops": downward[:top_k],
        "heuristic_top": _top_entries(heuristic_ranked, top_k),
        "graphcodebert_top": _top_entries(graph_ranked, top_k),
    }


def _index_ranker_examples(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for rank, row in enumerate(rows, start=1):
        score_breakdown = row.get("score_breakdown") or {}
        indexed[str(row["example_id"])] = {
            "example_id": row["example_id"],
            "invariant_id": row["invariant_id"],
            "rank": rank,
            "phase": row.get("rank_phase"),
            "score": score_breakdown.get("model_score", 0.0) + score_breakdown.get(
                "heuristic_score", 0.0
            ),
            "score_breakdown": score_breakdown,
        }
    return indexed


def _index_verifier_outcomes(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(row["finding_id"]): str((row.get("verification") or {}).get("outcome") or "")
        for row in rows
    }


def _top_ids(indexed: dict[str, dict[str, Any]], top_k: int) -> list[str]:
    top = sorted(indexed.values(), key=lambda item: int(item["rank"]))[:top_k]
    return [str(item["example_id"]) for item in top]


def _top_entries(indexed: dict[str, dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    top = sorted(indexed.values(), key=lambda item: int(item["rank"]))[:top_k]
    return [
        {
            "example_id": item["example_id"],
            "invariant_id": item["invariant_id"],
            "rank": item["rank"],
            "phase": item["phase"],
            "score_breakdown": item["score_breakdown"],
        }
        for item in top
    ]


def _render_comparison_report(comparison: dict[str, Any]) -> str:
    summary = comparison["summary"]
    lines = [
        "# Ranker Comparison",
        "",
        f"- Heuristic run: `{summary['heuristic']['run_id']}`",
        f"- GraphCodeBERT run: `{summary['graphcodebert']['run_id']}`",
        f"- Shared candidates: `{summary['shared_candidates']}`",
        f"- Top-{summary['top_k']} overlap: `{summary['top_k_overlap']}`",
        "",
        "## Top Promotions",
        "",
    ]
    for row in comparison["top_promotions"][:10]:
        lines.append(
            f"- `{row['example_id']}` moved from `{row['heuristic_rank']}` to "
            f"`{row['graphcodebert_rank']}` for `{row['invariant_id']}`"
        )
    lines.extend(["", "## Top Drops", ""])
    for row in comparison["top_drops"][:10]:
        lines.append(
            f"- `{row['example_id']}` moved from `{row['heuristic_rank']}` to "
            f"`{row['graphcodebert_rank']}` for `{row['invariant_id']}`"
        )
    lines.append("")
    return "\n".join(lines)
