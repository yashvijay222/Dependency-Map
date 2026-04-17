"""Phase 1: git workspace helper behavior."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from app.services.git_workspace import materialize_git_workspace


def test_materialize_git_workspace_returns_none_on_clone_failure(tmp_path: Path) -> None:
    dest = tmp_path / "ws"

    def _fail(*_a, **_k):
        raise subprocess.CalledProcessError(128, "git", output=b"nope", stderr=b"fail")

    with patch("app.services.git_workspace.subprocess.run", side_effect=_fail):
        assert materialize_git_workspace(dest, "acme/repo", "token", "base", "head") is None
