from __future__ import annotations

from typing import Any

from .parser import TreeSitterRegistry, parse_source
from .schema import (
    EdgeCategory,
    EdgeLabel,
    EdgeRecord,
    NodeCategory,
    NodeLabel,
    NodeRecord,
    ParsedFile,
    RepoIndex,
)
from .utils import edge_id, node_id, point_dict, small_snippet


def _iter_children(node, include_tokens: bool) -> list[Any]:
    return list(node.children) if include_tokens else list(node.named_children)


def _ast_node_id(file_path: str, node) -> str:
    return node_id(
        "ast",
        file_path,
        node.type,
        int(node.start_byte),
        int(node.end_byte),
        int(node.start_point[0]),
        int(node.start_point[1]),
    )


def build_ast_layer(
    repo_index: RepoIndex,
    *,
    include_tokens: bool = False,
    previous_trees: dict[str, Any] | None = None,
) -> list[ParsedFile]:
    registry = TreeSitterRegistry()
    parsed_files: list[ParsedFile] = []
    prev = previous_trees or {}

    for file_record in repo_index.files:
        parser = registry.parser_for_file(file_record.path, file_record.language)
        if parser is None:
            continue

        source_bytes = file_record.path.read_bytes()
        parse_result = parse_source(
            parser,
            source_bytes,
            previous_tree=prev.get(file_record.relative_path),
        )
        root = parse_result.tree.root_node
        root_id = node_id(
            "ast-root", file_record.relative_path, file_record.git_ref or "", root.type
        )
        ast_nodes = [
            NodeRecord(
                id=root_id,
                label=NodeLabel.AST_ROOT,
                category=NodeCategory.SYNTAX,
                language=file_record.language,
                file_path=file_record.relative_path,
                properties={
                    "kind": root.type,
                    "start_byte": int(root.start_byte),
                    "end_byte": int(root.end_byte),
                    "start_point": point_dict(root.start_point),
                    "end_point": point_dict(root.end_point),
                    "field_name": None,
                },
            ),
        ]
        ast_edges: list[EdgeRecord] = []
        ast_index: dict[str, dict[str, Any]] = {
            root_id: ast_nodes[0].as_dict(),
        }

        def walk(node, parent_id: str) -> list[str]:
            created_ids: list[str] = []
            children = _iter_children(node, include_tokens=include_tokens)
            for index, child in enumerate(children):
                child_id = _ast_node_id(file_record.relative_path, child)
                field_name = None
                try:
                    field_name = node.field_name_for_child(index)
                except Exception:
                    field_name = None
                record = NodeRecord(
                    id=child_id,
                    label=NodeLabel.AST_NODE,
                    category=NodeCategory.SYNTAX,
                    language=file_record.language,
                    file_path=file_record.relative_path,
                    properties={
                        "kind": child.type,
                        "text_snippet": small_snippet(
                            source_bytes, child.start_byte, child.end_byte
                        ),
                        "start_byte": int(child.start_byte),
                        "end_byte": int(child.end_byte),
                        "start_point": point_dict(child.start_point),
                        "end_point": point_dict(child.end_point),
                        "field_name": field_name,
                        "child_order": index,
                        "is_named": bool(getattr(child, "is_named", True)),
                    },
                )
                ast_nodes.append(record)
                ast_index[child_id] = record.as_dict()
                ast_edges.extend(
                    [
                        EdgeRecord(
                            id=edge_id(EdgeLabel.AST_CHILD, parent_id, child_id, index),
                            label=EdgeLabel.AST_CHILD,
                            src=parent_id,
                            dst=child_id,
                            category=EdgeCategory.SYNTAX,
                            properties={"order": index},
                        ),
                        EdgeRecord(
                            id=edge_id(EdgeLabel.AST_PARENT, child_id, parent_id, index),
                            label=EdgeLabel.AST_PARENT,
                            src=child_id,
                            dst=parent_id,
                            category=EdgeCategory.SYNTAX,
                            properties={"order": index},
                        ),
                    ],
                )
                created_ids.append(child_id)
                walk(child, child_id)
            for left, right in zip(created_ids, created_ids[1:], strict=False):
                ast_edges.append(
                    EdgeRecord(
                        id=edge_id(EdgeLabel.AST_NEXT_SIBLING, left, right),
                        label=EdgeLabel.AST_NEXT_SIBLING,
                        src=left,
                        dst=right,
                        category=EdgeCategory.SYNTAX,
                    ),
                )
            return created_ids

        walk(root, root_id)
        parsed_files.append(
            ParsedFile(
                file=file_record,
                source_bytes=source_bytes,
                tree=parse_result.tree,
                root_id=root_id,
                ast_nodes=ast_nodes,
                ast_edges=ast_edges,
                ast_index=ast_index,
                changed_ranges=parse_result.changed_ranges,
            ),
        )

    return parsed_files
