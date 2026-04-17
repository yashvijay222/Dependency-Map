from __future__ import annotations

import json
from pathlib import Path

from cpg_builder.prepare_reasoner_dataset import run_prepare_reasoner_dataset


def test_run_prepare_reasoner_dataset_split(tmp_path: Path) -> None:
    inp = tmp_path / "in.jsonl"
    rows = [
        {"review_label": "better", "id": i}
        for i in range(10)
    ]
    inp.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    summary = run_prepare_reasoner_dataset(inp, tmp_path / "out", val_ratio=0.2, seed=1)
    assert summary["total"] == 10
    assert summary["train"] + summary["val"] == 10
    assert (tmp_path / "out" / "reasoner-train.jsonl").is_file()
