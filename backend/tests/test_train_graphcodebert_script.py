from __future__ import annotations

import json
from pathlib import Path

from scripts.train_graphcodebert import GraphCodeBERTDataset, load_examples


def test_load_examples_reads_training_jsonl(tmp_path: Path) -> None:
    data_path = tmp_path / "train.jsonl"
    rows = [
        {
            "example_id": "cand:1",
            "label": 1,
            "label_text": "high_priority",
            "input_text": "invariant: schema_entity_still_referenced",
            "metadata": {"bucket": "top_promotions"},
        },
        {
            "example_id": "cand:2",
            "label": 0,
            "label_text": "low_priority",
            "input_text": "invariant: celery_task_binding",
            "metadata": {"bucket": "top_promotions"},
        },
    ]
    data_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    examples = load_examples(data_path)
    dataset = GraphCodeBERTDataset(examples)

    assert len(examples) == 2
    assert len(dataset) == 2
    assert dataset[0].example_id == "cand:1"
    assert dataset[1].label == 0
