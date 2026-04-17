from app.services.analysis_planner import (
    BACKEND_ROUTERS_STITCH_GLOB_DEFAULT,
    FRONTEND_STITCH_GLOB_DEFAULT,
    build_analysis_plan,
)


def test_analysis_planner_enables_stitch_and_schema_paths() -> None:
    plan = build_analysis_plan(
        [
            "frontend/app/dashboard/page.tsx",
            "backend/app/routers/orgs.py",
            "supabase/migrations/20260417000000_gated_analysis.sql",
        ],
        org_settings={"async_checks_enabled": True},
    )

    node_ids = {node["id"] for node in plan["task_graph"]["nodes"]}

    assert FRONTEND_STITCH_GLOB_DEFAULT == "frontend/app/**"
    assert BACKEND_ROUTERS_STITCH_GLOB_DEFAULT == "backend/app/routers/**"
    assert plan["analysis_mode"] == "standard"
    assert "frontend_backend_stitch" in node_ids
    assert "schema_extraction" in node_ids
    assert "route_binding_verifier" in node_ids
    assert plan["reason_json"]["migration_files_changed"] is True


def test_analysis_planner_uses_focused_scan_for_small_non_migration_diff() -> None:
    plan = build_analysis_plan(
        ["frontend/app/dashboard/page.tsx", "frontend/app/layout.tsx"],
        org_settings={"focused_contract_scan_max_changed_files": 5},
    )

    assert plan["analysis_mode"] == "focused_contract_scan"
    assert any(
        row["task_id"] == "route_extraction" for row in plan["disabled_subtasks"]
    )
