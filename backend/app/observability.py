"""Structured logging and lightweight in-process metrics (Phase 0 foundations)."""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

log = logging.getLogger("dm.pipeline")

_counters: defaultdict[str, int] = defaultdict(int)


def increment_counter(name: str, value: int = 1) -> None:
    _counters[name] += value


def snapshot_counters() -> dict[str, int]:
    return dict(_counters)


def emit_pipeline_event(
    event: str,
    *,
    analysis_id: str | None = None,
    org_id: str | None = None,
    repo_id: str | None = None,
    task_id: str | None = None,
    duration_ms: float | None = None,
    github_request_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "dm_event": event,
        "analysis_id": analysis_id,
        "org_id": org_id,
        "repo_id": repo_id,
        "task_id": task_id,
        "duration_ms": duration_ms,
        "github_request_id": github_request_id,
    }
    if extra:
        payload.update(extra)
    # Drop null keys for cleaner logs
    payload = {k: v for k, v in payload.items() if v is not None}
    log.info("%s", json.dumps(payload, default=str))


@contextmanager
def timed_task(
    event_base: str,
    *,
    analysis_id: str | None = None,
    org_id: str | None = None,
    repo_id: str | None = None,
    task_id: str | None = None,
) -> Iterator[None]:
    start = time.perf_counter()
    emit_pipeline_event(
        f"{event_base}_started",
        analysis_id=analysis_id,
        org_id=org_id,
        repo_id=repo_id,
        task_id=task_id,
    )
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        emit_pipeline_event(
            f"{event_base}_finished",
            analysis_id=analysis_id,
            org_id=org_id,
            repo_id=repo_id,
            task_id=task_id,
            duration_ms=round(duration_ms, 2),
        )
