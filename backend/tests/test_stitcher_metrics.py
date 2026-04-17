from __future__ import annotations

from cpg_builder.stitcher import StitcherMetrics


def test_stitcher_metrics_as_dict_covers_rates() -> None:
    m = StitcherMetrics(
        route_count=10,
        routes_with_frontend_edges=5,
        schema_touching_handlers=4,
        schema_linked_handlers=2,
        async_producers=3,
        linked_async_producers=1,
        missing_route_bindings=1,
        missing_task_bindings=0,
        low_stitcher_coverage=True,
        missing_seam_categories=["frontend_route"],
    )
    d = m.as_dict()
    assert d["route_coverage"] == 0.5
    assert d["schema_coverage"] == 0.5
    assert round(d["async_coverage"], 4) == round(1 / 3, 4)
    assert d["low_stitcher_coverage"] is True
    assert d["missing_seam_categories"] == ["frontend_route"]
