#!/usr/bin/env python3
"""Aggregate review labels from ranker-labels.jsonl (Phase 0 metrics).

Usage:
  uv run python scripts/aggregate_ranker_labels.py path/to/ranker-labels.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate ranker label counts from JSONL")
    parser.add_argument("labels_jsonl", type=Path, help="Path to ranker-labels.jsonl")
    ns = parser.parse_args()
    path: Path = ns.labels_jsonl
    if not path.is_file():
        print(f"Not a file: {path}", file=sys.stderr)
        return 1
    counts: dict[str, int] = {}
    total = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row: dict[str, Any] = json.loads(line)
            label = str(row.get("review_label") or "unclear").strip().lower() or "unclear"
            counts[label] = counts.get(label, 0) + 1
            total += 1
    better = counts.get("better", 0)
    worse = counts.get("worse", 0)
    unclear = counts.get("unclear", 0)
    net = better - worse
    denom = better + worse
    precision = (better / denom) if denom else 0.0
    unclear_rate = (unclear / total) if total else 0.0
    summary = {
        "total_reviewed": total,
        "counts": dict(sorted(counts.items())),
        "net_improvement": net,
        "review_precision": round(precision, 4),
        "unclear_rate": round(unclear_rate, 4),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
