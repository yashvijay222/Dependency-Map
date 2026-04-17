"""Optional slow integration: full CPG graph diff from a tiny git repo (Phase 1C).

Set RUN_GIT_CPG_INTEGRATION=1 to enable (can take tens of seconds; needs git + torch stack).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_GIT_CPG_INTEGRATION") != "1",
    reason="Set RUN_GIT_CPG_INTEGRATION=1 to run full graph diff integration",
)


@pytest.mark.skipif(not shutil.which("git"), reason="git binary not available")
def test_load_analysis_inputs_git_diff_payload(tmp_path: Path) -> None:
    from cpg_builder.scorer import _load_analysis_inputs

    tpl = tmp_path / "git_template"
    (tpl / "info").mkdir(parents=True)
    (tpl / "hooks").mkdir(parents=True)
    repo = tmp_path / "fixture"
    repo.mkdir()
    (repo / "lib.py").write_text("def x():\n    return 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "init", f"--template={tpl}"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "branch", "-M", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "a"], cwd=repo, check=True, capture_output=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (repo / "lib.py").write_text("def x():\n    return 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "b"], cwd=repo, check=True, capture_output=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    _g, _p, diff_payload, _rid, _b, _h = _load_analysis_inputs(
        repo,
        base=base,
        head=head,
        cpg_json=None,
        diff_json=None,
    )
    assert diff_payload is not None
    assert "graph_diff" in diff_payload or "changed_files" in diff_payload
