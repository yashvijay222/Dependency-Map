from __future__ import annotations

from fastapi.testclient import TestClient

from app.deps import get_supabase_admin, verify_user_or_api_key
from app.main import app

R1 = "00000000-0000-0000-0000-000000000101"
O1 = "00000000-0000-0000-0000-000000000201"
A1 = "00000000-0000-0000-0000-000000000301"
P1 = "00000000-0000-0000-0000-000000000401"


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
            "repositories": [{"id": R1, "org_id": O1}],
            "pr_analyses": [{"id": A1, "repo_id": R1, "org_id": O1}],
            "analysis_plans": [
                {
                    "id": P1,
                    "run_id": A1,
                    "repo_id": R1,
                    "plan_type": "gated_pr_risk_v1",
                    "analysis_mode": "standard",
                    "task_graph_json": {"nodes": [{"id": "surface", "status": "completed"}]},
                }
            ],
        }

    def table(self, name: str):
        return _FakeQuery(list(self.tables.get(name, [])))


def test_get_analysis_plan_route() -> None:
    app.dependency_overrides[verify_user_or_api_key] = lambda: {"auth": "api_key", "org_id": O1}
    app.dependency_overrides[get_supabase_admin] = lambda: _FakeSupabase()
    client = TestClient(app)

    response = client.get(f"/v1/repos/{R1}/analyses/{A1}/plan")

    assert response.status_code == 200
    assert response.json()["plan_type"] == "gated_pr_risk_v1"

    app.dependency_overrides.clear()
