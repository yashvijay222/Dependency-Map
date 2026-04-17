"""Materialize a git checkout suitable for CPG base/head scoring (Phase 1)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

log = logging.getLogger(__name__)


def _clone_url(full_name: str, token: str) -> str:
    # https://github.com/settings/tokens — x-access-token pattern for HTTPS GitHub
    safe = quote(token, safe="")
    return f"https://x-access-token:{safe}@github.com/{full_name}.git"


def materialize_git_workspace(
    dest: Path,
    full_name: str,
    token: str,
    base_sha: str,
    head_sha: str,
    *,
    timeout_seconds: int = 600,
) -> Path | None:
    """Clone repo into ``dest`` and verify both SHAs exist.

    Returns ``dest`` on success, or ``None`` if clone/fetch fails.
    """
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = _clone_url(full_name, token)
    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "200",
                "--filter=blob:none",
                url,
                str(dest),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        log.warning("git clone failed for %s: %s", full_name, exc)
        shutil.rmtree(dest, ignore_errors=True)
        return None

    def _has_sha(sha: str) -> bool:
        try:
            r = subprocess.run(
                ["git", "-C", str(dest), "cat-file", "-t", sha],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return r.stdout.strip() in {"commit", "tag"}
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    if not _has_sha(head_sha):
        log.warning("head sha %s missing after clone for %s", head_sha, full_name)
        shutil.rmtree(dest, ignore_errors=True)
        return None
    if base_sha and not _has_sha(base_sha):
        # deepen shallow history once
        try:
            subprocess.run(
                ["git", "-C", str(dest), "fetch", "--deepen=500", "origin"],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            log.warning("git fetch deepen failed: %s", exc)
        if not _has_sha(base_sha):
            log.warning("base sha %s still missing for %s", base_sha, full_name)
            shutil.rmtree(dest, ignore_errors=True)
            return None
    return dest
