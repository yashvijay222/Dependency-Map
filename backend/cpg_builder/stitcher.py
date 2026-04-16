from __future__ import annotations

import re
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
    RepoIndex,
)
from .utils import edge_id, node_id

ROUTE_DECORATOR_RE = re.compile(
    r"@\s*(?:router|app)\.(get|post|put|delete|patch)\(\s*[\"']([^\"']+)"
)
FUNCTION_RE = re.compile(r"def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
TABLE_CALL_RE = re.compile(r"\.table\(\s*[\"']([^\"']+)[\"']\s*\)")
RPC_CALL_RE = re.compile(r"\.rpc\(\s*[\"']([^\"']+)[\"']\s*\)")
POLICY_RE = re.compile(
    r'create policy\s+"([^"]+)"\s+on\s+public\.([a-zA-Z0-9_]+)\s+for\s+([a-zA-Z]+)',
    re.IGNORECASE,
)
CREATE_TABLE_RE = re.compile(
    r"create table(?: if not exists)?\s+public\.([a-zA-Z0-9_]+)\s*\((.*?)\);",
    re.IGNORECASE | re.DOTALL,
)
CREATE_FUNCTION_RE = re.compile(
    r"create or replace function\s+public\.([a-zA-Z0-9_]+)\s*\(",
    re.IGNORECASE,
)
FETCH_LITERAL_RE = re.compile(r"(?:fetch|apiFetchOptional)\(\s*([`\"'])(.+?)\1", re.DOTALL)
V1_ROUTE_FRAGMENT_RE = re.compile(r"(/v1/[A-Za-z0-9_\-./${}?=&]+)")
CELERY_TASK_RE = re.compile(
    r'@celery_app\.task\(name="([^"]+)"\)\s*\ndef\s+([A-Za-z_][A-Za-z0-9_]*)'
)
SEND_TASK_RE = re.compile(r"send_task\(\s*[\"']([^\"']+)[\"']")
DELAY_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\.delay\(")
APPLY_ASYNC_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\.apply_async\(")
ROUTER_PREFIX_RE = re.compile(r'APIRouter\(\s*prefix\s*=\s*[\"\']([^\"\']+)')

READ_OP_MARKERS = (".select(", ".execute(", ".in_(", ".limit(")
WRITE_OP_MARKERS = (".insert(", ".update(", ".delete(", ".upsert(")


@dataclass(slots=True)
class StitcherMetrics:
    route_count: int = 0
    routes_with_frontend_edges: int = 0
    schema_touching_handlers: int = 0
    schema_linked_handlers: int = 0
    async_producers: int = 0
    linked_async_producers: int = 0
    missing_route_bindings: int = 0
    missing_task_bindings: int = 0
    low_stitcher_coverage: bool = False
    missing_seam_categories: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        route_coverage = (
            self.routes_with_frontend_edges / self.route_count if self.route_count else 1.0
        )
        schema_coverage = (
            self.schema_linked_handlers / self.schema_touching_handlers
            if self.schema_touching_handlers
            else 1.0
        )
        async_coverage = (
            self.linked_async_producers / self.async_producers if self.async_producers else 1.0
        )
        return {
            "route_count": self.route_count,
            "routes_with_frontend_edges": self.routes_with_frontend_edges,
            "schema_touching_handlers": self.schema_touching_handlers,
            "schema_linked_handlers": self.schema_linked_handlers,
            "async_producers": self.async_producers,
            "linked_async_producers": self.linked_async_producers,
            "missing_route_bindings": self.missing_route_bindings,
            "missing_task_bindings": self.missing_task_bindings,
            "route_coverage": round(route_coverage, 4),
            "schema_coverage": round(schema_coverage, 4),
            "async_coverage": round(async_coverage, 4),
            "low_stitcher_coverage": self.low_stitcher_coverage,
            "missing_seam_categories": self.missing_seam_categories,
        }


@dataclass(slots=True)
class ParsedRoute:
    node_id: str
    file_path: str
    method: str
    route_pattern: str
    handler_name: str
    auth_mode: str
    uses_service_role: bool


@dataclass(slots=True)
class ParsedTask:
    node_id: str
    file_path: str
    task_name: str
    handler_name: str
    auth_context: str


class NodeAccumulator:
    def __init__(self) -> None:
        self.nodes: dict[str, NodeRecord] = {}

    def upsert(self, node: NodeRecord) -> str:
        existing = self.nodes.get(node.id)
        if existing is None:
            self.nodes[node.id] = node
            return node.id
        existing.properties = _merge_props(existing.properties, node.properties)
        if not existing.file_path:
            existing.file_path = node.file_path
        return node.id

    def values(self) -> list[NodeRecord]:
        return list(self.nodes.values())


def stitch_repository_graph(
    repo_index: RepoIndex,
    existing_nodes: list[NodeRecord],
) -> tuple[list[NodeRecord], list[EdgeRecord], dict[str, Any]]:
    file_nodes = {
        node.file_path: node.id
        for node in existing_nodes
        if node.label == NodeLabel.FILE and node.file_path
    }
    nodes = NodeAccumulator()
    edges: dict[str, EdgeRecord] = {}
    metrics = StitcherMetrics()
    routes_by_file: dict[str, list[ParsedRoute]] = {}
    tasks_by_file: dict[str, list[ParsedTask]] = {}
    routes: list[ParsedRoute] = []
    tasks: list[ParsedTask] = []
    db_entities: dict[tuple[str, str, str], str] = {}
    policies_by_table: dict[str, list[str]] = {}
    route_frontend_hits: set[str] = set()
    schema_links_by_route: set[str] = set()
    async_linked_producers: set[str] = set()
    task_name_to_id: dict[str, str] = {}

    migration_files = _migration_files(repo_index.repo_root)
    for migration_order, migration in enumerate(migration_files, start=1):
        migration_node_id = node_id("migration", migration.name)
        nodes.upsert(
            NodeRecord(
                id=migration_node_id,
                label=NodeLabel.MIGRATION,
                category=NodeCategory.META,
                language="sql",
                file_path=migration.relative_to(repo_index.repo_root).as_posix(),
                properties={
                    "migration_id": migration.name,
                    "migration_order": migration_order,
                    "source_system": "database",
                },
            )
        )
        if migration_order > 1:
            previous = node_id("migration", migration_files[migration_order - 2].name)
            _add_edge(
                edges,
                EdgeRecord(
                    id=edge_id(EdgeLabel.MIGRATION_PRECEDES, previous, migration_node_id),
                    label=EdgeLabel.MIGRATION_PRECEDES,
                    src=previous,
                    dst=migration_node_id,
                    category=EdgeCategory.SEMANTIC,
                    properties={"source_system": "database", "target_system": "database"},
                ),
            )
        _parse_migration_file(
            repo_index,
            migration,
            migration_node_id,
            migration_order,
            nodes,
            edges,
            db_entities,
            policies_by_table,
        )

    for file_record in repo_index.files:
        text = file_record.path.read_text(encoding="utf-8", errors="ignore")
        if file_record.language == "python":
            parsed_routes = _parse_routes(
                file_record.relative_path, text, file_record.language, nodes
            )
            if parsed_routes:
                routes_by_file[file_record.relative_path] = parsed_routes
                routes.extend(parsed_routes)
                metrics.route_count += len(parsed_routes)
                for route in parsed_routes:
                    _connect_file_to_node(
                        file_nodes, edges, file_record.relative_path, route.node_id
                    )

            parsed_tasks = _parse_tasks(file_record.relative_path, text, nodes)
            if parsed_tasks:
                tasks_by_file[file_record.relative_path] = parsed_tasks
                tasks.extend(parsed_tasks)
                for task in parsed_tasks:
                    task_name_to_id[task.task_name] = task.node_id
                    _connect_file_to_node(
                        file_nodes, edges, file_record.relative_path, task.node_id
                    )

    route_matchers = [(_route_pattern_to_regex(route.route_pattern), route) for route in routes]

    for file_record in repo_index.files:
        text = file_record.path.read_text(encoding="utf-8", errors="ignore")
        if file_record.language in {"typescript", "javascript"}:
            for fragment in _extract_client_route_fragments(text):
                call_id = node_id("http-call", file_record.relative_path, fragment["normalized"])
                nodes.upsert(
                    NodeRecord(
                        id=call_id,
                        label=NodeLabel.HTTP_CLIENT_CALL,
                        category=NodeCategory.SEMANTIC,
                        language=file_record.language,
                        file_path=file_record.relative_path,
                        properties={
                            "route_pattern": fragment["normalized"],
                            "raw_route": fragment["raw"],
                            "source_system": "frontend",
                            "target_system": "backend",
                        },
                    )
                )
                _connect_file_to_node(file_nodes, edges, file_record.relative_path, call_id)
                matched = False
                for matcher, route in route_matchers:
                    if matcher.fullmatch(fragment["normalized"]):
                        confidence = 0.99 if "{" not in fragment["normalized"] else 0.91
                        _add_edge(
                            edges,
                            EdgeRecord(
                                id=edge_id(
                                    EdgeLabel.HTTP_CALLS_ROUTE,
                                    call_id,
                                    route.node_id,
                                    fragment["normalized"],
                                ),
                                label=EdgeLabel.HTTP_CALLS_ROUTE,
                                src=call_id,
                                dst=route.node_id,
                                category=EdgeCategory.SEMANTIC,
                                properties={
                                    "confidence": confidence,
                                    "inferred": confidence < 0.99,
                                    "source_system": "frontend",
                                    "target_system": "backend",
                                    "contract_kind": "http",
                                    "route_pattern": route.route_pattern,
                                    "api_method": route.method,
                                },
                            ),
                        )
                        route_frontend_hits.add(route.node_id)
                        matched = True
                if not matched:
                    metrics.missing_route_bindings += 1

        if file_record.language == "python":
            route_nodes = routes_by_file.get(file_record.relative_path, [])
            task_nodes = tasks_by_file.get(file_record.relative_path, [])
            db_refs = _extract_db_references(text)
            if route_nodes and db_refs:
                metrics.schema_touching_handlers += len(route_nodes)
            for ref in db_refs:
                entity_id = _ensure_db_entity_node(
                    nodes,
                    db_entities,
                    ref["entity_kind"],
                    ref["name"],
                    ref.get("table_name", ""),
                    file_record.language,
                    file_record.relative_path,
                    {
                        "referenced_in_code": True,
                        "code_references": 1,
                        "branch_visible": False,
                        "defined_in_migration": False,
                        "source_system": "database",
                        "name": ref["name"],
                        "entity_kind": ref["entity_kind"],
                        "table_name": ref.get("table_name", ""),
                    },
                )
                for route in route_nodes:
                    edge_label = _db_edge_label(ref["entity_kind"], ref["operation"])
                    _add_edge(
                        edges,
                        EdgeRecord(
                            id=edge_id(
                                edge_label,
                                route.node_id,
                                entity_id,
                                ref["name"],
                                ref["operation"],
                            ),
                            label=edge_label,
                            src=route.node_id,
                            dst=entity_id,
                            category=EdgeCategory.SEMANTIC,
                            properties={
                                "confidence": 0.96,
                                "inferred": False,
                                "source_system": "backend",
                                "target_system": "database",
                                "table_name": ref.get("table_name", ref["name"]),
                                "column_name": ref["name"]
                                if ref["entity_kind"] == "column"
                                else "",
                                "rpc_name": ref["name"] if ref["entity_kind"] == "rpc" else "",
                                "operation": ref["operation"],
                            },
                        ),
                    )
                    schema_links_by_route.add(route.node_id)
                    _attach_rls_edges(edges, nodes, route, ref, policies_by_table)
                for task in task_nodes:
                    _add_edge(
                        edges,
                        EdgeRecord(
                            id=edge_id(
                                EdgeLabel.TASK_CONSUMES, task.node_id, entity_id, ref["name"]
                            ),
                            label=EdgeLabel.TASK_CONSUMES,
                            src=task.node_id,
                            dst=entity_id,
                            category=EdgeCategory.SEMANTIC,
                            properties={
                                "confidence": 0.82,
                                "inferred": True,
                                "source_system": "worker",
                                "target_system": "database",
                                "table_name": ref.get("table_name", ref["name"]),
                            },
                        ),
                    )

            producers = _extract_task_sends(text)
            if producers:
                metrics.async_producers += len(producers)
            for producer in producers:
                producer_id = (
                    task_nodes[0].node_id
                    if task_nodes
                    else file_nodes.get(file_record.relative_path, "")
                )
                if not producer_id:
                    continue
                target_id = task_name_to_id.get(producer["task_name"])
                if target_id:
                    async_linked_producers.add(producer_id)
                    _add_edge(
                        edges,
                        EdgeRecord(
                            id=edge_id(
                                EdgeLabel.TASK_ENQUEUES,
                                producer_id,
                                target_id,
                                producer["task_name"],
                            ),
                            label=EdgeLabel.TASK_ENQUEUES,
                            src=producer_id,
                            dst=target_id,
                            category=EdgeCategory.SEMANTIC,
                            properties={
                                "confidence": producer["confidence"],
                                "inferred": producer["confidence"] < 0.99,
                                "source_system": "worker",
                                "target_system": "worker",
                                "task_name": producer["task_name"],
                            },
                        ),
                    )
                else:
                    unresolved_id = node_id(
                        "task",
                        file_record.relative_path,
                        producer["task_name"],
                        "unresolved",
                    )
                    nodes.upsert(
                        NodeRecord(
                            id=unresolved_id,
                            label=NodeLabel.TASK,
                            category=NodeCategory.SEMANTIC,
                            language=file_record.language,
                            file_path=file_record.relative_path,
                            properties={
                                "task_name": producer["task_name"],
                                "handler_name": "",
                                "auth_context": "unknown",
                                "unresolved": True,
                                "source_system": "worker",
                            },
                        )
                    )
                    _add_edge(
                        edges,
                        EdgeRecord(
                            id=edge_id(
                                EdgeLabel.TASK_ENQUEUES,
                                producer_id,
                                unresolved_id,
                                producer["task_name"],
                            ),
                            label=EdgeLabel.TASK_ENQUEUES,
                            src=producer_id,
                            dst=unresolved_id,
                            category=EdgeCategory.SEMANTIC,
                            properties={
                                "confidence": producer["confidence"],
                                "inferred": True,
                                "source_system": "worker",
                                "target_system": "worker",
                                "task_name": producer["task_name"],
                            },
                        ),
                    )
                    metrics.missing_task_bindings += 1

    metrics.routes_with_frontend_edges = len(route_frontend_hits)
    metrics.schema_linked_handlers = len(schema_links_by_route)
    metrics.linked_async_producers = len(async_linked_producers)
    if metrics.route_count and metrics.routes_with_frontend_edges / metrics.route_count < 0.35:
        metrics.low_stitcher_coverage = True
        metrics.missing_seam_categories.append("frontend_to_route")
    if (
        metrics.schema_touching_handlers
        and metrics.schema_linked_handlers / metrics.schema_touching_handlers < 0.75
    ):
        metrics.low_stitcher_coverage = True
        metrics.missing_seam_categories.append("route_to_schema")
    if metrics.async_producers and metrics.linked_async_producers / metrics.async_producers < 0.75:
        metrics.low_stitcher_coverage = True
        metrics.missing_seam_categories.append("producer_to_consumer")

    return nodes.values(), list(edges.values()), metrics.as_dict()


def _migration_files(repo_root: Path) -> list[Path]:
    mig_root = repo_root / "supabase" / "migrations"
    if not mig_root.exists():
        return []
    return sorted(path for path in mig_root.glob("*.sql") if path.is_file())


def _parse_migration_file(
    repo_index: RepoIndex,
    migration: Path,
    migration_node_id: str,
    migration_order: int,
    nodes: NodeAccumulator,
    edges: dict[str, EdgeRecord],
    db_entities: dict[tuple[str, str, str], str],
    policies_by_table: dict[str, list[str]],
) -> None:
    content = migration.read_text(encoding="utf-8", errors="ignore")
    rel_path = migration.relative_to(repo_index.repo_root).as_posix()
    for table_name, block in CREATE_TABLE_RE.findall(content):
        table_id = _ensure_db_entity_node(
            nodes,
            db_entities,
            "table",
            table_name,
            "",
            "sql",
            rel_path,
            {
                "defined_in_migration": True,
                "branch_visible": True,
                "migration_id": migration.name,
                "migration_order": migration_order,
                "name": table_name,
                "entity_kind": "table",
                "source_system": "database",
            },
        )
        _add_edge(
            edges,
            EdgeRecord(
                id=edge_id(EdgeLabel.SCHEMA_DEFINED_BY_MIGRATION, table_id, migration_node_id),
                label=EdgeLabel.SCHEMA_DEFINED_BY_MIGRATION,
                src=table_id,
                dst=migration_node_id,
                category=EdgeCategory.SEMANTIC,
                properties={"source_system": "database", "target_system": "database"},
            ),
        )
        for raw_line in block.splitlines():
            line = raw_line.strip().rstrip(",")
            if not line or line.lower().startswith(
                ("primary key", "foreign key", "constraint", "unique", "check")
            ):
                continue
            parts = line.split()
            column_name = parts[0]
            if column_name.lower() in {"primary", "foreign", "constraint"}:
                continue
            column_id = _ensure_db_entity_node(
                nodes,
                db_entities,
                "column",
                column_name,
                table_name,
                "sql",
                rel_path,
                {
                    "defined_in_migration": True,
                    "branch_visible": True,
                    "migration_id": migration.name,
                    "migration_order": migration_order,
                    "name": column_name,
                    "table_name": table_name,
                    "entity_kind": "column",
                    "source_system": "database",
                },
            )
            _add_edge(
                edges,
                EdgeRecord(
                    id=edge_id(EdgeLabel.DEFINES, table_id, column_id, column_name),
                    label=EdgeLabel.DEFINES,
                    src=table_id,
                    dst=column_id,
                    category=EdgeCategory.SEMANTIC,
                    properties={"source_system": "database", "target_system": "database"},
                ),
            )
            _add_edge(
                edges,
                EdgeRecord(
                    id=edge_id(
                        EdgeLabel.SCHEMA_DEFINED_BY_MIGRATION,
                        column_id,
                        migration_node_id,
                    ),
                    label=EdgeLabel.SCHEMA_DEFINED_BY_MIGRATION,
                    src=column_id,
                    dst=migration_node_id,
                    category=EdgeCategory.SEMANTIC,
                    properties={"source_system": "database", "target_system": "database"},
                ),
            )

    for rpc_name in CREATE_FUNCTION_RE.findall(content):
        rpc_id = _ensure_db_entity_node(
            nodes,
            db_entities,
            "rpc",
            rpc_name,
            "",
            "sql",
            rel_path,
            {
                "defined_in_migration": True,
                "branch_visible": True,
                "migration_id": migration.name,
                "migration_order": migration_order,
                "name": rpc_name,
                "entity_kind": "rpc",
                "source_system": "database",
            },
        )
        _add_edge(
            edges,
            EdgeRecord(
                id=edge_id(EdgeLabel.SCHEMA_DEFINED_BY_MIGRATION, rpc_id, migration_node_id),
                label=EdgeLabel.SCHEMA_DEFINED_BY_MIGRATION,
                src=rpc_id,
                dst=migration_node_id,
                category=EdgeCategory.SEMANTIC,
                properties={"source_system": "database", "target_system": "database"},
            ),
        )

    for policy_name, table_name, command in POLICY_RE.findall(content):
        policy_id = node_id("rls", migration.name, table_name, command.lower(), policy_name)
        predicate = _policy_predicate(content, policy_name)
        nodes.upsert(
            NodeRecord(
                id=policy_id,
                label=NodeLabel.RLS_POLICY,
                category=NodeCategory.SEMANTIC,
                language="sql",
                file_path=rel_path,
                properties={
                    "policy_name": policy_name,
                    "table_name": table_name,
                    "rls_command": command.lower(),
                    "predicate_summary": predicate[:180],
                    "auth_context_required": "auth.uid" in predicate or "auth.role" in predicate,
                    "migration_id": migration.name,
                    "migration_order": migration_order,
                    "source_system": "database",
                },
            )
        )
        policies_by_table.setdefault(table_name, []).append(policy_id)
        table_id = _ensure_db_entity_node(
            nodes,
            db_entities,
            "table",
            table_name,
            "",
            "sql",
            rel_path,
            {
                "defined_in_migration": True,
                "branch_visible": True,
                "migration_id": migration.name,
                "migration_order": migration_order,
                "name": table_name,
                "entity_kind": "table",
                "source_system": "database",
            },
        )
        _add_edge(
            edges,
            EdgeRecord(
                id=edge_id(EdgeLabel.DEFINES, table_id, policy_id, policy_name),
                label=EdgeLabel.DEFINES,
                src=table_id,
                dst=policy_id,
                category=EdgeCategory.SEMANTIC,
                properties={"source_system": "database", "target_system": "database"},
            ),
        )


def _parse_routes(
    file_path: str,
    text: str,
    language: str,
    nodes: NodeAccumulator,
) -> list[ParsedRoute]:
    routes: list[ParsedRoute] = []
    prefix_match = ROUTER_PREFIX_RE.search(text)
    router_prefix = prefix_match.group(1) if prefix_match else ""
    for match in ROUTE_DECORATOR_RE.finditer(text):
        method = match.group(1).upper()
        route_pattern = _join_route_prefix(router_prefix, match.group(2))
        tail = text[match.end() :]
        func = FUNCTION_RE.search(tail)
        if func is None:
            continue
        handler_name = func.group(1)
        block = tail[func.start() : func.start() + 500]
        auth_mode = (
            "explicit_guard"
            if any(
                marker in block
                for marker in (
                    "verify_user_or_api_key",
                    "verify_supabase_jwt",
                    "_assert_org_access",
                    "_assert_repo_org_access",
                )
            )
            else "public"
        )
        uses_service_role = (
            "get_supabase_admin" in block or "supabase=Depends(get_supabase_admin)" in block
        )
        route_node_id = node_id("route", file_path, method, route_pattern, handler_name)
        nodes.upsert(
            NodeRecord(
                id=route_node_id,
                label=NodeLabel.ROUTE,
                category=NodeCategory.SEMANTIC,
                language=language,
                file_path=file_path,
                properties={
                    "route_pattern": route_pattern,
                    "api_method": method,
                    "handler_name": handler_name,
                    "auth_mode": auth_mode,
                    "uses_service_role": uses_service_role,
                    "source_system": "backend",
                    "target_system": "backend",
                },
            )
        )
        routes.append(
            ParsedRoute(
                node_id=route_node_id,
                file_path=file_path,
                method=method,
                route_pattern=route_pattern,
                handler_name=handler_name,
                auth_mode=auth_mode,
                uses_service_role=uses_service_role,
            )
        )
    return routes


def _parse_tasks(file_path: str, text: str, nodes: NodeAccumulator) -> list[ParsedTask]:
    tasks: list[ParsedTask] = []
    for task_name, handler_name in CELERY_TASK_RE.findall(text):
        task_id = node_id("task", file_path, task_name, handler_name)
        auth_context = (
            "system" if "service_role" in text or "get_supabase_admin" in text else "worker"
        )
        nodes.upsert(
            NodeRecord(
                id=task_id,
                label=NodeLabel.TASK,
                category=NodeCategory.SEMANTIC,
                language="python",
                file_path=file_path,
                properties={
                    "task_name": task_name,
                    "handler_name": handler_name,
                    "auth_context": auth_context,
                    "source_system": "worker",
                    "target_system": "worker",
                },
            )
        )
        tasks.append(
            ParsedTask(
                node_id=task_id,
                file_path=file_path,
                task_name=task_name,
                handler_name=handler_name,
                auth_context=auth_context,
            )
        )
    return tasks


def _extract_client_route_fragments(text: str) -> list[dict[str, str]]:
    fragments: list[dict[str, str]] = []
    for _quote, payload in FETCH_LITERAL_RE.findall(text):
        raw = payload.strip()
        if "/v1/" not in raw:
            continue
        for route in V1_ROUTE_FRAGMENT_RE.findall(raw):
            normalized = _normalize_client_route(route)
            if normalized:
                fragments.append({"raw": raw, "normalized": normalized})
    return _dedupe_dicts(fragments)


def _extract_db_references(text: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for match in TABLE_CALL_RE.finditer(text):
        name = match.group(1)
        line = _line_for_offset(text, match.start())
        operation = "read" if any(marker in line for marker in READ_OP_MARKERS) else "write"
        refs.append(
            {
                "entity_kind": "table",
                "name": name,
                "operation": operation,
                "table_name": name,
            }
        )
    for match in RPC_CALL_RE.finditer(text):
        refs.append({"entity_kind": "rpc", "name": match.group(1), "operation": "call"})
    return refs


def _extract_task_sends(text: str) -> list[dict[str, Any]]:
    sends: list[dict[str, Any]] = []
    for task_name in SEND_TASK_RE.findall(text):
        sends.append({"task_name": task_name, "confidence": 0.99})
    for task_ref in DELAY_RE.findall(text):
        task_name = _normalize_task_ref(task_ref)
        if task_name:
            sends.append({"task_name": task_name, "confidence": 0.82})
    for task_ref in APPLY_ASYNC_RE.findall(text):
        task_name = _normalize_task_ref(task_ref)
        if task_name:
            sends.append({"task_name": task_name, "confidence": 0.82})
    return _dedupe_dicts(sends)


def _attach_rls_edges(
    edges: dict[str, EdgeRecord],
    nodes: NodeAccumulator,
    route: ParsedRoute,
    ref: dict[str, str],
    policies_by_table: dict[str, list[str]],
) -> None:
    table_name = ref.get("table_name") or ref["name"]
    if ref["entity_kind"] not in {"table", "column"}:
        return
    for policy_id in policies_by_table.get(table_name, []):
        policy = nodes.nodes[policy_id]
        command = str(policy.properties.get("rls_command") or "")
        coverage = _coverage_for_operation(ref["operation"], command)
        _add_edge(
            edges,
            EdgeRecord(
                id=edge_id(
                    EdgeLabel.ROUTE_GUARDED_BY_RLS, route.node_id, policy_id, table_name, command
                ),
                label=EdgeLabel.ROUTE_GUARDED_BY_RLS,
                src=route.node_id,
                dst=policy_id,
                category=EdgeCategory.SEMANTIC,
                properties={
                    "confidence": 0.88,
                    "inferred": True,
                    "source_system": "backend",
                    "target_system": "database",
                    "table_name": table_name,
                    "rls_coverage": coverage,
                    "auth_context_required": bool(policy.properties.get("auth_context_required")),
                },
            ),
        )


def _coverage_for_operation(operation: str, command: str) -> str:
    if operation == "read" and command == "select":
        return "full"
    if operation == "write" and command in {"insert", "update", "delete", "all"}:
        return "full"
    if operation == "call":
        return "partial_predicate"
    return "partial_operation"


def _ensure_db_entity_node(
    nodes: NodeAccumulator,
    db_entities: dict[tuple[str, str, str], str],
    entity_kind: str,
    name: str,
    table_name: str,
    language: str,
    file_path: str,
    properties: dict[str, Any],
) -> str:
    key = (entity_kind, table_name, name)
    existing = db_entities.get(key)
    if existing:
        node = nodes.nodes[existing]
        node.properties = _merge_props(node.properties, properties)
        if properties.get("code_references"):
            node.properties["code_references"] = int(
                node.properties.get("code_references") or 0
            ) + int(properties["code_references"])
        return existing
    entity_id = node_id("db-entity", entity_kind, table_name, name)
    db_entities[key] = entity_id
    nodes.upsert(
        NodeRecord(
            id=entity_id,
            label=NodeLabel.DATABASE_ENTITY,
            category=NodeCategory.SEMANTIC,
            language=language,
            file_path=file_path,
            properties=properties,
        )
    )
    return entity_id


def _db_edge_label(entity_kind: str, operation: str) -> str:
    if entity_kind == "rpc":
        return EdgeLabel.ROUTE_CALLS_RPC
    if operation == "write":
        return EdgeLabel.ROUTE_WRITES_TABLE
    return EdgeLabel.ROUTE_READS_TABLE


def _connect_file_to_node(
    file_nodes: dict[str, str],
    edges: dict[str, EdgeRecord],
    file_path: str,
    semantic_node_id: str,
) -> None:
    file_id = file_nodes.get(file_path)
    if not file_id:
        return
    _add_edge(
        edges,
        EdgeRecord(
            id=edge_id(EdgeLabel.DEFINES, file_id, semantic_node_id),
            label=EdgeLabel.DEFINES,
            src=file_id,
            dst=semantic_node_id,
            category=EdgeCategory.SEMANTIC,
            properties={"source_system": "repo", "target_system": "semantic"},
        ),
    )


def _add_edge(edges: dict[str, EdgeRecord], edge: EdgeRecord) -> None:
    edges[edge.id] = edge


def _route_pattern_to_regex(pattern: str) -> re.Pattern[str]:
    normalized = _normalize_backend_route(pattern)
    escaped = re.escape(normalized)
    escaped = re.sub(r"\\\{[^/]+\\\}", r"[^/]+", escaped)
    return re.compile(f"^{escaped}$")


def _normalize_client_route(raw: str) -> str:
    value = raw.replace("${apiBase()}", "")
    value = re.sub(r"\$\{[^}]+\}", "{param}", value)
    if "?" in value:
        value = value.split("?", 1)[0]
    return value.strip()


def _normalize_backend_route(raw: str) -> str:
    if "?" in raw:
        raw = raw.split("?", 1)[0]
    return raw.strip()


def _join_route_prefix(prefix: str, route: str) -> str:
    if not prefix:
        return route
    return f"{prefix.rstrip('/')}/{route.lstrip('/')}"


def _line_for_offset(text: str, offset: int) -> str:
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    if end == -1:
        end = len(text)
    return text[start:end]


def _normalize_task_ref(value: str) -> str:
    if value.endswith("_task"):
        return f"dm.{value[:-5]}"
    return ""


def _policy_predicate(content: str, policy_name: str) -> str:
    marker = f'"{policy_name}"'
    start = content.find(marker)
    if start == -1:
        return ""
    end = content.find(";", start)
    if end == -1:
        end = min(len(content), start + 250)
    return " ".join(content[start:end].split())


def _merge_props(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if key not in merged:
            merged[key] = value
            continue
        current = merged[key]
        if isinstance(current, bool) and isinstance(value, bool):
            merged[key] = current or value
        elif isinstance(current, int) and isinstance(value, int):
            merged[key] = max(current, value)
        elif isinstance(current, list) or isinstance(value, list):
            items = []
            for item in [current, value]:
                if isinstance(item, list):
                    items.extend(item)
                else:
                    items.append(item)
            merged[key] = sorted({item for item in items if item not in {None, ""}})
        elif current in {None, "", False} and value not in {None, ""}:
            merged[key] = value
        else:
            merged[key] = current
    return merged


def _dedupe_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, Any], ...]] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = tuple(sorted(item.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
