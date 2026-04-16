from __future__ import annotations

import json
from pathlib import Path

from cpg_builder.exporters import export_graphml, export_json, export_ndjson, graph_payload
from cpg_builder.fusion import build_cpg
from cpg_builder.git_diff import diff_artifacts
from cpg_builder.pyg import cpg_to_pyg
from cpg_builder.schema import EdgeLabel, NodeCategory, NodeLabel

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "cpg_demo_repo"


def test_build_cpg_fuses_repo_ast_and_semantics() -> None:
    graph, artifacts = build_cpg(FIXTURE_REPO)

    labels = {node.label for node in artifacts.nodes}
    edge_labels = {edge.label for edge in artifacts.edges}

    assert graph.number_of_nodes() == len(artifacts.nodes)
    assert NodeLabel.REPO in labels
    assert NodeLabel.FILE in labels
    assert NodeLabel.AST_ROOT in labels
    assert NodeLabel.FUNCTION in labels
    assert NodeLabel.CALLSITE in labels
    assert EdgeLabel.FILE_CONTAINS_AST_ROOT in edge_labels
    assert EdgeLabel.AST_CHILD in edge_labels
    assert EdgeLabel.DECLARES in edge_labels
    assert EdgeLabel.RESOLVES_TO in edge_labels
    assert artifacts.summaries["file_count"] >= 2


def test_semantic_nodes_keep_ast_anchor() -> None:
    _graph, artifacts = build_cpg(FIXTURE_REPO)
    semantic_nodes = [node for node in artifacts.nodes if node.category == NodeCategory.SEMANTIC]
    anchored = [node for node in semantic_nodes if node.properties.get("anchor_ast_id")]

    assert semantic_nodes
    assert anchored
    assert any(node.label == NodeLabel.MODULE_SYMBOL for node in anchored)


def test_build_single_file_cpg_filters_scope() -> None:
    _graph, artifacts = build_cpg(FIXTURE_REPO, only_paths={"web/index.ts"})
    file_nodes = [node for node in artifacts.nodes if node.label == NodeLabel.FILE]

    assert len(file_nodes) == 1
    assert file_nodes[0].file_path == "web/index.ts"


def test_exporters_write_expected_formats(tmp_path: Path) -> None:
    graph, artifacts = build_cpg(FIXTURE_REPO)
    json_path = tmp_path / "cpg.json"
    ndjson_path = tmp_path / "cpg.ndjson"
    graphml_path = tmp_path / "cpg.graphml"

    export_json(graph, artifacts, json_path)
    export_ndjson(graph, artifacts, ndjson_path)
    export_graphml(graph, graphml_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["node_count"] == graph.number_of_nodes()
    assert ndjson_path.read_text(encoding="utf-8").count("\n") >= 2
    assert graphml_path.exists()


def test_diff_artifacts_detects_changed_nodes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "app.py").write_text(
        "def greet(name):\n    return name\n",
        encoding="utf-8",
    )
    _base_graph, base_artifacts = build_cpg(repo_root)

    (repo_root / "app.py").write_text(
        "def greet(name):\n    alias = name\n    return alias\n",
        encoding="utf-8",
    )
    _head_graph, head_artifacts = build_cpg(
        repo_root,
        previous_artifacts=base_artifacts,
        changed_paths={"app.py"},
    )
    diff = diff_artifacts(base_artifacts, head_artifacts)

    assert diff.added_nodes or diff.changed_nodes
    assert not diff.removed_nodes


def test_graph_payload_is_json_ready() -> None:
    graph, artifacts = build_cpg(FIXTURE_REPO)
    payload = graph_payload(graph, artifacts)

    assert payload["repo"]["path"]
    assert payload["summary"]["node_count"] == len(payload["nodes"])


def test_cpg_to_pyg_returns_expected_tensors() -> None:
    try:
        import torch  # noqa: F401
    except ImportError:
        return

    graph, _artifacts = build_cpg(FIXTURE_REPO)
    tensors = cpg_to_pyg(graph)

    assert tensors["x"].shape[0] == graph.number_of_nodes()
    assert tensors["edge_index"].shape[0] == 2
    assert len(tensors["node_ids"]) == graph.number_of_nodes()
