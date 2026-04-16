"""Abstract semantic graph (ASG) built from AST + dependency graph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.ast_parser import build_ast_graph
from app.services.graph_builder import build_dependency_graph

SEMANTIC_AST_TYPES = {
    "import_statement",
    "function_declaration",
    "function_expression",
    "arrow_function",
    "method_definition",
    "class_declaration",
    "interface_declaration",
    "type_alias_declaration",
    "enum_declaration",
    "variable_declarator",
}


def _semantic_kind(ast_node: dict[str, Any]) -> str:
    ast_type = str(ast_node.get("ast_type", ""))
    kind = str(ast_node.get("kind", ""))
    if ast_type == "import_statement":
        return "import"
    if ast_type in {"class_declaration", "interface_declaration", "type_alias_declaration"}:
        return "type"
    if ast_type == "enum_declaration":
        return "enum"
    if ast_type == "variable_declarator":
        return "binding"
    if kind == "function":
        return "function"
    return kind or ast_type or "symbol"


def _semantic_node_id(ast_node: dict[str, Any]) -> str:
    return f"symbol:{ast_node['id']}"


def _module_node(file_path: str) -> dict[str, Any]:
    name = file_path.rsplit("/", 1)[-1]
    return {
        "id": f"module:{file_path}",
        "kind": "module",
        "name": name,
        "file": file_path,
        "path": file_path,
    }


def _package_node(package_name: str) -> dict[str, Any]:
    return {
        "id": f"package:{package_name}",
        "kind": "package",
        "name": package_name,
    }


def build_asg(repo_root: Path) -> dict[str, Any]:
    ast_graph = build_ast_graph(repo_root)
    dep_graph = build_dependency_graph(repo_root)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()

    def add_node(node: dict[str, Any]) -> None:
        node_id = str(node["id"])
        if node_id in seen_nodes:
            return
        seen_nodes.add(node_id)
        nodes.append(node)

    ast_nodes = [n for n in (ast_graph.get("nodes") or []) if isinstance(n, dict)]
    dep_edges = [e for e in (dep_graph.get("edges") or []) if isinstance(e, dict)]

    file_nodes = [n for n in ast_nodes if str(n.get("kind")) == "file" and n.get("file")]
    module_ids_by_file: dict[str, str] = {}
    for file_node in file_nodes:
        file_path = str(file_node["file"])
        module = _module_node(file_path)
        add_node(module)
        module_ids_by_file[file_path] = str(module["id"])

    for ast_node in ast_nodes:
        ast_type = str(ast_node.get("ast_type", ""))
        file_path = str(ast_node.get("file", ""))
        if ast_type not in SEMANTIC_AST_TYPES or not file_path:
            continue
        semantic_node = {
            "id": _semantic_node_id(ast_node),
            "kind": _semantic_kind(ast_node),
            "name": str(ast_node.get("name") or ast_type),
            "file": file_path,
            "line": int(ast_node.get("line") or 0),
            "ast_type": ast_type,
            "code_snippet": str(ast_node.get("code_snippet") or ""),
        }
        add_node(semantic_node)
        module_id = module_ids_by_file.get(file_path)
        if module_id:
            edges.append(
                {
                    "source": module_id,
                    "target": semantic_node["id"],
                    "type": "contains",
                },
            )

    for dep_edge in dep_edges:
        source_path = str(dep_edge.get("source", ""))
        target_path = str(dep_edge.get("target", ""))
        edge_type = str(dep_edge.get("type", "depends_on"))
        source_id = module_ids_by_file.get(source_path)
        if not source_id:
            continue
        if target_path.startswith("package:"):
            package_name = target_path.removeprefix("package:")
            package = _package_node(package_name)
            add_node(package)
            edges.append(
                {
                    "source": source_id,
                    "target": package["id"],
                    "type": "imports_package" if edge_type == "import" else edge_type,
                },
            )
            continue
        target_id = module_ids_by_file.get(target_path)
        if target_id:
            edges.append(
                {
                    "source": source_id,
                    "target": target_id,
                    "type": "imports_module" if edge_type == "import" else edge_type,
                },
            )

    counts_by_kind: dict[str, int] = {}
    for node in nodes:
        kind = str(node.get("kind", "unknown"))
        counts_by_kind[kind] = counts_by_kind.get(kind, 0) + 1

    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "counts_by_kind": counts_by_kind,
        "source_ast_node_count": int(ast_graph.get("node_count", 0)),
        "source_dependency_edge_count": len(dep_edges),
    }
