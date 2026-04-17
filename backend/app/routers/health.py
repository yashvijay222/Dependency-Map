from fastapi import APIRouter

from app.observability import snapshot_counters

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/metrics")
def health_metrics() -> dict[str, object]:
    """Lightweight process counters for operators (Phase 0)."""
    return {"status": "ok", "counters": snapshot_counters()}
