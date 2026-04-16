from pathlib import Path

from app.services.asg_builder import build_asg


def test_build_asg_contains_modules_and_symbols(tmp_path: Path) -> None:
    (tmp_path / "index.ts").write_text(
        "import { helper } from './helper';\nexport function run() { return helper(); }\n",
        encoding="utf-8",
    )
    (tmp_path / "helper.ts").write_text(
        "export function helper() { return 1; }\n",
        encoding="utf-8",
    )

    graph = build_asg(tmp_path)

    assert graph["node_count"] >= 4
    assert graph["edge_count"] >= 3
    assert graph["counts_by_kind"]["module"] == 2
    assert graph["counts_by_kind"]["function"] >= 2
    assert any(e["type"] == "contains" for e in graph["edges"])
    assert any(e["type"] == "imports_module" for e in graph["edges"])


def test_build_asg_creates_package_nodes(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"react": "^19.0.0"}}',
        encoding="utf-8",
    )
    (tmp_path / "app.tsx").write_text(
        "import React from 'react';\nexport function App() { return <div />; }\n",
        encoding="utf-8",
    )

    graph = build_asg(tmp_path)

    package_nodes = [n for n in graph["nodes"] if n["kind"] == "package"]
    assert package_nodes
    assert any(n["name"] == "react" for n in package_nodes)
    assert any(e["type"] == "imports_package" for e in graph["edges"])
