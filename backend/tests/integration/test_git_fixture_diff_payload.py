"""Integration: tiny git repo yields real changed-file list between SHAs (Phase 1C)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from cpg_builder.git_diff import changed_files


@pytest.mark.skipif(not shutil.which("git"), reason="git binary not available")
def test_git_fixture_changed_files_non_empty(tmp_path: Path) -> None:
    repo = tmp_path / "fixture"
    repo.mkdir()
    (repo / "stub.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    init = subprocess.run(["git", "init"], cwd=repo, capture_output=True, text=True)
    if init.returncode != 0:
        pytest.skip(f"git init unavailable: {init.stderr}")
    subprocess.run(["git", "branch", "-M", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "fixture@test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "fixture"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (repo / "stub.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "head"], cwd=repo, check=True, capture_output=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    names = changed_files(repo, base, head)
    assert "stub.py" in names
