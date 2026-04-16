from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class ReasonerResult:
    status: str
    output: dict[str, Any] | None
    error: str | None = None
    confidence: float | None = None


class HostedGemmaReasoner:
    def __init__(self) -> None:
        self.provider = (os.getenv("CPG_REASONER_PROVIDER") or "").strip().lower()

    def reason(self, evidence_pack: dict[str, Any]) -> ReasonerResult:
        if self.provider == "stub":
            return self._stub_reason(evidence_pack)
        return ReasonerResult(
            status="reasoning_unavailable",
            output=None,
            error="Hosted reasoner provider is not configured",
        )

    def replayable_entry(
        self,
        evidence_pack: dict[str, Any],
        *,
        run_id: str,
        ttl_seconds: int = 86400,
    ) -> dict[str, Any]:
        created_at = datetime.now(UTC)
        return {
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "expires_at": created_at.timestamp() + ttl_seconds,
            "provider": self.provider or "unconfigured",
            "evidence_pack": evidence_pack,
            "cached_rank_score": evidence_pack.get("rank_score"),
            "cached_rank_phase": evidence_pack.get("rank_phase"),
        }

    def _stub_reason(self, evidence_pack: dict[str, Any]) -> ReasonerResult:
        facts = evidence_pack.get("facts") or {}
        invariant_id = str(evidence_pack.get("invariant_id") or "")
        violation = False
        if invariant_id == "schema_entity_still_referenced":
            violation = bool(facts.get("referenced_in_code")) and not bool(
                facts.get("defined_in_migration", True)
            )
        elif invariant_id == "frontend_route_binding":
            violation = not bool(facts.get("matched_route_id"))
        elif invariant_id == "missing_guard_or_rls_gap":
            violation = facts.get("auth_mode") != "explicit_guard"
        elif invariant_id == "celery_task_binding":
            violation = bool(facts.get("target_unresolved"))
        output = {
            "violation": violation,
            "confidence": evidence_pack.get("rank_score", 0.5),
            "invariant_id": invariant_id,
            "witness_paths": evidence_pack.get("witness_paths", []),
            "broken_contract": facts,
            "missing_guard": evidence_pack.get("facts", {}).get("auth_mode") == "public",
            "affected_surfaces": evidence_pack.get("changed_anchors", []),
            "explanation": f"Stub reasoner evaluated invariant {invariant_id}",
            "recommended_fix": (
                "Inspect deterministic verifier output for the canonical "
                "remediation target."
            ),
        }
        return ReasonerResult(
            status="ok",
            output=output,
            confidence=float(output["confidence"]),
        )


def load_queue_entries(queue_path: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    with open(queue_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries
