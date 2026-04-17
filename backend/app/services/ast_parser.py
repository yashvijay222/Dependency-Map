"""Layer 1: tree-sitter AST graph (TS/JS/TSX/JSX)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.graph_builder import SKIP_DIR_PARTS, SOURCE_EXTS
from app.services.tree_sitter_languages import parser_for_suffix


def _iter_source_files(repo_root: Path) -> list[str]:
    out: list[str] = []
    root = repo_root.resolve()
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in SOURCE_EXTS:
            continue
        if any(part in SKIP_DIR_PARTS for part in p.parts):
            continue
        out.append(p.relative_to(root).as_posix())
    return sorted(out)


def _snippet_for_node(source: bytes, start_byte: int, end_byte: int, limit: int = 240) -> str:
    text = source[start_byte:end_byte].decode("utf-8", errors="ignore").strip()
    if not text:
        return ""
    return text.splitlines()[0][:limit]


def _node_kind(node_type: str) -> str:
    if node_type == "import_statement":
        return "import"
    if node_type in {
        "function_declaration",
        "function_expression",
        "arrow_function",
        "method_definition",
    }:
        return "function"
    return node_type


def _node_name(node, source: bytes) -> str:
    if node.type == "import_statement":
        return "import"
    for child in node.children:
        if child.type in {"identifier", "property_identifier", "type_identifier"}:
            return source[child.start_byte : child.end_byte].decode("utf-8", errors="ignore")
    return node.type


def _node_id(rel: str, node) -> str:
    line = node.start_point[0] + 1
    column = node.start_point[1] + 1
    return f"{rel}:{line}:{column}:{node.type}:{node.start_byte}"


def _append_ast_node(
    nodes: list[dict[str, Any]],
    rel: str,
    source: bytes,
    node,
) -> str:
    node_id = _node_id(rel, node)
    nodes.append(
        {
            "id": node_id,
            "kind": _node_kind(node.type),
            "ast_type": node.type,
            "name": _node_name(node, source),
            "file": rel,
            "line": node.start_point[0] + 1,
            "column": node.start_point[1] + 1,
            "start_byte": node.start_byte,
            "end_byte": node.end_byte,
            "named": bool(getattr(node, "is_named", True)),
            "code_snippet": _snippet_for_node(source, node.start_byte, node.end_byte),
        },
    )
    return node_id


def _walk_named_tree(
    node,
    rel: str,
    source: bytes,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    parent_id: str,
) -> None:
    node_id = _append_ast_node(nodes, rel, source, node)
    edges.append({"source": parent_id, "target": node_id, "type": "ast_child"})
    for child in node.named_children:
        _walk_named_tree(child, rel, source, nodes, edges, node_id)


def build_ast_graph(repo_root: Path) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    root = repo_root.resolve()
    parsed_files = 0

    for rel in _iter_source_files(root):
        path = root / rel
        parser = parser_for_suffix(path.suffix)
        if parser is None:
            continue
        parsed_files += 1
        file_id = f"{rel}:0:0:file:0"
        nodes.append(
            {
                "id": file_id,
                "kind": "file",
                "ast_type": "file",
                "name": rel.rsplit("/", 1)[-1],
                "file": rel,
                "line": 1,
                "column": 1,
                "start_byte": 0,
                "end_byte": 0,
                "named": True,
                "code_snippet": "",
            },
        )
        source_bytes = path.read_bytes()
        tree = parser.parse(source_bytes)
        _walk_named_tree(tree.root_node, rel, source_bytes, nodes, edges, file_id)

    return {
        "nodes": nodes,
        "edges": edges,
        "file_count": parsed_files,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
