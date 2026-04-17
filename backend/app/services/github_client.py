"""GitHub App installation token, tarball download, compare API, CODEOWNERS."""

from __future__ import annotations

import io
import logging
import sys
import tarfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import jwt

from app.config import settings
from app.observability import increment_counter

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
API_ACCEPT = "application/vnd.github+json"
API_VERSION = "2022-11-28"


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": API_ACCEPT,
        "X-GitHub-Api-Version": API_VERSION,
    }


def _github_request(
    method: str,
    url: str,
    token: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 60.0,
    follow_redirects: bool = False,
) -> httpx.Response:
    """HTTP call with Retry-After / 429 handling."""
    max_retries = max(1, int(settings.github_max_retries))
    r: httpx.Response | None = None
    for attempt in range(max_retries):
        with httpx.Client(timeout=timeout, follow_redirects=follow_redirects) as client:
            r = client.request(
                method,
                url,
                headers=_auth_headers(token),
                params=params,
                json=json_body,
            )
        if r.status_code == 429 or (
            r.status_code == 403 and "rate limit" in (r.text or "").lower()
        ):
            increment_counter("github_429")
            ra = r.headers.get("Retry-After")
            wait = float(ra) if ra and str(ra).isdigit() else min(2**attempt, 60)
            log.warning("GitHub rate limit; sleeping %.1fs (attempt %s)", wait, attempt + 1)
            time.sleep(wait)
            if attempt == max_retries - 1:
                r.raise_for_status()
            continue
        if 500 <= r.status_code < 600 and attempt < max_retries - 1:
            time.sleep(min(2**attempt, 30))
            continue
        return r
    assert r is not None
    return r


def _pem() -> str:
    raw = settings.github_app_private_key.strip()
    if not raw:
        return ""
    return raw.replace("\\n", "\n")


def _app_jwt() -> str:
    app_id = settings.github_app_id.strip()
    pem = _pem()
    if not app_id or not pem:
        raise RuntimeError("GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY must be set")
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 9 * 60,
        "iss": app_id,
    }
    return jwt.encode(payload, pem, algorithm="RS256")


def get_installation_token(installation_id: int) -> str:
    """Exchange GitHub App JWT for an installation access token."""
    gh_jwt = _app_jwt()
    url = f"{GITHUB_API}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {gh_jwt}",
        "Accept": API_ACCEPT,
        "X-GitHub-Api-Version": API_VERSION,
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, headers=headers)
        r.raise_for_status()
        data = r.json()
    token = data.get("token")
    if not token:
        raise RuntimeError("GitHub returned no installation token")
    return str(token)


def fetch_tarball_to_dir(full_name: str, sha: str, token: str, dest_dir: Path) -> Path:
    """
    Download repo tarball for commit sha and extract into dest_dir.
    Returns the root folder containing extracted files (first member prefix).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = f"{GITHUB_API}/repos/{full_name}/tarball/{sha}"
    r = _github_request("GET", url, token, timeout=120.0, follow_redirects=True)
    r.raise_for_status()
    data = r.content

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        if sys.version_info >= (3, 12):
            tf.extractall(dest_dir, filter="data")
        else:
            tf.extractall(dest_dir)

    # GitHub tarball is one top-level dir: {owner}-{repo}-{sha}/
    subdirs = [p for p in dest_dir.iterdir() if p.is_dir()]
    if len(subdirs) != 1:
        log.warning("Expected one root dir in tarball, got %s", subdirs)
        return dest_dir
    return subdirs[0]


def compare_commits(
    full_name: str,
    base_sha: str,
    head_sha: str,
    token: str,
) -> dict[str, Any]:
    """GET /compare/{base}...{head}"""
    url = f"{GITHUB_API}/repos/{full_name}/compare/{base_sha}...{head_sha}"
    r = _github_request("GET", url, token, timeout=60.0)
    r.raise_for_status()
    return r.json()


def changed_files_from_compare(compare_json: dict[str, Any]) -> list[str]:
    files = compare_json.get("files") or []
    names: list[str] = []
    for f in files:
        if isinstance(f, dict) and f.get("filename"):
            names.append(str(f["filename"]))
    return names


def fetch_codeowners_text(full_name: str, sha: str, token: str) -> str | None:
    """Return CODEOWNERS raw text if present at root or .github/."""
    paths = ["CODEOWNERS", ".github/CODEOWNERS"]
    with httpx.Client(timeout=30.0) as client:
        for p in paths:
            url = f"{GITHUB_API}/repos/{full_name}/contents/{p}"
            r = client.get(
                url,
                headers=_auth_headers(token),
                params={"ref": sha},
            )
            if r.status_code != 200:
                continue
            body = r.json()
            if isinstance(body, dict) and body.get("encoding") == "base64":
                import base64

                raw = base64.b64decode(body.get("content", "")).decode(
                    "utf-8", errors="replace"
                )
                return raw
    return None


def github_configured() -> bool:
    return bool(settings.github_app_id.strip() and settings.github_app_private_key.strip())


def list_installation_repos(token: str, per_page: int = 100) -> list[dict[str, Any]]:
    """GET /installation/repositories (paginated)."""
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        url = f"{GITHUB_API}/installation/repositories"
        r = _github_request(
            "GET",
            url,
            token,
            params={"per_page": per_page, "page": page},
        )
        r.raise_for_status()
        data = r.json()
        repos = data.get("repositories") or []
        if isinstance(repos, list):
            out.extend([x for x in repos if isinstance(x, dict)])
        if not repos or len(repos) < per_page:
            break
        page += 1
    return out


def list_branches(full_name: str, token: str, per_page: int = 100) -> list[dict[str, Any]]:
    """GET /repos/{owner}/{repo}/branches"""
    owner, _, repo = full_name.partition("/")
    if not owner or not repo:
        raise ValueError("full_name must be owner/repo")
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/branches"
        r = _github_request(
            "GET",
            url,
            token,
            params={"per_page": per_page, "page": page},
        )
        r.raise_for_status()
        chunk = r.json()
        if not isinstance(chunk, list):
            break
        out.extend([b for b in chunk if isinstance(b, dict)])
        if len(chunk) < per_page:
            break
        page += 1
    return out


def get_branch_head_sha(full_name: str, branch: str, token: str) -> str:
    """Resolve git ref heads/{branch} to SHA."""
    owner, _, repo = full_name.partition("/")
    if not owner or not repo:
        raise ValueError("full_name must be owner/repo")
    ref_path = quote(f"heads/{branch}", safe="")
    url = f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/{ref_path}"
    r = _github_request("GET", url, token, timeout=30.0)
    r.raise_for_status()
    body = r.json()
    obj = body.get("object") if isinstance(body, dict) else None
    if isinstance(obj, dict) and obj.get("sha"):
        return str(obj["sha"])
    raise RuntimeError(f"Could not resolve branch {branch!r} for {full_name}")


def github_installation_http(
    token: str,
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> httpx.Response:
    """GitHub REST call with installation token (429 / retry aligned with other GitHub calls)."""
    return _github_request(method, url, token, json_body=json_body, timeout=timeout)
