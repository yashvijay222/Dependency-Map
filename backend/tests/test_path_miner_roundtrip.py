from __future__ import annotations

from cpg_builder.path_miner import (
    CandidatePath,
    deserialize_candidate_path,
    serialize_candidate_path,
)


def test_serialize_deserialize_candidate_roundtrip() -> None:
    original = CandidatePath(
        id="c1",
        invariant_id="celery_task_binding",
        seed_id="s1",
        node_ids=["a", "b"],
        edge_ids=["e1"],
        seam_type="async",
        changed_anchors=["x"],
        heuristic_features={"k": 1},
        facts={"target_unresolved": True},
    )
    blob = serialize_candidate_path(original)
    restored = deserialize_candidate_path(blob)
    assert restored == original
