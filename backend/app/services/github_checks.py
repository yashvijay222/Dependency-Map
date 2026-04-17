"""GitHub Check Runs and PR comments (Phase 3) using shared GitHub HTTP retry/429 handling."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.services.github_client import GITHUB_API, github_installation_http

log = logging.getLogger(__name__)

def upsert_pr_comment(
    token: str,
    full_name: str,
    pr_number: int,
    body: str,
    *,
    existing_comment_id: int | None = None,
) -> int | None:
    """Create or update a single Dependency Map comment. Returns comment id."""
    if not settings.feature_github_pr_comments:
        return None
    owner, repo = full_name.split("/", 1)
    if existing_comment_id:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/comments/{existing_comment_id}"
        r = github_installation_http(token, "PATCH", url, json_body={"body": body})
        if r.status_code >= 400:
            log.warning("github comment update failed: %s %s", r.status_code, r.text[:200])
            return None
        return existing_comment_id
    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{pr_number}/comments"
    r = github_installation_http(token, "POST", url, json_body={"body": body})
    if r.status_code >= 400:
        log.warning("github comment create failed: %s %s", r.status_code, r.text[:200])
        return None
    data = r.json()
    return int(data["id"]) if isinstance(data.get("id"), int) else None


def create_check_run(
    token: str,
    full_name: str,
    head_sha: str,
    name: str = "Dependency Map",
) -> int | None:
    if not settings.feature_github_check_runs:
        return None
    owner, repo = full_name.split("/", 1)
    url = f"{GITHUB_API}/repos/{owner}/{repo}/check-runs"
    payload: dict[str, Any] = {
        "name": name,
        "head_sha": head_sha,
        "status": "in_progress",
        "output": {
            "title": "Dependency Map analysis",
            "summary": "Running contract analysis…",
        },
    }
    r = github_installation_http(token, "POST", url, json_body=payload)
    if r.status_code >= 400:
        log.warning("github check run create failed: %s %s", r.status_code, r.text[:200])
        return None
    data = r.json()
    return int(data["id"]) if isinstance(data.get("id"), int) else None


def complete_check_run(
    token: str,
    full_name: str,
    check_run_id: int,
    conclusion: str,
    summary: str,
) -> None:
    if not settings.feature_github_check_runs or not check_run_id:
        return
    owner, repo = full_name.split("/", 1)
    url = f"{GITHUB_API}/repos/{owner}/{repo}/check-runs/{check_run_id}"
    payload = {
        "status": "completed",
        "conclusion": conclusion,
        "output": {"title": "Dependency Map", "summary": summary[:65000]},
    }
    r = github_installation_http(token, "PATCH", url, json_body=payload)
    if r.status_code >= 400:
        log.warning("github check run complete failed: %s %s", r.status_code, r.text[:200])


def github_check_conclusion_for_outcome(outcome: str | None) -> str:
    """Advisory product: avoid false 'failure' on degraded runs (Phase 3C policy)."""
    if outcome == "completed_ok":
        return "success"
    if outcome == "completed_degraded":
        return "neutral"
    if outcome == "failed":
        return "failure"
    return "neutral"
