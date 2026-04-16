from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schema import (
    EdgeCategory,
    EdgeLabel,
    EdgeRecord,
    NodeCategory,
    NodeLabel,
    NodeRecord,
    ParsedFile,
)
from .utils import edge_id, node_id

DECLARATION_NODE_TYPES = {
    "python": {
        "class_definition": NodeLabel.CLASS,
        "function_definition": NodeLabel.FUNCTION,
        "assignment": NodeLabel.VARIABLE,
        "import_statement": NodeLabel.IMPORT,
        "import_from_statement": NodeLabel.IMPORT,
    },
    "javascript": {
        "class_declaration": NodeLabel.CLASS,
        "function_declaration": NodeLabel.FUNCTION,
        "method_definition": NodeLabel.METHOD,
        "lexical_declaration": NodeLabel.VARIABLE,
        "variable_declarator": NodeLabel.VARIABLE,
        "import_statement": NodeLabel.IMPORT,
    },
    "typescript": {
        "class_declaration": NodeLabel.CLASS,
        "function_declaration": NodeLabel.FUNCTION,
        "method_definition": NodeLabel.METHOD,
        "lexical_declaration": NodeLabel.VARIABLE,
        "variable_declarator": NodeLabel.VARIABLE,
        "interface_declaration": NodeLabel.TYPE,
        "type_alias_declaration": NodeLabel.TYPE,
        "enum_declaration": NodeLabel.TYPE,
        "import_statement": NodeLabel.IMPORT,
    },
    "java": {
        "class_declaration": NodeLabel.CLASS,
        "interface_declaration": NodeLabel.TYPE,
        "enum_declaration": NodeLabel.TYPE,
        "method_declaration": NodeLabel.METHOD,
        "constructor_declaration": NodeLabel.METHOD,
        "field_declaration": NodeLabel.VARIABLE,
        "local_variable_declaration": NodeLabel.VARIABLE,
        "import_declaration": NodeLabel.IMPORT,
    },
}

CALL_NODE_TYPES = {
    "python": {"call"},
    "javascript": {"call_expression"},
    "typescript": {"call_expression"},
    "java": {"method_invocation", "object_creation_expression"},
}

IDENTIFIER_TYPES = {
    "python": {"identifier"},
    "javascript": {"identifier", "property_identifier"},
    "typescript": {"identifier", "property_identifier", "type_identifier"},
    "java": {"identifier", "type_identifier"},
}


@dataclass(slots=True)
class ScopeFrame:
    id: str
    label: str
    parent: str | None
    names: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class SemanticState:
    nodes: list[NodeRecord] = field(default_factory=list)
    edges: list[EdgeRecord] = field(default_factory=list)
    node_ids: set[str] = field(default_factory=set)
    unresolved_cache: dict[tuple[str, str], str] = field(default_factory=dict)
    module_symbols_by_file: dict[str, str] = field(default_factory=dict)
    exported_symbols: dict[str, dict[str, str]] = field(default_factory=dict)
    global_modules_by_name: dict[str, str] = field(default_factory=dict)

    def add_node(self, node: NodeRecord) -> None:
        if node.id in self.node_ids:
            return
        node.validate()
        self.node_ids.add(node.id)
        self.nodes.append(node)

    def add_edge(self, edge: EdgeRecord) -> None:
        edge.validate()
        self.edges.append(edge)


def _module_name_for_file(file_path: str) -> str:
    path = Path(file_path)
    if path.name == "__init__.py":
        return ".".join(path.parent.parts)
    stem = path.with_suffix("")
    return ".".join(stem.parts)


def _iter_named(node) -> list[Any]:
    try:
        return list(node.named_children)
    except Exception:
        return []


def _node_id(prefix: str, file_path: str, *parts: object) -> str:
    return node_id(prefix, file_path, *parts)


def _find_first_identifier(node, source: bytes, language: str) -> tuple[str | None, Any | None]:
    types = IDENTIFIER_TYPES.get(language, {"identifier"})
    stack = [node]
    while stack:
        cur = stack.pop()
        if cur.type in types:
            text = source[cur.start_byte : cur.end_byte].decode("utf-8", errors="ignore")
            return text, cur
        stack.extend(reversed(_iter_named(cur)))
    return None, None


def _call_target_name(node, source: bytes, language: str) -> str | None:
    for child in _iter_named(node):
        name, _ = _find_first_identifier(child, source, language)
        if name:
            return name
    return None


def _resolve_relative_import(importer: str, spec: str, available_files: set[str]) -> str | None:
    if not spec.startswith("."):
        return None
    importer_path = Path(importer)
    base_dir = importer_path.parent
    target = (base_dir / spec).as_posix()
    candidates = [
        target,
        f"{target}.py",
        f"{target}.ts",
        f"{target}.tsx",
        f"{target}.js",
        f"{target}.jsx",
        f"{target}.java",
        f"{target}/__init__.py",
        f"{target}/index.ts",
        f"{target}/index.tsx",
        f"{target}/index.js",
        f"{target}/index.jsx",
    ]
    for candidate in candidates:
        norm = Path(candidate).as_posix()
        if norm in available_files:
            return norm
    return None


def _read_identifier_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="ignore")


def _extract_import_specs(node, source: bytes) -> list[str]:
    text = source[node.start_byte : node.end_byte].decode("utf-8", errors="ignore")
    specs: list[str] = []
    quote = None
    current = []
    for ch in text:
        if quote is None and ch in {"'", '"'}:
            quote = ch
            current = []
            continue
        if quote is not None:
            if ch == quote:
                specs.append("".join(current))
                quote = None
                current = []
            else:
                current.append(ch)
    return specs


def _is_declaration_identifier(parent_type: str, language: str) -> bool:
    decls = DECLARATION_NODE_TYPES.get(language, {})
    return parent_type in decls or parent_type in {"formal_parameters", "parameters", "identifier"}


def _lookup_name(scopes: list[ScopeFrame], name: str) -> str | None:
    for scope in reversed(scopes):
        if name in scope.names:
            return scope.names[name]
    return None


def _unresolved_symbol(state: SemanticState, file_path: str, name: str, language: str) -> str:
    key = (file_path, name)
    if key in state.unresolved_cache:
        return state.unresolved_cache[key]
    unresolved_id = _node_id("semantic-unresolved", file_path, name)
    state.add_node(
        NodeRecord(
            id=unresolved_id,
            label=NodeLabel.SYMBOL,
            category=NodeCategory.SEMANTIC,
            language=language,
            file_path=file_path,
            properties={"name": name, "unresolved": True},
        ),
    )
    state.unresolved_cache[key] = unresolved_id
    return unresolved_id


def build_semantic_layer(
    parsed_files: list[ParsedFile],
) -> tuple[list[NodeRecord], list[EdgeRecord]]:
    state = SemanticState()
    available_files = {parsed.file.relative_path for parsed in parsed_files}

    for parsed in parsed_files:
        file_path = parsed.file.relative_path
        module_symbol_id = _node_id("semantic-module", file_path)
        module_scope_id = _node_id("semantic-scope", file_path, "module")
        state.add_node(
            NodeRecord(
                id=module_symbol_id,
                label=NodeLabel.MODULE_SYMBOL,
                category=NodeCategory.SEMANTIC,
                language=parsed.file.language,
                file_path=file_path,
                properties={
                    "name": _module_name_for_file(file_path),
                    "anchor_ast_id": parsed.root_id,
                },
            ),
        )
        state.add_node(
            NodeRecord(
                id=module_scope_id,
                label=NodeLabel.SCOPE,
                category=NodeCategory.SEMANTIC,
                language=parsed.file.language,
                file_path=file_path,
                properties={"scope_kind": "module", "anchor_ast_id": parsed.root_id},
            ),
        )
        state.add_edge(
            EdgeRecord(
                id=edge_id(EdgeLabel.BELONGS_TO_SCOPE, module_symbol_id, module_scope_id),
                label=EdgeLabel.BELONGS_TO_SCOPE,
                src=module_symbol_id,
                dst=module_scope_id,
                category=EdgeCategory.SEMANTIC,
            ),
        )
        state.module_symbols_by_file[file_path] = module_symbol_id
        state.global_modules_by_name[_module_name_for_file(file_path)] = module_symbol_id
        state.exported_symbols[file_path] = {}

    for parsed in parsed_files:
        file_path = parsed.file.relative_path
        language = parsed.file.language
        module_symbol_id = state.module_symbols_by_file[file_path]
        module_scope_id = _node_id("semantic-scope", file_path, "module")
        scopes: list[ScopeFrame] = [ScopeFrame(id=module_scope_id, label="module", parent=None)]
        declaration_anchors: set[str] = set()
        ref_nodes: list[tuple[str, str, str, str | None, str]] = []
        callsites: list[tuple[str, str, str, str | None]] = []
        def_sites: dict[str, list[str]] = {}

        def register_symbol(
            label: str,
            name: str,
            anchor_ast_id: str,
            *,
            scope_kind: str | None = None,
            parent_symbol: str | None = None,
            inferred: bool = False,
        ) -> str:
            current_scope = scopes[-1]
            semantic_id = _node_id(
                "semantic", file_path, current_scope.id, label, name, anchor_ast_id
            )
            state.add_node(
                NodeRecord(
                    id=semantic_id,
                    label=label,
                    category=NodeCategory.SEMANTIC,
                    language=language,
                    file_path=file_path,
                    properties={
                        "name": name,
                        "anchor_ast_id": anchor_ast_id,
                        "inferred": inferred,
                    },
                ),
            )
            state.add_edge(
                EdgeRecord(
                    id=edge_id(EdgeLabel.DECLARES, current_scope.id, semantic_id, name),
                    label=EdgeLabel.DECLARES,
                    src=current_scope.id,
                    dst=semantic_id,
                    category=EdgeCategory.SEMANTIC,
                ),
            )
            state.add_edge(
                EdgeRecord(
                    id=edge_id(EdgeLabel.BELONGS_TO_SCOPE, semantic_id, current_scope.id, name),
                    label=EdgeLabel.BELONGS_TO_SCOPE,
                    src=semantic_id,
                    dst=current_scope.id,
                    category=EdgeCategory.SEMANTIC,
                ),
            )
            if parent_symbol:
                state.add_edge(
                    EdgeRecord(
                        id=edge_id(EdgeLabel.DEFINES, parent_symbol, semantic_id, name),
                        label=EdgeLabel.DEFINES,
                        src=parent_symbol,
                        dst=semantic_id,
                        category=EdgeCategory.SEMANTIC,
                    ),
                )
            current_scope.names.setdefault(name, semantic_id)
            if current_scope.label == "module":
                state.exported_symbols[file_path].setdefault(name, semantic_id)
            if scope_kind:
                scope_id = _node_id("semantic-scope", file_path, semantic_id, scope_kind)
                state.add_node(
                    NodeRecord(
                        id=scope_id,
                        label=NodeLabel.SCOPE,
                        category=NodeCategory.SEMANTIC,
                        language=language,
                        file_path=file_path,
                        properties={"scope_kind": scope_kind, "anchor_ast_id": anchor_ast_id},
                    ),
                )
                scopes.append(ScopeFrame(id=scope_id, label=scope_kind, parent=current_scope.id))
            return semantic_id

        def leave_scope_if_needed(node_type: str) -> None:
            if len(scopes) <= 1:
                return
            if (
                node_type in {"class_definition", "class_declaration"}
                and scopes[-1].label == "class"
            ):
                scopes.pop()
            elif node_type in {
                "function_definition",
                "function_declaration",
                "method_definition",
                "method_declaration",
                "constructor_declaration",
            } and scopes[-1].label in {"function", "method"}:
                scopes.pop()

        def walk(node, owner_symbol: str) -> None:
            ast_id = _node_id(
                "ast",
                file_path,
                node.type,
                node.start_byte,
                node.end_byte,
                node.start_point[0],
                node.start_point[1],
            )
            decl_map = DECLARATION_NODE_TYPES.get(language, {})
            label = decl_map.get(node.type)
            entered_scope = False

            if label is not None:
                name, name_node = _find_first_identifier(node, parsed.source_bytes, language)
                if label == NodeLabel.IMPORT:
                    specs = _extract_import_specs(node, parsed.source_bytes)
                    import_name = specs[0] if specs else (name or "import")
                    import_id = register_symbol(
                        NodeLabel.IMPORT, import_name, ast_id, parent_symbol=module_symbol_id
                    )
                    declaration_anchors.add(ast_id)
                    for spec in specs:
                        target_file = _resolve_relative_import(file_path, spec, available_files)
                        if target_file and target_file in state.module_symbols_by_file:
                            target_symbol = state.module_symbols_by_file[target_file]
                        else:
                            target_symbol = state.global_modules_by_name.get(spec)
                        if target_symbol is None:
                            target_symbol = _unresolved_symbol(state, file_path, spec, language)
                        state.add_edge(
                            EdgeRecord(
                                id=edge_id(
                                    EdgeLabel.IMPORTS, module_symbol_id, target_symbol, import_id
                                ),
                                label=EdgeLabel.IMPORTS,
                                src=module_symbol_id,
                                dst=target_symbol,
                                category=EdgeCategory.SEMANTIC,
                                properties={"anchor_ast_id": ast_id},
                            ),
                        )
                        alias_name = name or spec.rsplit("/", 1)[-1].split(".")[-1]
                        scopes[0].names.setdefault(alias_name, target_symbol)
                    return
                if name:
                    declaration_anchors.add(ast_id)
                    parent = owner_symbol
                    if label == NodeLabel.CLASS:
                        parent = module_symbol_id
                        register_symbol(
                            label, name, ast_id, scope_kind="class", parent_symbol=parent
                        )
                        entered_scope = True
                    elif label in {NodeLabel.FUNCTION, NodeLabel.METHOD}:
                        scope_kind = "method" if label == NodeLabel.METHOD else "function"
                        register_symbol(
                            label, name, ast_id, scope_kind=scope_kind, parent_symbol=parent
                        )
                        entered_scope = True
                    elif label == NodeLabel.TYPE:
                        register_symbol(label, name, ast_id, parent_symbol=parent)
                    elif label == NodeLabel.VARIABLE:
                        var_id = register_symbol(
                            label,
                            name,
                            ast_id,
                            parent_symbol=parent,
                            inferred=node.type == "assignment",
                        )
                        def_sites.setdefault(name, []).append(var_id)

            if node.type in CALL_NODE_TYPES.get(language, set()):
                callsite_name = _call_target_name(node, parsed.source_bytes, language) or "call"
                callsite_id = _node_id("callsite", file_path, ast_id, callsite_name)
                state.add_node(
                    NodeRecord(
                        id=callsite_id,
                        label=NodeLabel.CALLSITE,
                        category=NodeCategory.SEMANTIC,
                        language=language,
                        file_path=file_path,
                        properties={"name": callsite_name, "anchor_ast_id": ast_id},
                    ),
                )
                state.add_edge(
                    EdgeRecord(
                        id=edge_id(
                            EdgeLabel.BELONGS_TO_SCOPE, callsite_id, scopes[-1].id, callsite_name
                        ),
                        label=EdgeLabel.BELONGS_TO_SCOPE,
                        src=callsite_id,
                        dst=scopes[-1].id,
                        category=EdgeCategory.SEMANTIC,
                    ),
                )
                callsites.append(
                    (callsite_id, callsite_name, ast_id, _lookup_name(scopes, callsite_name))
                )

            if node.type in IDENTIFIER_TYPES.get(language, set()):
                text = _read_identifier_text(node, parsed.source_bytes)
                parent_type = node.parent.type if getattr(node, "parent", None) is not None else ""
                if text and not _is_declaration_identifier(parent_type, language):
                    ref_id = _node_id("semantic-ref", file_path, ast_id, text)
                    state.add_node(
                        NodeRecord(
                            id=ref_id,
                            label=NodeLabel.SYMBOL,
                            category=NodeCategory.SEMANTIC,
                            language=language,
                            file_path=file_path,
                            properties={"name": text, "anchor_ast_id": ast_id, "role": "reference"},
                        ),
                    )
                    state.add_edge(
                        EdgeRecord(
                            id=edge_id(EdgeLabel.BELONGS_TO_SCOPE, ref_id, scopes[-1].id, text),
                            label=EdgeLabel.BELONGS_TO_SCOPE,
                            src=ref_id,
                            dst=scopes[-1].id,
                            category=EdgeCategory.SEMANTIC,
                        ),
                    )
                    ref_nodes.append(
                        (ref_id, text, ast_id, _lookup_name(scopes, text), scopes[-1].id)
                    )

            for child in _iter_named(node):
                walk(child, owner_symbol)

            if entered_scope:
                leave_scope_if_needed(node.type)

        walk(parsed.tree.root_node, module_symbol_id)

        for ref_id, name, ast_id, resolved_now, scope_id in ref_nodes:
            resolved = resolved_now
            if resolved is None:
                resolved = _unresolved_symbol(state, file_path, name, language)
            state.add_edge(
                EdgeRecord(
                    id=edge_id(EdgeLabel.RESOLVES_TO, ref_id, resolved, ast_id),
                    label=EdgeLabel.RESOLVES_TO,
                    src=ref_id,
                    dst=resolved,
                    category=EdgeCategory.SEMANTIC,
                ),
            )
            state.add_edge(
                EdgeRecord(
                    id=edge_id(EdgeLabel.REFERENCES, scope_id, resolved, ref_id),
                    label=EdgeLabel.REFERENCES,
                    src=scope_id,
                    dst=resolved,
                    category=EdgeCategory.SEMANTIC,
                    properties={"reference_id": ref_id},
                ),
            )
            if name in def_sites:
                for source_var in def_sites[name]:
                    state.add_edge(
                        EdgeRecord(
                            id=edge_id(EdgeLabel.DEF_USE, source_var, resolved, ref_id),
                            label=EdgeLabel.DEF_USE,
                            src=source_var,
                            dst=resolved,
                            category=EdgeCategory.SEMANTIC,
                            properties={"inferred": True, "reference_id": ref_id},
                        ),
                    )

        for callsite_id, call_name, ast_id, resolved_now in callsites:
            resolved = resolved_now
            if resolved is None:
                resolved = _unresolved_symbol(state, file_path, call_name, language)
            state.add_edge(
                EdgeRecord(
                    id=edge_id(EdgeLabel.CALLS, callsite_id, resolved, ast_id),
                    label=EdgeLabel.CALLS,
                    src=callsite_id,
                    dst=resolved,
                    category=EdgeCategory.SEMANTIC,
                    properties={"inferred": True},
                ),
            )

    return state.nodes, state.edges
