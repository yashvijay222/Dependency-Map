"""Split CPG_REASONER_TRAINING_JSONL-style rows into train/val JSONL files."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def split_rows(
    rows: list[dict[str, Any]],
    *,
    val_ratio: float,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    indices = list(range(len(rows)))
    rng.shuffle(indices)
    val_count = max(1, int(len(rows) * val_ratio)) if len(rows) > 1 else 0
    val_set = set(indices[:val_count])
    train = [rows[i] for i in range(len(rows)) if i not in val_set]
    val = [rows[i] for i in range(len(rows)) if i in val_set]
    return train, val


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, default=str) + "\n" for r in rows), encoding="utf-8")


def run_prepare_reasoner_dataset(
    input_path: Path,
    out_dir: Path,
    *,
    val_ratio: float = 0.2,
    seed: int = 42,
) -> dict[str, Any]:
    inp = input_path.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = load_rows(inp)
    if not rows:
        raise ValueError("No rows found in input JSONL")
    train, val = split_rows(rows, val_ratio=val_ratio, seed=seed)
    write_jsonl(out_dir / "reasoner-train.jsonl", train)
    write_jsonl(out_dir / "reasoner-val.jsonl", val)
    summary: dict[str, Any] = {
        "total": len(rows),
        "train": len(train),
        "val": len(val),
        "input": str(inp),
    }
    (out_dir / "reasoner-dataset-summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare reasoner fine-tuning split from JSONL")
    parser.add_argument("--input", required=True, help="Path to reasoner training JSONL")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    ns = parser.parse_args(argv)
    try:
        summary = run_prepare_reasoner_dataset(
            Path(ns.input),
            Path(ns.out_dir),
            val_ratio=float(ns.val_ratio),
            seed=int(ns.seed),
        )
    except ValueError as exc:
        print(str(exc))
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
