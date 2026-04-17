"""Contract-style tests for stable API response shapes (Phase 0)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.deps import get_supabase_admin, verify_user_or_api_key
from app.main import app

R1 = "00000000-0000-0000-0000-000000000101"
O1 = "00000000-0000-0000-0000-000000000201"
A1 = "00000000-0000-0000-0000-000000000301"
F1 = "00000000-0000-0000-0000-000000000401"


class _FakeQuery:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.filters: dict[str, str] = {}

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key: str, value: str):
        self.filters[key] = value
        return self

    def limit(self, _value: int):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        filtered = self.rows
        for key, value in self.filters.items():
            filtered = [row for row in filtered if str(row.get(key)) == value]
        return type("Result", (), {"data": filtered})()


class _FakeSupabaseAnalysis:
    def __init__(self):
        self.tables = {
            "repositories": [{"id": R1, "org_id": O1}],
            "pr_analyses": [
                {
                    "id": A1,
                    "repo_id": R1,
                    "status": "completed",
                    "outcome": "completed_ok",
                    "base_sha": "abc",
                    "head_sha": "def",
                    "summary_json": {
                        "cpg_status": {"mode": "ran", "reason": "ok"},
                        "cpg_candidate_count": 1,
                        "cpg_surfaced_count": 0,
                    },
                    "mode": "standard",
                }
            ],
        }

    def table(self, name: str):
        return _FakeQuery(list(self.tables.get(name, [])))


def test_get_analysis_contract_includes_cpg_summary_keys() -> None:
    app.dependency_overrides[verify_user_or_api_key] = lambda: {"auth": "api_key", "org_id": O1}
    app.dependency_overrides[get_supabase_admin] = lambda: _FakeSupabaseAnalysis()
    client = TestClient(app)
    res = client.get(f"/v1/repos/{R1}/analyses/{A1}")
    assert res.status_code == 200
    body = res.json()
    assert "summary_json" in body
    summary = body["summary_json"]
    assert "cpg_status" in summary
    assert summary["cpg_status"]["mode"] == "ran"
    assert "cpg_candidate_count" in summary
    app.dependency_overrides.clear()


def test_health_metrics_contract() -> None:
    client = TestClient(app)
    res = client.get("/health/metrics")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "counters" in body
    assert isinstance(body["counters"], dict)


class _FakeSupabaseFindings(_FakeSupabaseAnalysis):
    def __init__(self) -> None:
        super().__init__()
        self.tables["findings"] = [
            {
                "id": F1,
                "analysis_id": A1,
                "repo_id": R1,
                "created_at": "2026-01-01T00:00:00Z",
                "finding_key": "fk1",
                "invariant_id": "frontend_route_binding",
                "severity": "high",
                "status": "verified",
                "withhold_reason": None,
                "rank_score": 0.9,
                "rank_phase": "heuristic",
                "candidate_json": {"facts": {"file_path": "app/page.tsx"}},
                "verification_json": {"outcome": "verified", "surfaced": True},
                "reasoner_json": {},
                "summary_json": {"caveats": []},
            },
        ]


def test_get_findings_contract_includes_presented() -> None:
    app.dependency_overrides[verify_user_or_api_key] = lambda: {"auth": "api_key", "org_id": O1}
    app.dependency_overrides[get_supabase_admin] = lambda: _FakeSupabaseFindings()
    client = TestClient(app)
    res = client.get(f"/v1/repos/{R1}/analyses/{A1}/findings")
    assert res.status_code == 200
    body = res.json()
    assert "presented" in body
    assert isinstance(body["presented"], list)
    assert body["presented"][0]["title"]
    assert body["presented"][0]["file_anchors"]
    app.dependency_overrides.clear()


def test_get_finding_by_id_contract_includes_presented() -> None:
    app.dependency_overrides[verify_user_or_api_key] = lambda: {"auth": "api_key", "org_id": O1}
    app.dependency_overrides[get_supabase_admin] = lambda: _FakeSupabaseFindings()
    client = TestClient(app)
    res = client.get(f"/v1/repos/{R1}/findings/{F1}")
    assert res.status_code == 200
    body = res.json()
    assert "finding" in body
    assert body["finding"]["id"] == F1
    assert "presented" in body
    assert isinstance(body["presented"], dict)
    assert body["presented"]["title"]
    assert isinstance(body["presented"].get("file_anchors"), list)
    app.dependency_overrides.clear()


def test_get_repository_contract() -> None:
    class _RepoOnly:
        tables = {
            "repositories": [
                {
                    "id": R1,
                    "org_id": O1,
                    "full_name": "acme/demo",
                    "default_branch": "main",
                    "github_repo_id": 99,
                },
            ],
        }

        def table(self, name: str):
            return _FakeQuery(list(self.tables.get(name, [])))

    app.dependency_overrides[verify_user_or_api_key] = lambda: {"auth": "api_key", "org_id": O1}
    app.dependency_overrides[get_supabase_admin] = lambda: _RepoOnly()
    client = TestClient(app)
    res = client.get(f"/v1/repos/{R1}")
    assert res.status_code == 200
    repo = res.json()["repository"]
    assert repo["full_name"] == "acme/demo"
    assert repo["org_id"] == O1
    app.dependency_overrides.clear()
