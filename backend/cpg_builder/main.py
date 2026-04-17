from __future__ import annotations

import argparse
import json
from pathlib import Path

from .compare_rankers import compare_ranker_runs
from .exporters import export_graphml, export_json, export_ndjson
from .fusion import build_cpg
from .git_diff import changed_files, diff_artifacts, materialize_git_ref
from .label_ranker_results import generate_ranker_label_file
from .prepare_graphcodebert_dataset import prepare_graphcodebert_dataset
from .scorer import replay_reasoner_queue, score_repository


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

    score = sub.add_parser("score", help="Run the offline invariant scorer")
    score.add_argument("--repo", required=True, help="Local repository path")
    score.add_argument("--out-dir", required=True, help="Output directory for scorer artifacts")
    score.add_argument("--base", help="Optional base git ref")
    score.add_argument("--head", help="Optional head git ref")
    score.add_argument("--cpg-json", help="Optional existing CPG JSON payload")
    score.add_argument("--diff-json", help="Optional existing diff JSON payload")

    replay = sub.add_parser("replay", help="Replay queued reasoner work")
    replay.add_argument("--queue", required=True, help="Path to reasoner_queue.jsonl")
    replay.add_argument("--out-dir", required=True, help="Output directory for replay artifacts")
    replay.add_argument("--force-stale", action="store_true")
    replay.add_argument("--rerank", action="store_true")

    compare = sub.add_parser(
        "compare-rankers",
        help="Compare heuristic and GraphCodeBERT ranking",
    )
    compare.add_argument("--repo", required=True, help="Local repository path")
    compare.add_argument(
        "--out-dir",
        required=True,
        help="Output directory for comparison artifacts",
    )
    compare.add_argument("--base", help="Optional base git ref")
    compare.add_argument("--head", help="Optional head git ref")
    compare.add_argument("--cpg-json", help="Optional existing CPG JSON payload")
    compare.add_argument("--diff-json", help="Optional existing diff JSON payload")
    compare.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="How many rank movements to summarize",
    )

    label = sub.add_parser(
        "label-ranker-results",
        help="Generate a JSONL review file from compare-rankers output",
    )
    label.add_argument("--compare-dir", required=True, help="Directory from compare-rankers")
    label.add_argument("--out", help="Optional output JSONL path")
    label.add_argument(
        "--limit",
        type=int,
        default=20,
        help="How many promotions and drops to include",
    )

    prepare = sub.add_parser(
        "prepare-graphcodebert-dataset",
        help="Prepare reviewed ranker labels for GraphCodeBERT fine-tuning",
    )
    prepare.add_argument("--labels", required=True, help="Path to reviewed ranker-labels JSONL")
    prepare.add_argument("--out-dir", required=True, help="Output directory for train/val JSONL")
    prepare.add_argument(
        "--val-ratio",
        type=float,
        default=0.2,
        help="Validation split ratio",
    )

    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.command == "build":
        return _run_build(args)
    if args.command == "diff":
        return _run_diff(args)
    if args.command == "score":
        return _run_score(args)
    if args.command == "compare-rankers":
        return _run_compare_rankers(args)
    if args.command == "label-ranker-results":
        return _run_label_ranker_results(args)
    if args.command == "prepare-graphcodebert-dataset":
        return _run_prepare_graphcodebert_dataset(args)
    return _run_replay(args)


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


def _run_score(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    out_dir = Path(args.out_dir).resolve()
    artifacts = score_repository(
        repo,
        out_dir,
        base=args.base,
        head=args.head,
        cpg_json=Path(args.cpg_json).resolve() if args.cpg_json else None,
        diff_json=Path(args.diff_json).resolve() if args.diff_json else None,
    )
    print(
        json.dumps(
            {
                "out_dir": str(out_dir),
                "run_id": artifacts.run_id,
                "violations": len(artifacts.violations),
                "queued_reasoner_items": len(artifacts.reasoner_queue),
            },
            indent=2,
        )
    )
    return 0


def _run_replay(args: argparse.Namespace) -> int:
    queue = Path(args.queue).resolve()
    out_dir = Path(args.out_dir).resolve()
    replay = replay_reasoner_queue(
        queue,
        out_dir,
        force_stale=bool(args.force_stale),
        rerank=bool(args.rerank),
    )
    print(json.dumps(replay, indent=2))
    return 0


def _run_compare_rankers(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    out_dir = Path(args.out_dir).resolve()
    comparison = compare_ranker_runs(
        repo,
        out_dir,
        base=args.base,
        head=args.head,
        cpg_json=Path(args.cpg_json).resolve() if args.cpg_json else None,
        diff_json=Path(args.diff_json).resolve() if args.diff_json else None,
        top_k=int(args.top_k),
    )
    print(
        json.dumps(
            {
                "out_dir": str(out_dir),
                "shared_candidates": comparison["summary"]["shared_candidates"],
                "top_k_overlap": comparison["summary"]["top_k_overlap"],
            },
            indent=2,
        )
    )
    return 0


def _run_label_ranker_results(args: argparse.Namespace) -> int:
    compare_dir = Path(args.compare_dir).resolve()
    output = Path(args.out).resolve() if args.out else None
    result = generate_ranker_label_file(
        compare_dir,
        output,
        limit=int(args.limit),
    )
    print(json.dumps(result, indent=2))
    return 0


def _run_prepare_graphcodebert_dataset(args: argparse.Namespace) -> int:
    labels = Path(args.labels).resolve()
    out_dir = Path(args.out_dir).resolve()
    result = prepare_graphcodebert_dataset(
        labels,
        out_dir,
        val_ratio=float(args.val_ratio),
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
