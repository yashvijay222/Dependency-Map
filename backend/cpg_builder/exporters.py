from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

import networkx as nx

from .schema import BuildArtifacts
from .utils import json_safe


def graph_payload(graph: nx.MultiDiGraph, artifacts: BuildArtifacts) -> dict[str, Any]:
    return {
        "summary": artifacts.summaries,
        "repo": {
            "path": str(artifacts.repo_index.repo_root),
            "git_ref": artifacts.repo_index.git_ref,
        },
        "nodes": [json_safe(node.as_dict()) for node in artifacts.nodes],
        "edges": [json_safe(edge.as_dict()) for edge in artifacts.edges],
    }


def export_json(graph: nx.MultiDiGraph, artifacts: BuildArtifacts, out_path: Path) -> None:
    out_path.write_text(json.dumps(graph_payload(graph, artifacts), indent=2), encoding="utf-8")


def export_ndjson(graph: nx.MultiDiGraph, artifacts: BuildArtifacts, out_path: Path) -> None:
    lines: list[str] = []
    for node in artifacts.nodes:
        lines.append(json.dumps({"kind": "node", **json_safe(node.as_dict())}))
    for edge in artifacts.edges:
        lines.append(json.dumps({"kind": "edge", **json_safe(edge.as_dict())}))
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_graphml(graph: nx.MultiDiGraph, out_path: Path) -> None:
    normalized = nx.MultiDiGraph()
    for node_id, attrs in graph.nodes(data=True):
        normalized.add_node(node_id, **{k: _graphml_value(v) for k, v in attrs.items()})
    for src, dst, key, attrs in graph.edges(keys=True, data=True):
        normalized.add_edge(src, dst, key=key, **{k: _graphml_value(v) for k, v in attrs.items()})
    nx.write_graphml(normalized, out_path)


def _graphml_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return str(value.value)
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(json_safe(value), sort_keys=True)
