"""Tests for Layer 1: tree-sitter AST graph builder."""

from pathlib import Path

from app.services.ast_parser import build_ast_graph


def test_build_ast_graph_on_typescript(tmp_path: Path) -> None:
    (tmp_path / "hello.ts").write_text(
        "import { x } from 'other';\nexport function foo() { return 1; }\n",
        encoding="utf-8",
    )
    g = build_ast_graph(tmp_path)
    assert g["node_count"] >= 1
    assert g["file_count"] == 1
    assert g["edge_count"] >= 1


def test_extracts_import_nodes(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text(
        "import { bar } from './bar';\nimport * as React from 'react';\n",
        encoding="utf-8",
    )
    g = build_ast_graph(tmp_path)
    imports = [n for n in g["nodes"] if n["kind"] == "import"]
    assert len(imports) == 2
    for imp in imports:
        assert imp["file"] == "a.ts"
        assert imp["line"] >= 1
        assert "import" in imp["code_snippet"]
    assert any(e["type"] == "ast_child" for e in g["edges"])


def test_extracts_function_nodes(tmp_path: Path) -> None:
    (tmp_path / "funcs.ts").write_text(
        "function greet(name: string) { return `Hello ${name}`; }\n"
        "export function add(a: number, b: number) { return a + b; }\n",
        encoding="utf-8",
    )
    g = build_ast_graph(tmp_path)
    funcs = [n for n in g["nodes"] if n["kind"] == "function"]
    assert len(funcs) >= 2
    names = {f["name"] for f in funcs}
    assert "greet" in names
    assert "add" in names
    for f in funcs:
        assert f["code_snippet"]
        assert f["line"] >= 1


def test_includes_file_nodes_and_parent_child_edges(tmp_path: Path) -> None:
    (tmp_path / "hello.ts").write_text(
        "import { x } from './x';\nfunction myFunc() { return x; }\n",
        encoding="utf-8",
    )
    (tmp_path / "x.ts").write_text("export const x = 1;\n", encoding="utf-8")
    g = build_ast_graph(tmp_path)
    file_nodes = [n for n in g["nodes"] if n["kind"] == "file"]
    assert len(file_nodes) == 2
    assert any(e["type"] == "ast_child" for e in g["edges"])


def test_extracts_arrow_functions(tmp_path: Path) -> None:
    (tmp_path / "arrows.ts").write_text(
        "const double = (x: number) => x * 2;\n"
        "export const triple = (x: number) => x * 3;\n",
        encoding="utf-8",
    )
    g = build_ast_graph(tmp_path)
    assert g["node_count"] >= 1


def test_handles_jsx_tsx_files(tmp_path: Path) -> None:
    (tmp_path / "app.tsx").write_text(
        "import React from 'react';\n"
        "function App() { return <div>Hello</div>; }\n"
        "export default App;\n",
        encoding="utf-8",
    )
    g = build_ast_graph(tmp_path)
    assert g["node_count"] >= 1
    assert g["file_count"] == 1
    kinds = {n["kind"] for n in g["nodes"]}
    assert "import" in kinds or "function" in kinds


def test_handles_javascript_files(tmp_path: Path) -> None:
    (tmp_path / "util.js").write_text(
        "const fs = require('fs');\n"
        "function readFile(path) { return fs.readFileSync(path); }\n"
        "module.exports = { readFile };\n",
        encoding="utf-8",
    )
    g = build_ast_graph(tmp_path)
    assert g["node_count"] >= 1
    assert g["file_count"] == 1


def test_skips_node_modules(tmp_path: Path) -> None:
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("function internal() {}\n", encoding="utf-8")
    (tmp_path / "src.ts").write_text("function main() {}\n", encoding="utf-8")
    g = build_ast_graph(tmp_path)
    files = {n["file"] for n in g["nodes"]}
    assert all("node_modules" not in f for f in files)


def test_multiple_files(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text(
        "import { b } from './b';\nexport function processA() {}\n",
        encoding="utf-8",
    )
    (tmp_path / "b.ts").write_text(
        "export function helperB() { return 42; }\n",
        encoding="utf-8",
    )
    (tmp_path / "c.tsx").write_text(
        "import { processA } from './a';\nfunction Component() { processA(); }\n",
        encoding="utf-8",
    )
    g = build_ast_graph(tmp_path)
    assert g["file_count"] == 3
    assert g["node_count"] >= 3


def test_empty_directory(tmp_path: Path) -> None:
    g = build_ast_graph(tmp_path)
    assert g["node_count"] == 0
    assert g["edge_count"] == 0
    assert g["file_count"] == 0


def test_node_id_format(tmp_path: Path) -> None:
    (tmp_path / "hello.ts").write_text(
        "import { x } from 'y';\nfunction myFunc() {}\n",
        encoding="utf-8",
    )
    g = build_ast_graph(tmp_path)
    for node in g["nodes"]:
        parts = node["id"].split(":")
        assert len(parts) >= 3, f"Node id should have file:line:kind format, got: {node['id']}"


def test_non_ts_js_files_ignored(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text("# Hello\n", encoding="utf-8")
    (tmp_path / "style.css").write_text("body { color: red; }\n", encoding="utf-8")
    (tmp_path / "data.json").write_text('{"key": "value"}\n', encoding="utf-8")
    (tmp_path / "app.ts").write_text("function main() {}\n", encoding="utf-8")
    g = build_ast_graph(tmp_path)
    assert g["file_count"] == 1
    files = {n["file"] for n in g["nodes"]}
    assert "readme.md" not in files
    assert "style.css" not in files
