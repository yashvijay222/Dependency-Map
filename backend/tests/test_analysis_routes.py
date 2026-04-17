from __future__ import annotations

from fastapi.testclient import TestClient

from app.deps import get_supabase_admin, verify_user_or_api_key
from app.main import app


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


class _FakeSupabase:
    def __init__(self):
        self.tables = {
            "repositories": [{"id": "00000000-0000-0000-0000-000000000101", "org_id": "00000000-0000-0000-0000-000000000201"}],
            "pr_analyses": [{"id": "00000000-0000-0000-0000-000000000301", "repo_id": "00000000-0000-0000-0000-000000000101", "org_id": "00000000-0000-0000-0000-000000000201"}],
            "analysis_plans": [
                {
                    "id": "00000000-0000-0000-0000-000000000401",
                    "run_id": "00000000-0000-0000-0000-000000000301",
                    "repo_id": "00000000-0000-0000-0000-000000000101",
                    "plan_type": "gated_pr_risk_v1",
                    "analysis_mode": "standard",
                    "task_graph_json": {"nodes": [{"id": "surface", "status": "completed"}]},
                }
            ],
        }

    def table(self, name: str):
        return _FakeQuery(list(self.tables.get(name, [])))


def test_get_analysis_plan_route() -> None:
    app.dependency_overrides[verify_user_or_api_key] = lambda: {"auth": "api_key", "org_id": "00000000-0000-0000-0000-000000000201"}
    app.dependency_overrides[get_supabase_admin] = lambda: _FakeSupabase()
    client = TestClient(app)

    response = client.get(
        "/v1/repos/00000000-0000-0000-0000-000000000101/analyses/00000000-0000-0000-0000-000000000301/plan"
    )

    assert response.status_code == 200
    assert response.json()["plan_type"] == "gated_pr_risk_v1"

    app.dependency_overrides.clear()
