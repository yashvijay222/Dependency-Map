from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.ast_parser import build_ast_graph
from app.services.graph_builder import SKIP_DIR_PARTS, SOURCE_EXTS
from app.services.tree_sitter_languages import parser_for_suffix


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a tree-sitter AST graph for a repository directory.",
    )
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=str(REPO_ROOT),
        help="Path to the repository root to scan. Defaults to the monorepo root.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional path to write the AST graph JSON.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation level for output. Defaults to 2.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print only graph counts instead of the full graph payload.",
    )
    return parser.parse_args()


def _summary_payload(graph: dict) -> dict[str, int]:
    return {
        "file_count": int(graph.get("file_count", 0)),
        "node_count": int(graph.get("node_count", 0)),
        "edge_count": int(graph.get("edge_count", 0)),
    }


def _iter_source_files(repo_root: Path) -> list[str]:
    out: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix not in SOURCE_EXTS:
            continue
        if any(part in SKIP_DIR_PARTS for part in path.parts):
            continue
        out.append(path.relative_to(repo_root).as_posix())
    return sorted(out)


def _parser_support() -> dict[str, bool]:
    return {
        ".ts": parser_for_suffix(".ts") is not None,
        ".tsx": parser_for_suffix(".tsx") is not None,
        ".js": parser_for_suffix(".js") is not None,
        ".jsx": parser_for_suffix(".jsx") is not None,
    }


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists():
        print(f"Repository path does not exist: {repo_root}", file=sys.stderr)
        return 1
    if not repo_root.is_dir():
        print(f"Repository path is not a directory: {repo_root}", file=sys.stderr)
        return 1

    source_files = _iter_source_files(repo_root)
    parser_support = _parser_support()
    graph = build_ast_graph(repo_root)

    if args.summary_only:
        payload: dict = {
            **_summary_payload(graph),
            "source_file_count": len(source_files),
            "parser_support": parser_support,
        }
    else:
        payload = {
            **graph,
            "source_file_count": len(source_files),
            "parser_support": parser_support,
        }
    text = json.dumps(payload, indent=args.indent) + "\n"

    if source_files and not any(parser_support.values()):
        print(
            "Warning: source files were found, but tree-sitter parsers are unavailable. "
            "Install backend dependencies before generating the AST.",
            file=sys.stderr,
        )
    elif source_files and int(graph.get("node_count", 0)) == 0:
        print(
            "Warning: source files were found, but no AST nodes were produced. "
            "This usually means the parser layer failed to initialize for this environment.",
            file=sys.stderr,
        )
    elif not source_files:
        print(
            "Warning: no .ts/.tsx/.js/.jsx source files were found under the target path.",
            file=sys.stderr,
        )

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        print(f"Wrote AST graph to {output_path}")
    else:
        print(text, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
