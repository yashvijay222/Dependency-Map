from __future__ import annotations

from cpg_builder.reasoner_providers import validate_reasoner_json


def test_validate_reasoner_json_ok() -> None:
    data = {
        "violation": True,
        "confidence": 0.7,
        "invariant_id": "frontend_route_binding",
        "witness_paths": [],
        "broken_contract": {},
        "missing_guard": False,
        "affected_surfaces": [],
        "explanation": "x",
        "recommended_fix": "y",
    }
    ok, err = validate_reasoner_json(data)
    assert ok and err == ""


def test_validate_reasoner_json_missing_key() -> None:
    data = {"violation": True}
    ok, err = validate_reasoner_json(data)
    assert not ok
    assert "Missing keys" in err
