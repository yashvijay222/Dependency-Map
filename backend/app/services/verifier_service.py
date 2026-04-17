"""Deterministic verifier service for surfaced analysis findings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class VerifierAudit:
    finding_id: str
    status: str
    checks_run: list[dict[str, Any]]
    passed_checks: list[dict[str, Any]]
    failed_checks: list[dict[str, Any]]
    provenance: list[str]
    withhold_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "status": self.status,
            "checks_run": self.checks_run,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "provenance": self.provenance,
            "withhold_reason": self.withhold_reason,
        }


def evaluate_offline_finding(finding: dict[str, Any]) -> VerifierAudit:
    verification = dict(finding.get("verification") or {})
    checks = list(verification.get("checks") or [])
    outcome = str(verification.get("outcome") or "unconfirmed")
    surfaced = bool(verification.get("surfaced"))
    status = "verified" if surfaced else "withheld"
    withhold_reason = None if surfaced else outcome
    return VerifierAudit(
        finding_id=str(finding.get("finding_id") or ""),
        status=status,
        checks_run=checks,
        passed_checks=[check for check in checks if check.get("passed")],
        failed_checks=[check for check in checks if not check.get("passed")],
        provenance=["deterministic_verifier", "offline_cpg"],
        withhold_reason=withhold_reason,
    )


def summarize_audits(audits: list[VerifierAudit]) -> dict[str, int]:
    verified = sum(1 for audit in audits if audit.status == "verified")
    withheld = sum(1 for audit in audits if audit.status == "withheld")
    return {"verified": verified, "withheld": withheld}
