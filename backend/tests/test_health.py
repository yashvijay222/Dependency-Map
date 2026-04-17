from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_metrics() -> None:
    r = client.get("/health/metrics")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "counters" in data
