from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx

from .invariants import InvariantSpec
from .path_miner import CandidatePath


@dataclass(slots=True)
class VerificationResult:
    outcome: str
    surfaced: bool
    checks: list[dict[str, Any]]
    caveats: list[str]
    rls_coverage_verdict: str
    effective_edge_confidence_floor: float
    contradiction_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "surfaced": self.surfaced,
            "checks": self.checks,
            "caveats": self.caveats,
            "rls_coverage_verdict": self.rls_coverage_verdict,
            "effective_edge_confidence_floor": self.effective_edge_confidence_floor,
            "contradiction_count": self.contradiction_count,
        }


def verify_candidate(
    graph: nx.MultiDiGraph,
    spec: InvariantSpec,
    candidate: CandidatePath,
    reasoner_output: dict[str, Any] | None,
    *,
    stitcher_coverage_state: str,
) -> VerificationResult:
    checks: list[dict[str, Any]] = []
    caveats: list[str] = []
    contradiction_count = 0
    rls_verdict = "none"
    edge_floor = _edge_confidence_floor(graph, candidate.edge_ids)
    facts = candidate.facts

    if candidate.invariant_id == "schema_entity_still_referenced":
        checks.append(
            _check("entity_referenced_in_code", bool(facts.get("referenced_in_code")), True)
        )
        defined = bool(facts.get("defined_in_migration", True))
        checks.append(_check("entity_defined_in_branch", not defined, True))
        checks.append(_check("seam_path_present", len(candidate.node_ids) >= 1, True))
        contradiction_count += int(defined)
    elif candidate.invariant_id == "frontend_route_binding":
        matched = bool(facts.get("matched_route_id"))
        checks.append(_check("frontend_call_present", True, True))
        checks.append(_check("route_exists", not matched, True))
        checks.append(
            _check(
                "stitcher_coverage_sufficient",
                stitcher_coverage_state != "low_stitcher_coverage",
                False,
            )
        )
        contradiction_count += int(matched)
        if stitcher_coverage_state == "low_stitcher_coverage":
            caveats.append("Low stitcher coverage reduces certainty for route binding findings.")
    elif candidate.invariant_id == "missing_guard_or_rls_gap":
        auth_mode = str(facts.get("auth_mode") or "")
        uses_service_role = bool(facts.get("uses_service_role"))
        rls_verdict = _rls_verdict(graph, candidate.node_ids[0], uses_service_role)
        checks.append(_check("route_touches_schema", len(candidate.node_ids) > 1, True))
        checks.append(_check("explicit_guard_present", auth_mode != "explicit_guard", True))
        checks.append(
            _check(
                "rls_coverage_verdict",
                rls_verdict
                in {"none", "partial_operation", "partial_predicate", "context_mismatch"},
                True,
            )
        )
        contradiction_count += int(auth_mode == "explicit_guard")
        if rls_verdict != "none":
            caveats.append(f"RLS coverage verdict: {rls_verdict}")
    elif candidate.invariant_id == "celery_task_binding":
        unresolved = bool(facts.get("target_unresolved"))
        checks.append(_check("task_enqueued", True, True))
        checks.append(_check("task_target_resolved", unresolved, True))
        contradiction_count += int(not unresolved)

    if edge_floor < spec.min_edge_confidence_for_partially_confirmed:
        caveats.append("Inferred seam confidence is below the minimum surfacing threshold.")
        return VerificationResult(
            outcome="unconfirmed",
            surfaced=False,
            checks=checks,
            caveats=caveats,
            rls_coverage_verdict=rls_verdict,
            effective_edge_confidence_floor=edge_floor,
            contradiction_count=contradiction_count,
        )

    passed_count = sum(1 for check in checks if check["passed"])
    seam_critical_passed = any(check["passed"] and check["seam_critical"] for check in checks)
    allow_confirmed = edge_floor >= spec.min_edge_confidence_for_confirmed
    outcome = "unconfirmed"
    surfaced = False

    if contradiction_count and reasoner_output and reasoner_output.get("violation", True):
        outcome = "invalid_reasoning"
    elif contradiction_count:
        outcome = "unconfirmed"
    elif passed_count >= len(checks) and seam_critical_passed and allow_confirmed:
        outcome = "confirmed"
        surfaced = True
    elif (
        passed_count >= int(spec.partially_confirmed_policy.get("min_passed_checks", 2))
        and seam_critical_passed
        and not contradiction_count
    ):
        outcome = "partially_confirmed"
        surfaced = True
    if candidate.invariant_id == "missing_guard_or_rls_gap" and rls_verdict in {
        "partial_operation",
        "partial_predicate",
        "context_mismatch",
    }:
        outcome = "partially_confirmed" if surfaced or passed_count >= 2 else "unconfirmed"
        surfaced = outcome == "partially_confirmed"
    if not allow_confirmed and outcome == "confirmed":
        outcome = "partially_confirmed"
    return VerificationResult(
        outcome=outcome,
        surfaced=surfaced,
        checks=checks,
        caveats=caveats,
        rls_coverage_verdict=rls_verdict,
        effective_edge_confidence_floor=edge_floor,
        contradiction_count=contradiction_count,
    )


def _check(name: str, passed: bool, seam_critical: bool) -> dict[str, Any]:
    return {"name": name, "passed": passed, "seam_critical": seam_critical}


def _edge_confidence_floor(graph: nx.MultiDiGraph, edge_ids: list[str]) -> float:
    confidence = 1.0
    for edge_id in edge_ids:
        found = False
        for _src, _dst, key, attrs in graph.edges(keys=True, data=True):
            if str(key) != edge_id:
                continue
            confidence = min(confidence, float(attrs.get("confidence", 1.0)))
            found = True
            break
        if not found:
            confidence = min(confidence, 0.5)
    return round(confidence, 4)


def _rls_verdict(graph: nx.MultiDiGraph, route_id: str, uses_service_role: bool) -> str:
    coverages: list[str] = []
    auth_context_required = False
    for _src, _dst, _key, attrs in graph.out_edges(route_id, keys=True, data=True):
        if attrs.get("label") != "ROUTE_GUARDED_BY_RLS":
            continue
        coverages.append(str(attrs.get("rls_coverage") or "none"))
        auth_context_required = auth_context_required or bool(attrs.get("auth_context_required"))
    if not coverages:
        return "none"
    if uses_service_role and auth_context_required:
        return "context_mismatch"
    if all(item == "full" for item in coverages):
        return "full"
    if any(item == "partial_operation" for item in coverages):
        return "partial_operation"
    if any(item == "partial_predicate" for item in coverages):
        return "partial_predicate"
    return "none"
