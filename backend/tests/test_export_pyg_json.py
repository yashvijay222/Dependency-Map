from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from cpg_builder.exporters import export_pyg_json
from cpg_builder.schema import BuildArtifacts, RepoIndex


def test_export_pyg_json_shape(tmp_path: Path) -> None:
    graph = nx.MultiDiGraph()
    graph.add_node("n1", label="FILE", language="typescript")
    graph.add_node("n2", label="ROUTE", language="python")
    graph.add_edge("n1", "n2", key="e1", label="HTTP_CALLS_ROUTE")
    idx = RepoIndex(
        repo_root=tmp_path,
        repo_id="test",
        files=[],
        directories=[],
        packages=[],
        git_ref=None,
    )
    artifacts = BuildArtifacts(
        repo_index=idx,
        parsed_files=[],
        nodes=[],
        edges=[],
        summaries={"node_count": 2, "edge_count": 1},
    )
    out = tmp_path / "pyg.json"
    export_pyg_json(graph, artifacts, out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["format"] == "cpg_pyg_v1"
    assert data["num_nodes"] == 2
    assert len(data["edge_index"][0]) == 1
    assert len(data["x"]) == 2
