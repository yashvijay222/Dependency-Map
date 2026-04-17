"""OpenAPI path lines are stitched as synthetic routes (Phase 4A)."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from cpg_builder.schema import FileRecord, RepoIndex
from cpg_builder.stitcher import (
    NodeAccumulator,
    _parse_openapi_yaml_routes,
    stitch_repository_graph,
)


def test_parse_openapi_yaml_routes_extracts_paths() -> None:
    yaml = """
openapi: 3.0.0
paths:
  /api/v1/widgets:
    get:
      summary: List
  /api/v1/widgets/{id}:
    get:
      summary: Get
"""
    nodes = NodeAccumulator()
    routes = _parse_openapi_yaml_routes("openapi/openapi.yaml", yaml, nodes)
    patterns = {r.route_pattern for r in routes}
    assert "/api/v1/widgets" in patterns
    assert "/api/v1/widgets/{id}" in patterns


def test_stitch_repository_graph_includes_openapi_routes(tmp_path: Path) -> None:
    """Minimal repo index with one OpenAPI yaml file."""
    openapi = tmp_path / "docs" / "openapi.yaml"
    openapi.parent.mkdir(parents=True)
    openapi.write_text(
        "openapi: 3.0.0\npaths:\n  /v1/ping:\n    get: {}\n",
        encoding="utf-8",
    )
    raw = openapi.read_bytes()
    files = [
        FileRecord(
            path=openapi,
            repo_root=tmp_path,
            language="yaml",
            sha256=hashlib.sha256(raw).hexdigest(),
            size=len(raw),
            last_modified=time.time(),
        ),
    ]
    idx = RepoIndex(repo_root=tmp_path, repo_id="test", files=files, directories=[], packages=[])
    nodes, _edges, metrics = stitch_repository_graph(idx, [])
    assert int(metrics.get("route_count", 0)) >= 1
    assert any(
        str(getattr(n, "properties", {}) or {}).find("openapi") >= 0
        or getattr(n, "properties", {}).get("source_system") == "openapi"
        for n in nodes
    )
