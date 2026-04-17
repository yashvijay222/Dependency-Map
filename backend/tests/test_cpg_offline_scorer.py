from __future__ import annotations

import json
from pathlib import Path

import pytest

from cpg_builder.compare_rankers import compare_ranker_runs
from cpg_builder.fusion import build_cpg
from cpg_builder.invariants import default_invariants
from cpg_builder.label_ranker_results import generate_ranker_label_file
from cpg_builder.path_miner import CandidatePath
from cpg_builder.prepare_graphcodebert_dataset import prepare_graphcodebert_dataset
from cpg_builder.ranker import rank_candidates, serialize_candidate
from cpg_builder.schema import EdgeLabel, NodeLabel
from cpg_builder.scorer import score_repository


@pytest.fixture(autouse=True)
def _heuristic_ranker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CPG_RANKER_BACKEND", "heuristic")


def test_build_cpg_stitches_frontend_route_and_schema(tmp_path: Path) -> None:
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "page.tsx").write_text(
        'async function load() { return apiFetchOptional("/v1/orgs/123/repositories"); }\n',
        encoding="utf-8",
    )
    (tmp_path / "backend" / "app" / "routers").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "routers" / "orgs.py").write_text(
        "from fastapi import APIRouter, Depends\n"
        "from app.deps import verify_user_or_api_key, get_supabase_admin\n"
        'router = APIRouter(prefix="/v1/orgs")\n'
        '@router.get("/{org_id}/repositories")\n'
        "def list_org_repositories(\n"
        "    actor=Depends(verify_user_or_api_key),\n"
        "    supabase=Depends(get_supabase_admin),\n"
        "):\n"
        '    return supabase.table("repositories").select("*").execute()\n',
        encoding="utf-8",
    )
    (tmp_path / "supabase" / "migrations").mkdir(parents=True)
    (tmp_path / "supabase" / "migrations" / "20250101000000_initial.sql").write_text(
        "create table public.repositories (\n"
        "  id uuid primary key,\n"
        "  org_id uuid not null\n"
        ");\n"
        'create policy "Members see repos"\n'
        "  on public.repositories for select\n"
        "  using (auth.uid() is not null);\n",
        encoding="utf-8",
    )

    graph, artifacts = build_cpg(tmp_path)
    edge_labels = {edge.label for edge in artifacts.edges}
    node_labels = {node.label for node in artifacts.nodes}

    assert NodeLabel.ROUTE in node_labels
    assert NodeLabel.HTTP_CLIENT_CALL in node_labels
    assert NodeLabel.DATABASE_ENTITY in node_labels
    assert NodeLabel.RLS_POLICY in node_labels
    assert EdgeLabel.HTTP_CALLS_ROUTE in edge_labels
    assert EdgeLabel.ROUTE_READS_TABLE in edge_labels
    assert EdgeLabel.ROUTE_GUARDED_BY_RLS in edge_labels
    assert not artifacts.summaries["stitcher_metrics"]["low_stitcher_coverage"]
    assert graph.number_of_nodes() == len(artifacts.nodes)


def test_score_repository_emits_schema_violation_for_missing_table(tmp_path: Path) -> None:
    (tmp_path / "backend" / "app" / "routers").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "routers" / "orgs.py").write_text(
        "from fastapi import APIRouter, Depends\n"
        "from app.deps import get_supabase_admin\n"
        'router = APIRouter(prefix="/v1/orgs")\n'
        '@router.get("/{org_id}/repositories")\n'
        "def list_org_repositories(supabase=Depends(get_supabase_admin)):\n"
        '    return supabase.table("organization_members").select("*").execute()\n',
        encoding="utf-8",
    )
    (tmp_path / "supabase" / "migrations").mkdir(parents=True)
    (tmp_path / "supabase" / "migrations" / "20250101000000_initial.sql").write_text(
        "create table public.repositories (\n  id uuid primary key\n);\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    artifacts = score_repository(tmp_path, out_dir)

    violations = json.loads((out_dir / "violations.json").read_text(encoding="utf-8"))
    audit = json.loads((out_dir / "verifier_audit.json").read_text(encoding="utf-8"))

    assert artifacts.violations
    assert any(
        finding["invariant_id"] == "schema_entity_still_referenced"
        for finding in violations["violations"]
    )
    assert any(
        finding["verification"]["outcome"] in {"confirmed", "partially_confirmed"}
        for finding in audit["audit"]
        if finding["invariant_id"] == "schema_entity_still_referenced"
    )


def test_rank_candidates_uses_graphcodebert_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CPG_RANKER_BACKEND", "graphcodebert")
    monkeypatch.setattr("cpg_builder.ranker._build_graphcodebert_ranker", lambda: _StubRanker())
    candidate = CandidatePath(
        id="cand:test",
        invariant_id="schema_entity_still_referenced",
        seed_id="db:1",
        node_ids=["route:1", "db:1"],
        edge_ids=["edge:1"],
        seam_type="schema",
        changed_anchors=["db:1"],
        heuristic_features={"changed_anchor_count": 1},
        facts={
            "entity_name": "organization_members",
            "defined_in_migration": False,
            "referenced_in_code": True,
        },
    )

    ranked = rank_candidates([candidate], {spec.id: spec for spec in default_invariants()})

    assert ranked[0].phase == "phase0_graphcodebert_blend"
    assert ranked[0].label_source == "graphcodebert_inference"
    assert ranked[0].score_breakdown["model_score"] == 0.9


def test_serialize_candidate_is_deterministic() -> None:
    candidate = CandidatePath(
        id="cand:test",
        invariant_id="frontend_route_binding",
        seed_id="http:1",
        node_ids=["http:1", "route:1"],
        edge_ids=["edge:1"],
        seam_type="http",
        changed_anchors=[],
        heuristic_features={"matched_route": True, "changed_anchor_count": 0},
        facts={"matched_route_id": "route:1", "route_pattern": "/v1/dashboard"},
    )

    serialized_a = serialize_candidate(candidate)
    serialized_b = serialize_candidate(candidate)

    assert serialized_a == serialized_b
    assert "invariant: frontend_route_binding" in serialized_a
    assert "path_nodes: http:1 -> route:1" in serialized_a


class _StubRanker:
    available = True

    def score(self, candidate: CandidatePath, spec: object | None = None) -> float:
        return 0.9


def test_compare_ranker_runs_writes_comparison_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "backend" / "app" / "routers").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "routers" / "orgs.py").write_text(
        "from fastapi import APIRouter, Depends\n"
        "from app.deps import get_supabase_admin\n"
        'router = APIRouter(prefix="/v1/orgs")\n'
        '@router.get("/{org_id}/repositories")\n'
        "def list_org_repositories(supabase=Depends(get_supabase_admin)):\n"
        '    return supabase.table("organization_members").select("*").execute()\n',
        encoding="utf-8",
    )
    (tmp_path / "supabase" / "migrations").mkdir(parents=True)
    (tmp_path / "supabase" / "migrations" / "20250101000000_initial.sql").write_text(
        "create table public.repositories (\n  id uuid primary key\n);\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("cpg_builder.ranker._build_graphcodebert_ranker", lambda: _StubRanker())

    comparison = compare_ranker_runs(tmp_path, tmp_path / "compare", top_k=5)

    assert comparison["summary"]["shared_candidates"] >= 1
    assert (tmp_path / "compare" / "ranker-comparison.json").exists()
    assert (tmp_path / "compare" / "ranker-comparison.md").exists()


def test_generate_ranker_label_file_writes_review_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "backend" / "app" / "routers").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "routers" / "orgs.py").write_text(
        "from fastapi import APIRouter, Depends\n"
        "from app.deps import get_supabase_admin\n"
        'router = APIRouter(prefix="/v1/orgs")\n'
        '@router.get("/{org_id}/repositories")\n'
        "def list_org_repositories(supabase=Depends(get_supabase_admin)):\n"
        '    return supabase.table("organization_members").select("*").execute()\n',
        encoding="utf-8",
    )
    (tmp_path / "supabase" / "migrations").mkdir(parents=True)
    (tmp_path / "supabase" / "migrations" / "20250101000000_initial.sql").write_text(
        "create table public.repositories (\n  id uuid primary key\n);\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("cpg_builder.ranker._build_graphcodebert_ranker", lambda: _StubRanker())

    compare_ranker_runs(tmp_path, tmp_path / "compare", top_k=5)
    result = generate_ranker_label_file(tmp_path / "compare", limit=3)

    label_path = Path(result["out"])
    rows = [
        json.loads(line)
        for line in label_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert result["count"] >= 1
    assert label_path.exists()
    assert all("review_label" in row for row in rows)
    assert all("heuristic_candidate" in row for row in rows)


def test_prepare_graphcodebert_dataset_filters_unclear_and_splits(
    tmp_path: Path,
) -> None:
    labels_path = tmp_path / "ranker-labels.jsonl"
    rows = [
        {
            "example_id": "cand:one",
            "bucket": "top_promotions",
            "review_label": "expected_better",
            "review_notes": "Strong confirmed promotion.",
            "invariant_id": "schema_entity_still_referenced",
            "heuristic_rank": 20,
            "graphcodebert_rank": 5,
            "rank_delta": 15,
            "heuristic_outcome": "confirmed",
            "graphcodebert_outcome": "confirmed",
            "graphcodebert_candidate": {
                "severity": "high",
                "seam_type": "schema",
                "verification_outcome": "confirmed",
                "verification_caveats": [],
                "facts": {"entity_name": "organization_members"},
            },
        },
        {
            "example_id": "cand:two",
            "bucket": "top_promotions",
            "review_label": "noisy_promotion",
            "review_notes": "Unconfirmed noisy promotion.",
            "invariant_id": "schema_entity_still_referenced",
            "heuristic_rank": 40,
            "graphcodebert_rank": 8,
            "rank_delta": 32,
            "heuristic_outcome": "unconfirmed",
            "graphcodebert_outcome": "unconfirmed",
            "graphcodebert_candidate": {
                "severity": "high",
                "seam_type": "schema",
                "verification_outcome": "unconfirmed",
                "verification_caveats": [],
                "facts": {"entity_name": "repositories"},
            },
        },
        {
            "example_id": "cand:three",
            "bucket": "top_promotions",
            "review_label": "unclear",
            "review_notes": "Still ambiguous.",
            "invariant_id": "celery_task_binding",
            "heuristic_rank": 50,
            "graphcodebert_rank": 30,
            "rank_delta": 20,
            "heuristic_outcome": "unconfirmed",
            "graphcodebert_outcome": "unconfirmed",
            "graphcodebert_candidate": {
                "severity": "medium",
                "seam_type": "worker",
                "verification_outcome": "unconfirmed",
                "verification_caveats": [],
                "facts": {"task_name": "dm.build_org_graph"},
            },
        },
    ]
    labels_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    summary = prepare_graphcodebert_dataset(labels_path, tmp_path / "prepared", val_ratio=0.5)

    train_path = tmp_path / "prepared" / "graphcodebert-train.jsonl"
    val_path = tmp_path / "prepared" / "graphcodebert-val.jsonl"
    train_rows = [
        json.loads(line)
        for line in train_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    val_rows = [
        json.loads(line)
        for line in val_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert summary["usable_rows"] == 2
    assert summary["skipped_unclear"] == 1
    assert summary["positive_rows"] == 1
    assert summary["negative_rows"] == 1
    assert len(train_rows) + len(val_rows) == 2
    assert {row["label_text"] for row in train_rows + val_rows} == {
        "high_priority",
        "low_priority",
    }
