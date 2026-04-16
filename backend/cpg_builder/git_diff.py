from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .schema import BuildArtifacts, GraphDiff
from .utils import graph_attr_fingerprint


def changed_files(repo_root: Path, base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base, head],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def materialize_git_ref(repo_root: Path, ref: str) -> tempfile.TemporaryDirectory[str]:
    tempdir = tempfile.TemporaryDirectory()
    target = Path(tempdir.name)
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    for rel_path in [line.strip() for line in result.stdout.splitlines() if line.strip()]:
        dest = target / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob = subprocess.run(
            ["git", "show", f"{ref}:{rel_path}"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        dest.write_bytes(blob.stdout)
    return tempdir


def diff_artifacts(base: BuildArtifacts, head: BuildArtifacts) -> GraphDiff:
    base_nodes = {node.id: node.as_dict() for node in base.nodes}
    head_nodes = {node.id: node.as_dict() for node in head.nodes}
    base_edges = {edge.id: edge.as_dict() for edge in base.edges}
    head_edges = {edge.id: edge.as_dict() for edge in head.edges}

    def changed(before: dict[str, dict], after: dict[str, dict]) -> list[dict]:
        out: list[dict] = []
        for key in sorted(before.keys() & after.keys()):
            if graph_attr_fingerprint(before[key]) != graph_attr_fingerprint(after[key]):
                out.append({"before": before[key], "after": after[key]})
        return out

    return GraphDiff(
        added_nodes=[head_nodes[k] for k in sorted(head_nodes.keys() - base_nodes.keys())],
        removed_nodes=[base_nodes[k] for k in sorted(base_nodes.keys() - head_nodes.keys())],
        changed_nodes=changed(base_nodes, head_nodes),
        added_edges=[head_edges[k] for k in sorted(head_edges.keys() - base_edges.keys())],
        removed_edges=[base_edges[k] for k in sorted(base_edges.keys() - head_edges.keys())],
        changed_edges=changed(base_edges, head_edges),
    )
