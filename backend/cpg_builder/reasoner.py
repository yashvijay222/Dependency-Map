from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .reasoner_providers import (
    call_gemini_reasoner,
    call_openai_compatible_reasoner,
    validate_reasoner_json,
)

if TYPE_CHECKING:
    from .path_miner import CandidatePath


@dataclass(slots=True)
class ReasonerResult:
    status: str
    output: dict[str, Any] | None
    error: str | None = None
    confidence: float | None = None


def append_reasoner_training_row(path: str | None, row: dict[str, Any]) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str) + "\n")


class HostedGemmaReasoner:
    def __init__(self) -> None:
        self.provider = (os.getenv("CPG_REASONER_PROVIDER") or "").strip().lower()

    def reason(self, evidence_pack: dict[str, Any]) -> ReasonerResult:
        training_path = (os.getenv("CPG_REASONER_TRAINING_JSONL") or "").strip() or None

        if self.provider in {"", "unconfigured"}:
            return ReasonerResult(
                status="reasoning_unavailable",
                output=None,
                error="Hosted reasoner provider is not configured (set CPG_REASONER_PROVIDER)",
            )

        if self.provider == "stub":
            result = self._stub_reason(evidence_pack)
            if result.output and training_path:
                append_reasoner_training_row(
                    training_path,
                    {
                        "provider": "stub",
                        "evidence_pack": evidence_pack,
                        "reasoner_output": result.output,
                        "created_at": datetime.now(UTC).isoformat(),
                    },
                )
            return result

        if self.provider in {"openai", "openai_compatible"}:
            parsed, err = call_openai_compatible_reasoner(evidence_pack)
            if err or not parsed:
                return ReasonerResult(
                    status="reasoner_failed",
                    output=None,
                    error=err or "empty model output",
                )
            conf = float(parsed.get("confidence", 0.5))
            if training_path:
                append_reasoner_training_row(
                    training_path,
                    {
                        "provider": "openai",
                        "evidence_pack": evidence_pack,
                        "reasoner_output": parsed,
                        "created_at": datetime.now(UTC).isoformat(),
                    },
                )
            return ReasonerResult(status="ok", output=parsed, error=None, confidence=conf)

        if self.provider in {"gemini", "google", "gemma"}:
            parsed, err = call_gemini_reasoner(evidence_pack)
            if err or not parsed:
                return ReasonerResult(
                    status="reasoner_failed",
                    output=None,
                    error=err or "empty model output",
                )
            conf = float(parsed.get("confidence", 0.5))
            if training_path:
                append_reasoner_training_row(
                    training_path,
                    {
                        "provider": self.provider,
                        "evidence_pack": evidence_pack,
                        "reasoner_output": parsed,
                        "created_at": datetime.now(UTC).isoformat(),
                    },
                )
            return ReasonerResult(status="ok", output=parsed, error=None, confidence=conf)

        return ReasonerResult(
            status="reasoning_unavailable",
            output=None,
            error=f"Unknown CPG_REASONER_PROVIDER={self.provider!r}",
        )

    def replayable_entry(
        self,
        evidence_pack: dict[str, Any],
        *,
        run_id: str,
        ttl_seconds: int = 86400,
        candidate_path: CandidatePath | None = None,
    ) -> dict[str, Any]:
        from .path_miner import serialize_candidate_path

        created_at = datetime.now(UTC)
        entry: dict[str, Any] = {
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "expires_at": created_at.timestamp() + ttl_seconds,
            "provider": self.provider or "unconfigured",
            "evidence_pack": evidence_pack,
            "cached_rank_score": evidence_pack.get("rank_score"),
            "cached_rank_phase": evidence_pack.get("rank_phase"),
        }
        if candidate_path is not None:
            entry["candidate_path"] = serialize_candidate_path(candidate_path)
        return entry

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
            "confidence": float(evidence_pack.get("rank_score") or 0.5),
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
        ok, err = validate_reasoner_json(output)
        if not ok:
            return ReasonerResult(status="reasoner_failed", output=None, error=err)
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
