from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx

from .invariants import InvariantSpec
from .schema import EdgeLabel, NodeLabel
from .utils import stable_id


@dataclass(slots=True)
class CandidatePath:
    id: str
    invariant_id: str
    seed_id: str
    node_ids: list[str]
    edge_ids: list[str]
    seam_type: str
    changed_anchors: list[str]
    heuristic_features: dict[str, Any]
    facts: dict[str, Any]


def mine_candidate_paths(
    graph: nx.MultiDiGraph,
    invariants: list[InvariantSpec],
    diff_payload: dict[str, Any] | None = None,
) -> list[CandidatePath]:
    changed_ids = _changed_ids(diff_payload)
    candidates: list[CandidatePath] = []
    for spec in invariants:
        if spec.id == "schema_entity_still_referenced":
            candidates.extend(_mine_schema_candidates(graph, spec, changed_ids))
        elif spec.id == "frontend_route_binding":
            candidates.extend(_mine_route_candidates(graph, spec, changed_ids))
        elif spec.id == "missing_guard_or_rls_gap":
            candidates.extend(_mine_guard_candidates(graph, spec, changed_ids))
        elif spec.id == "celery_task_binding":
            candidates.extend(_mine_task_candidates(graph, spec, changed_ids))
    return _dedupe_candidates(candidates)


def _mine_schema_candidates(
    graph: nx.MultiDiGraph,
    spec: InvariantSpec,
    changed_ids: set[str],
) -> list[CandidatePath]:
    db_nodes = [
        (node_id, attrs)
        for node_id, attrs in graph.nodes(data=True)
        if attrs.get("label") == NodeLabel.DATABASE_ENTITY
        and (
            not attrs.get("defined_in_migration", False)
            or node_id in changed_ids
            or attrs.get("referenced_in_code")
        )
    ]
    db_nodes = sorted(
        db_nodes,
        key=lambda item: (
            item[0] not in changed_ids,
            not item[1].get("referenced_in_code", False),
            item[1].get("name", ""),
        ),
    )[: spec.max_seeds_per_diff]
    candidates: list[CandidatePath] = []
    for node_id, attrs in db_nodes:
        predecessors = _predecessor_candidates(
            graph,
            node_id,
            {EdgeLabel.ROUTE_READS_TABLE, EdgeLabel.ROUTE_WRITES_TABLE, EdgeLabel.ROUTE_CALLS_RPC},
        )
        if not predecessors:
            predecessors = [node_id]
        for predecessor in predecessors[: spec.max_paths_per_seed]:
            node_ids = [predecessor, node_id] if predecessor != node_id else [node_id]
            edge_ids = _edge_ids_for_path(graph, node_ids)
            candidates.append(
                CandidatePath(
                    id=f"cand:{stable_id(spec.id, predecessor, node_id)}",
                    invariant_id=spec.id,
                    seed_id=node_id,
                    node_ids=node_ids,
                    edge_ids=edge_ids,
                    seam_type="schema",
                    changed_anchors=[nid for nid in node_ids if nid in changed_ids],
                    heuristic_features={
                        "changed_anchor_count": sum(1 for nid in node_ids if nid in changed_ids),
                        "referenced_in_code": bool(attrs.get("referenced_in_code")),
                        "defined_in_migration": bool(attrs.get("defined_in_migration")),
                    },
                    facts={
                        "entity_name": attrs.get("name"),
                        "entity_kind": attrs.get("entity_kind"),
                        "defined_in_migration": bool(attrs.get("defined_in_migration")),
                        "referenced_in_code": bool(attrs.get("referenced_in_code")),
                    },
                )
            )
    return candidates


def _mine_route_candidates(
    graph: nx.MultiDiGraph,
    spec: InvariantSpec,
    changed_ids: set[str],
) -> list[CandidatePath]:
    client_calls = [
        (node_id, attrs)
        for node_id, attrs in graph.nodes(data=True)
        if attrs.get("label") == NodeLabel.HTTP_CLIENT_CALL
    ]
    client_calls = sorted(
        client_calls,
        key=lambda item: (item[0] not in changed_ids, item[1].get("route_pattern", "")),
    )[: spec.max_seeds_per_diff]
    candidates: list[CandidatePath] = []
    for node_id, attrs in client_calls:
        route_targets = _successor_candidates(graph, node_id, {EdgeLabel.HTTP_CALLS_ROUTE})
        target = route_targets[0] if route_targets else None
        node_ids = [node_id] + ([target] if target else [])
        edge_ids = _edge_ids_for_path(graph, node_ids)
        candidates.append(
            CandidatePath(
                id=f"cand:{stable_id(spec.id, node_id, target or 'missing')}",
                invariant_id=spec.id,
                seed_id=node_id,
                node_ids=node_ids,
                edge_ids=edge_ids,
                seam_type="http",
                changed_anchors=[nid for nid in node_ids if nid in changed_ids],
                heuristic_features={
                    "changed_anchor_count": sum(1 for nid in node_ids if nid in changed_ids),
                    "matched_route": target is not None,
                },
                facts={
                    "route_pattern": attrs.get("route_pattern"),
                    "matched_route_id": target,
                },
            )
        )
    return candidates


def _mine_guard_candidates(
    graph: nx.MultiDiGraph,
    spec: InvariantSpec,
    changed_ids: set[str],
) -> list[CandidatePath]:
    route_nodes = [
        (node_id, attrs)
        for node_id, attrs in graph.nodes(data=True)
        if attrs.get("label") == NodeLabel.ROUTE
    ]
    route_nodes = sorted(
        route_nodes,
        key=lambda item: (item[0] not in changed_ids, item[1].get("route_pattern", "")),
    )[: spec.max_seeds_per_diff]
    candidates: list[CandidatePath] = []
    for node_id, attrs in route_nodes:
        schema_targets = _successor_candidates(
            graph,
            node_id,
            {EdgeLabel.ROUTE_READS_TABLE, EdgeLabel.ROUTE_WRITES_TABLE},
        )
        if not schema_targets:
            continue
        node_ids = [node_id] + schema_targets[: spec.max_paths_per_seed]
        edge_ids = _edge_ids_for_path(graph, node_ids)
        candidates.append(
            CandidatePath(
                id=f"cand:{stable_id(spec.id, *node_ids)}",
                invariant_id=spec.id,
                seed_id=node_id,
                node_ids=node_ids,
                edge_ids=edge_ids,
                seam_type="auth",
                changed_anchors=[nid for nid in node_ids if nid in changed_ids],
                heuristic_features={
                    "changed_anchor_count": sum(1 for nid in node_ids if nid in changed_ids),
                    "explicit_guard": attrs.get("auth_mode") == "explicit_guard",
                    "uses_service_role": bool(attrs.get("uses_service_role")),
                },
                facts={
                    "route_pattern": attrs.get("route_pattern"),
                    "auth_mode": attrs.get("auth_mode"),
                    "uses_service_role": bool(attrs.get("uses_service_role")),
                    "schema_target_ids": schema_targets[: spec.max_paths_per_seed],
                },
            )
        )
    return candidates


def _mine_task_candidates(
    graph: nx.MultiDiGraph,
    spec: InvariantSpec,
    changed_ids: set[str],
) -> list[CandidatePath]:
    enqueues = []
    for src, dst, key, attrs in graph.edges(keys=True, data=True):
        if attrs.get("label") == EdgeLabel.TASK_ENQUEUES:
            enqueues.append((src, dst, key, attrs))
    enqueues = sorted(
        enqueues,
        key=lambda item: (
            item[0] not in changed_ids and item[1] not in changed_ids,
            item[3].get("task_name", ""),
        ),
    )[: spec.max_seeds_per_diff]
    candidates: list[CandidatePath] = []
    for src, dst, key, attrs in enqueues:
        candidates.append(
            CandidatePath(
                id=f"cand:{stable_id(spec.id, src, dst, key)}",
                invariant_id=spec.id,
                seed_id=src,
                node_ids=[src, dst],
                edge_ids=[key],
                seam_type="worker",
                changed_anchors=[nid for nid in (src, dst) if nid in changed_ids],
                heuristic_features={
                    "changed_anchor_count": sum(1 for nid in (src, dst) if nid in changed_ids),
                    "target_unresolved": bool(graph.nodes[dst].get("unresolved")),
                },
                facts={
                    "task_name": attrs.get("task_name"),
                    "target_unresolved": bool(graph.nodes[dst].get("unresolved")),
                },
            )
        )
    return candidates


def _changed_ids(diff_payload: dict[str, Any] | None) -> set[str]:
    if not diff_payload:
        return set()
    ids: set[str] = set()
    graph_diff = diff_payload.get("graph_diff") or diff_payload
    for item in graph_diff.get("added_nodes", []):
        if isinstance(item, dict) and item.get("id"):
            ids.add(str(item["id"]))
    for item in graph_diff.get("removed_nodes", []):
        if isinstance(item, dict) and item.get("id"):
            ids.add(str(item["id"]))
    for item in graph_diff.get("changed_nodes", []):
        before = item.get("before") if isinstance(item, dict) else None
        after = item.get("after") if isinstance(item, dict) else None
        for candidate in (before, after):
            if isinstance(candidate, dict) and candidate.get("id"):
                ids.add(str(candidate["id"]))
    return ids


def _predecessor_candidates(
    graph: nx.MultiDiGraph,
    node_id: str,
    labels: set[str],
) -> list[str]:
    out: list[str] = []
    for predecessor, _dst, _key, attrs in graph.in_edges(node_id, keys=True, data=True):
        if attrs.get("label") in labels:
            out.append(predecessor)
    return out


def _successor_candidates(
    graph: nx.MultiDiGraph,
    node_id: str,
    labels: set[str],
) -> list[str]:
    out: list[str] = []
    for _src, successor, _key, attrs in graph.out_edges(node_id, keys=True, data=True):
        if attrs.get("label") in labels:
            out.append(successor)
    return out


def _edge_ids_for_path(graph: nx.MultiDiGraph, node_ids: list[str]) -> list[str]:
    edge_ids: list[str] = []
    for left, right in zip(node_ids, node_ids[1:], strict=False):
        edge_data = graph.get_edge_data(left, right) or {}
        edge_ids.extend(str(key) for key in edge_data.keys())
    return edge_ids


def _dedupe_candidates(candidates: list[CandidatePath]) -> list[CandidatePath]:
    seen: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()
    out: list[CandidatePath] = []
    for candidate in candidates:
        key = (candidate.invariant_id, tuple(candidate.node_ids), tuple(candidate.changed_anchors))
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def serialize_candidate_path(candidate: CandidatePath) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "invariant_id": candidate.invariant_id,
        "seed_id": candidate.seed_id,
        "node_ids": candidate.node_ids,
        "edge_ids": candidate.edge_ids,
        "seam_type": candidate.seam_type,
        "changed_anchors": candidate.changed_anchors,
        "heuristic_features": dict(candidate.heuristic_features),
        "facts": dict(candidate.facts),
    }


def deserialize_candidate_path(data: dict[str, Any]) -> CandidatePath:
    return CandidatePath(
        id=str(data["id"]),
        invariant_id=str(data["invariant_id"]),
        seed_id=str(data["seed_id"]),
        node_ids=[str(x) for x in data.get("node_ids") or []],
        edge_ids=[str(x) for x in data.get("edge_ids") or []],
        seam_type=str(data.get("seam_type") or ""),
        changed_anchors=[str(x) for x in data.get("changed_anchors") or []],
        heuristic_features=dict(data.get("heuristic_features") or {}),
        facts=dict(data.get("facts") or {}),
    )
