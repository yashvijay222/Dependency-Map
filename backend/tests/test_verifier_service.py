from app.services.verifier_service import evaluate_offline_finding, summarize_audits


def test_evaluate_offline_finding_verified() -> None:
    audit = evaluate_offline_finding(
        {
            "finding_id": "cand:1",
            "verification": {
                "surfaced": True,
                "outcome": "confirmed",
                "checks": [
                    {"name": "route_exists", "passed": True, "seam_critical": True},
                ],
            },
        }
    )

    assert audit.status == "verified"
    assert audit.withhold_reason is None
    assert len(audit.passed_checks) == 1


def test_evaluate_offline_finding_withheld() -> None:
    audit = evaluate_offline_finding(
        {
            "finding_id": "cand:2",
            "verification": {
                "surfaced": False,
                "outcome": "unconfirmed",
                "checks": [
                    {"name": "entity_defined_in_branch", "passed": False, "seam_critical": True},
                ],
            },
        }
    )

    summary = summarize_audits([audit])

    assert audit.status == "withheld"
    assert audit.withhold_reason == "unconfirmed"
    assert len(audit.failed_checks) == 1
    assert summary == {"verified": 0, "withheld": 1}
