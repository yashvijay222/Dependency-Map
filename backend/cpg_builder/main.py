from __future__ import annotations

import argparse
import json
from pathlib import Path

from .exporters import export_graphml, export_json, export_ndjson
from .fusion import build_cpg
from .git_diff import changed_files, diff_artifacts, materialize_git_ref


def _parse_language_set(value: str | None) -> set[str] | None:
    if not value:
        return None
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m cpg_builder.main")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build a fused CPG")
    build.add_argument("--repo", required=True, help="Local repository path")
    build.add_argument("--out", required=True, help="Output file path")
    build.add_argument("--format", default="json", choices=["json", "graphml", "ndjson"])
    build.add_argument("--file", help="Build only for a single repo-relative file")
    build.add_argument("--languages", help="Comma-separated language set")
    build.add_argument("--git-ref", help="Optional git ref to annotate outputs")
    build.add_argument("--include-tokens", action="store_true")

    diff = sub.add_parser("diff", help="Build and diff two revisions")
    diff.add_argument("--repo", required=True, help="Local repository path")
    diff.add_argument("--base", required=True, help="Base git ref")
    diff.add_argument("--head", required=True, help="Head git ref")
    diff.add_argument("--out", required=True, help="Diff output path")
    diff.add_argument("--languages", help="Comma-separated language set")

    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.command == "build":
        return _run_build(args)
    return _run_diff(args)


def _run_build(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    out = Path(args.out).resolve()
    graph, artifacts = build_cpg(
        repo,
        target_languages=_parse_language_set(args.languages),
        only_paths={args.file} if args.file else None,
        git_ref=args.git_ref,
        include_tokens=bool(args.include_tokens),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.format == "json":
        export_json(graph, artifacts, out)
    elif args.format == "graphml":
        export_graphml(graph, out)
    else:
        export_ndjson(graph, artifacts, out)
    print(
        json.dumps(
            {
                "out": str(out),
                "node_count": artifacts.summaries["node_count"],
                "edge_count": artifacts.summaries["edge_count"],
            },
            indent=2,
        ),
    )
    return 0


def _run_diff(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    out = Path(args.out).resolve()
    langs = _parse_language_set(args.languages)
    changed = changed_files(repo, args.base, args.head)
    base_dir = materialize_git_ref(repo, args.base)
    head_dir = materialize_git_ref(repo, args.head)
    try:
        _base_graph, base_artifacts = build_cpg(
            base_dir.name,
            target_languages=langs,
            git_ref=args.base,
            repo_identity=repo,
        )
        _head_graph, head_artifacts = build_cpg(
            head_dir.name,
            target_languages=langs,
            git_ref=args.head,
            previous_artifacts=base_artifacts,
            changed_paths=set(changed),
            repo_identity=repo,
        )
        diff = diff_artifacts(base_artifacts, head_artifacts)
        payload = {
            "repo": str(repo),
            "base": args.base,
            "head": args.head,
            "changed_files": changed,
            "graph_diff": {
                "added_nodes": diff.added_nodes,
                "removed_nodes": diff.removed_nodes,
                "changed_nodes": diff.changed_nodes,
                "added_edges": diff.added_edges,
                "removed_edges": diff.removed_edges,
                "changed_edges": diff.changed_edges,
            },
            "base_summary": base_artifacts.summaries,
            "head_summary": head_artifacts.summaries,
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    finally:
        base_dir.cleanup()
        head_dir.cleanup()
    print(json.dumps({"out": str(out), "changed_files": len(changed)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
