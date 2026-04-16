from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import networkx as nx

from .ast_builder import build_ast_layer
from .repo_index import index_repository
from .schema import (
    BuildArtifacts,
    EdgeCategory,
    EdgeLabel,
    EdgeRecord,
    FileRecord,
    NodeCategory,
    NodeLabel,
    NodeRecord,
    ParsedFile,
    RepoIndex,
)
from .semantic_builder import build_semantic_layer
from .stitcher import stitch_repository_graph
from .utils import edge_id, json_safe, node_id


def _directory_nodes(
    repo_id: str, directories: list[str]
) -> tuple[list[NodeRecord], list[EdgeRecord]]:
    nodes: list[NodeRecord] = []
    edges: list[EdgeRecord] = []
    for directory in directories:
        directory_id = node_id("dir", directory)
        nodes.append(
            NodeRecord(
                id=directory_id,
                label=NodeLabel.DIRECTORY,
                category=NodeCategory.META,
                language="",
                file_path=directory,
                properties={"path": directory},
            ),
        )
        edges.append(
            EdgeRecord(
                id=edge_id(EdgeLabel.REPO_CONTAINS_DIR, repo_id, directory_id),
                label=EdgeLabel.REPO_CONTAINS_DIR,
                src=repo_id,
                dst=directory_id,
                category=EdgeCategory.CONTAINMENT,
            ),
        )
    return nodes, edges


def _package_nodes(repo_id: str, packages: list[str]) -> tuple[list[NodeRecord], list[EdgeRecord]]:
    nodes: list[NodeRecord] = []
    edges: list[EdgeRecord] = []
    for package in packages:
        package_id = node_id("package", package)
        nodes.append(
            NodeRecord(
                id=package_id,
                label=NodeLabel.PACKAGE,
                category=NodeCategory.META,
                language="",
                file_path=package,
                properties={"path": package, "name": package.rsplit("/", 1)[-1]},
            ),
        )
        edges.append(
            EdgeRecord(
                id=edge_id(EdgeLabel.REPO_CONTAINS_DIR, repo_id, package_id, package),
                label=EdgeLabel.REPO_CONTAINS_DIR,
                src=repo_id,
                dst=package_id,
                category=EdgeCategory.CONTAINMENT,
                properties={"package": True},
            ),
        )
    return nodes, edges


def _file_and_module_nodes(
    files: list[FileRecord],
) -> tuple[list[NodeRecord], list[EdgeRecord], dict[str, str]]:
    nodes: list[NodeRecord] = []
    edges: list[EdgeRecord] = []
    file_ids: dict[str, str] = {}

    for file_record in files:
        file_id = node_id("file", file_record.relative_path)
        module_id = node_id("module-meta", file_record.relative_path)
        file_ids[file_record.relative_path] = file_id
        nodes.extend(
            [
                NodeRecord(
                    id=file_id,
                    label=NodeLabel.FILE,
                    category=NodeCategory.META,
                    language=file_record.language,
                    file_path=file_record.relative_path,
                    properties={
                        "path": file_record.relative_path,
                        "hash": file_record.sha256,
                        "size": file_record.size,
                        "last_modified": file_record.last_modified,
                        "git_ref": file_record.git_ref,
                    },
                ),
                NodeRecord(
                    id=module_id,
                    label=NodeLabel.MODULE,
                    category=NodeCategory.META,
                    language=file_record.language,
                    file_path=file_record.relative_path,
                    properties={
                        "path": file_record.relative_path,
                        "name": file_record.path.stem,
                    },
                ),
            ],
        )
        edges.append(
            EdgeRecord(
                id=edge_id(EdgeLabel.DEFINES, file_id, module_id),
                label=EdgeLabel.DEFINES,
                src=file_id,
                dst=module_id,
                category=EdgeCategory.SEMANTIC,
            ),
        )
        parent_dir = file_record.path.relative_to(file_record.repo_root).parent.as_posix()
        if parent_dir and parent_dir != ".":
            dir_id = node_id("dir", parent_dir)
            edges.append(
                EdgeRecord(
                    id=edge_id(EdgeLabel.DIR_CONTAINS_FILE, dir_id, file_id),
                    label=EdgeLabel.DIR_CONTAINS_FILE,
                    src=dir_id,
                    dst=file_id,
                    category=EdgeCategory.CONTAINMENT,
                ),
            )
    return nodes, edges, file_ids


def _dedupe_nodes(nodes: list[NodeRecord]) -> list[NodeRecord]:
    deduped: dict[str, NodeRecord] = {}
    for node in nodes:
        node.validate()
        deduped[node.id] = node
    return list(deduped.values())


def _dedupe_edges(edges: list[EdgeRecord]) -> list[EdgeRecord]:
    deduped: dict[str, EdgeRecord] = {}
    for edge in edges:
        edge.validate()
        deduped[edge.id] = edge
    return list(deduped.values())


def _build_parsed_files(
    repo_index: RepoIndex,
    *,
    include_tokens: bool,
    previous_artifacts: BuildArtifacts | None,
    changed_paths: set[str] | None,
) -> list[ParsedFile]:
    if previous_artifacts is None:
        return build_ast_layer(repo_index, include_tokens=include_tokens)

    current_files = {file.relative_path: file for file in repo_index.files}
    previous_by_path = {
        parsed.file.relative_path: parsed for parsed in previous_artifacts.parsed_files
    }
    changed = {path.replace("\\", "/") for path in (changed_paths or set())}
    if not changed:
        changed = {
            path
            for path, file_record in current_files.items()
            if path not in previous_by_path
            or previous_by_path[path].file.sha256 != file_record.sha256
        }

    reparsed_index = replace(
        repo_index,
        files=[file for file in repo_index.files if file.relative_path in changed],
    )
    previous_trees = {
        rel_path: parsed.tree
        for rel_path, parsed in previous_by_path.items()
        if rel_path in changed
    }
    reparsed = build_ast_layer(
        reparsed_index,
        include_tokens=include_tokens,
        previous_trees=previous_trees,
    )
    reused = [
        replace(parsed, file=current_files[parsed.file.relative_path])
        for parsed in previous_artifacts.parsed_files
        if parsed.file.relative_path in current_files and parsed.file.relative_path not in changed
    ]
    return sorted(reused + reparsed, key=lambda parsed: parsed.file.relative_path)


def _summaries(
    nodes: list[NodeRecord],
    edges: list[EdgeRecord],
    parsed_files: list[ParsedFile],
    stitcher_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    node_labels: dict[str, int] = {}
    node_categories: dict[str, int] = {}
    edge_labels: dict[str, int] = {}
    edge_categories: dict[str, int] = {}
    actual_files = {parsed.file.relative_path for parsed in parsed_files}
    node_to_file = {
        node.id: node.file_path
        for node in nodes
        if node.file_path and node.file_path in actual_files
    }
    per_file: dict[str, dict[str, Any]] = {}

    for node in nodes:
        node_labels[str(node.label)] = node_labels.get(str(node.label), 0) + 1
        node_categories[str(node.category)] = node_categories.get(str(node.category), 0) + 1
        if not node.file_path or node.file_path not in actual_files:
            continue
        slot = per_file.setdefault(
            node.file_path,
            {"node_count": 0, "edge_count": 0, "languages": set(), "changed_ranges": 0},
        )
        slot["node_count"] += 1
        slot["languages"].add(node.language)

    for edge in edges:
        edge_labels[str(edge.label)] = edge_labels.get(str(edge.label), 0) + 1
        edge_categories[str(edge.category)] = edge_categories.get(str(edge.category), 0) + 1
        touched = {node_to_file.get(edge.src), node_to_file.get(edge.dst)}
        for file_path in [path for path in touched if path]:
            slot = per_file.setdefault(
                file_path,
                {"node_count": 0, "edge_count": 0, "languages": set(), "changed_ranges": 0},
            )
            slot["edge_count"] += 1

    for parsed in parsed_files:
        slot = per_file.setdefault(
            parsed.file.relative_path,
            {
                "node_count": 0,
                "edge_count": 0,
                "languages": {parsed.file.language},
                "changed_ranges": 0,
            },
        )
        slot["languages"].add(parsed.file.language)
        slot["changed_ranges"] = len(parsed.changed_ranges)

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "file_count": len(per_file),
        "parsed_file_count": len(parsed_files),
        "node_labels": node_labels,
        "node_categories": node_categories,
        "edge_labels": edge_labels,
        "edge_categories": edge_categories,
        "per_file": {
            file_path: {
                **slot,
                "languages": sorted(slot["languages"]),
            }
            for file_path, slot in sorted(per_file.items())
        },
        "stitcher_metrics": stitcher_metrics or {},
    }


def build_cpg(
    repo_root: str | Path,
    *,
    target_languages: set[str] | None = None,
    only_paths: set[str] | None = None,
    git_ref: str | None = None,
    include_tokens: bool = False,
    previous_artifacts: BuildArtifacts | None = None,
    changed_paths: set[str] | None = None,
    repo_identity: str | Path | None = None,
) -> tuple[nx.MultiDiGraph, BuildArtifacts]:
    repo_root = Path(repo_root).resolve()
    repo_index = index_repository(
        repo_root,
        target_languages=target_languages,
        only_paths=only_paths,
        git_ref=git_ref,
        repo_identity=repo_identity,
    )
    parsed_files = _build_parsed_files(
        repo_index,
        include_tokens=include_tokens,
        previous_artifacts=previous_artifacts,
        changed_paths=changed_paths,
    )
    semantic_nodes, semantic_edges = build_semantic_layer(parsed_files)

    nodes: list[NodeRecord] = [
        NodeRecord(
            id=repo_index.repo_id,
            label=NodeLabel.REPO,
            category=NodeCategory.META,
            language="",
            file_path=None,
            properties={"path": str(repo_index.repo_root), "git_ref": repo_index.git_ref},
        ),
    ]
    edges: list[EdgeRecord] = []

    dir_nodes, dir_edges = _directory_nodes(repo_index.repo_id, repo_index.directories)
    pkg_nodes, pkg_edges = _package_nodes(repo_index.repo_id, repo_index.packages)
    file_nodes, file_edges, file_ids = _file_and_module_nodes(repo_index.files)
    stitched_nodes, stitched_edges, stitcher_metrics = stitch_repository_graph(
        repo_index,
        existing_nodes=file_nodes,
    )
    nodes.extend(dir_nodes)
    nodes.extend(pkg_nodes)
    nodes.extend(file_nodes)
    edges.extend(dir_edges)
    edges.extend(pkg_edges)
    edges.extend(file_edges)

    for parsed in parsed_files:
        nodes.extend(parsed.ast_nodes)
        edges.extend(parsed.ast_edges)
        file_id = file_ids.get(parsed.file.relative_path)
        if file_id:
            edges.append(
                EdgeRecord(
                    id=edge_id(EdgeLabel.FILE_CONTAINS_AST_ROOT, file_id, parsed.root_id),
                    label=EdgeLabel.FILE_CONTAINS_AST_ROOT,
                    src=file_id,
                    dst=parsed.root_id,
                    category=EdgeCategory.CONTAINMENT,
                ),
            )

    nodes.extend(semantic_nodes)
    edges.extend(semantic_edges)
    nodes.extend(stitched_nodes)
    edges.extend(stitched_edges)
    nodes = _dedupe_nodes(nodes)
    edges = _dedupe_edges(edges)
    summaries = _summaries(nodes, edges, parsed_files, stitcher_metrics=stitcher_metrics)

    graph = nx.MultiDiGraph()
    for node in nodes:
        graph.add_node(node.id, **json_safe(node.as_dict()))
    for edge in edges:
        graph.add_edge(edge.src, edge.dst, key=edge.id, **json_safe(edge.as_dict()))

    return graph, BuildArtifacts(
        repo_index=repo_index,
        parsed_files=parsed_files,
        nodes=nodes,
        edges=edges,
        summaries=summaries,
    )
