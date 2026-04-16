from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class InvariantSpec:
    id: str
    severity: str
    seed_selector: str
    allowed_edge_families: list[str]
    path_constraints: dict[str, Any]
    verifier_checks: list[str]
    max_seeds_per_diff: int
    max_paths_per_seed: int
    max_tokens_per_pack: int
    truncation_order: list[str]
    partially_confirmed_policy: dict[str, Any]
    min_edge_confidence_for_confirmed: float
    min_edge_confidence_for_partially_confirmed: float
    description: str = ""
    tags: list[str] = field(default_factory=list)


DEFAULT_TRUNCATION_ORDER = [
    "drop_neighborhood_summaries",
    "trim_diff_snippets",
    "drop_alternate_paths",
    "trim_path_tails",
]


def default_invariants() -> list[InvariantSpec]:
    return [
        InvariantSpec(
            id="schema_entity_still_referenced",
            severity="high",
            seed_selector="changed_or_unbound_schema_entities",
            allowed_edge_families=[
                "ROUTE_READS_TABLE",
                "ROUTE_WRITES_TABLE",
                "ROUTE_CALLS_RPC",
                "HTTP_CALLS_ROUTE",
            ],
            path_constraints={"max_hops": 4, "branch_factor": 8},
            verifier_checks=[
                "entity_referenced_in_code",
                "entity_defined_in_branch",
                "entity_removed_or_missing",
                "seam_path_present",
            ],
            max_seeds_per_diff=24,
            max_paths_per_seed=3,
            max_tokens_per_pack=1400,
            truncation_order=list(DEFAULT_TRUNCATION_ORDER),
            partially_confirmed_policy={
                "min_passed_checks": 2,
                "require_seam_critical": True,
                "allow_contradictions": False,
            },
            min_edge_confidence_for_confirmed=0.85,
            min_edge_confidence_for_partially_confirmed=0.55,
            description=(
                "Code still references schema entities that are absent "
                "or removed in the analyzed branch."
            ),
            tags=["schema", "diff", "supabase"],
        ),
        InvariantSpec(
            id="frontend_route_binding",
            severity="medium",
            seed_selector="frontend_http_calls",
            allowed_edge_families=["HTTP_CALLS_ROUTE"],
            path_constraints={"max_hops": 2, "branch_factor": 6},
            verifier_checks=[
                "frontend_call_present",
                "route_exists",
                "stitcher_coverage_sufficient",
            ],
            max_seeds_per_diff=32,
            max_paths_per_seed=2,
            max_tokens_per_pack=1000,
            truncation_order=list(DEFAULT_TRUNCATION_ORDER),
            partially_confirmed_policy={
                "min_passed_checks": 2,
                "require_seam_critical": True,
                "allow_contradictions": False,
            },
            min_edge_confidence_for_confirmed=0.95,
            min_edge_confidence_for_partially_confirmed=0.65,
            description="Frontend API calls should bind to a live FastAPI route.",
            tags=["frontend", "backend", "http"],
        ),
        InvariantSpec(
            id="missing_guard_or_rls_gap",
            severity="high",
            seed_selector="routes_touching_schema",
            allowed_edge_families=[
                "ROUTE_READS_TABLE",
                "ROUTE_WRITES_TABLE",
                "ROUTE_GUARDED_BY_RLS",
            ],
            path_constraints={"max_hops": 3, "branch_factor": 8},
            verifier_checks=[
                "route_touches_schema",
                "explicit_guard_present",
                "rls_coverage_verdict",
            ],
            max_seeds_per_diff=20,
            max_paths_per_seed=3,
            max_tokens_per_pack=1200,
            truncation_order=list(DEFAULT_TRUNCATION_ORDER),
            partially_confirmed_policy={
                "min_passed_checks": 2,
                "require_seam_critical": True,
                "allow_contradictions": False,
            },
            min_edge_confidence_for_confirmed=0.8,
            min_edge_confidence_for_partially_confirmed=0.5,
            description=(
                "Routes that touch protected schema should have an explicit "
                "guard or trustworthy RLS coverage."
            ),
            tags=["auth", "rls", "backend"],
        ),
        InvariantSpec(
            id="celery_task_binding",
            severity="medium",
            seed_selector="async_producers",
            allowed_edge_families=["TASK_ENQUEUES"],
            path_constraints={"max_hops": 2, "branch_factor": 6},
            verifier_checks=["task_enqueued", "task_target_resolved"],
            max_seeds_per_diff=20,
            max_paths_per_seed=2,
            max_tokens_per_pack=900,
            truncation_order=list(DEFAULT_TRUNCATION_ORDER),
            partially_confirmed_policy={
                "min_passed_checks": 2,
                "require_seam_critical": True,
                "allow_contradictions": False,
            },
            min_edge_confidence_for_confirmed=0.9,
            min_edge_confidence_for_partially_confirmed=0.6,
            description="Celery task producers should target resolvable task consumers.",
            tags=["celery", "worker"],
        ),
    ]


def invariants_by_id() -> dict[str, InvariantSpec]:
    return {spec.id: spec for spec in default_invariants()}
