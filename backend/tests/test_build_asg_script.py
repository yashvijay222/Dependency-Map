from __future__ import annotations

import json
from pathlib import Path

from scripts.build_asg import main


def test_build_asg_script_writes_output(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "index.ts").write_text(
        "import { helper } from './helper';\nexport function run() { return helper(); }\n",
        encoding="utf-8",
    )
    (repo_root / "helper.ts").write_text(
        "export function helper() { return 1; }\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "asg.json"

    monkeypatch.setattr(
        "sys.argv",
        ["build_asg.py", str(repo_root), "--output", str(output_path)],
    )

    exit_code = main()

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["node_count"] >= 4
    assert payload["edge_count"] >= 3
    assert payload["counts_by_kind"]["module"] == 2


def test_build_asg_script_summary_only(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "app.tsx").write_text(
        "import React from 'react';\nfunction App() { return <div />; }\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "sys.argv",
        ["build_asg.py", str(repo_root), "--summary-only"],
    )

    exit_code = main()

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["node_count"] >= 2
    assert payload["counts_by_kind"]["module"] == 1
    assert payload["source_file_count"] == 1
