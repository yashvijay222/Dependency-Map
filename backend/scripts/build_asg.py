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

from app.services.asg_builder import build_asg
from app.services.graph_builder import SKIP_DIR_PARTS, SOURCE_EXTS
from app.services.tree_sitter_languages import parser_for_suffix


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an abstract semantic graph (ASG) for a repository directory.",
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
        help="Optional path to write the ASG JSON.",
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
        help="Print only graph counts and kind breakdowns instead of the full ASG payload.",
    )
    return parser.parse_args()


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


def _summary_payload(graph: dict[str, object]) -> dict[str, object]:
    return {
        "node_count": int(graph.get("node_count", 0)),
        "edge_count": int(graph.get("edge_count", 0)),
        "counts_by_kind": graph.get("counts_by_kind", {}),
        "source_ast_node_count": int(graph.get("source_ast_node_count", 0)),
        "source_dependency_edge_count": int(graph.get("source_dependency_edge_count", 0)),
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
    graph = build_asg(repo_root)
    payload = _summary_payload(graph) if args.summary_only else graph
    payload = {
        **payload,
        "source_file_count": len(source_files),
        "parser_support": parser_support,
    }
    text = json.dumps(payload, indent=args.indent) + "\n"

    if source_files and not any(parser_support.values()):
        print(
            "Warning: source files were found, but tree-sitter parsers are unavailable. "
            "Install backend dependencies before generating the ASG.",
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
        print(f"Wrote ASG to {output_path}")
    else:
        print(text, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
