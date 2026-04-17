from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import networkx as nx

from .exporters import graph_payload
from .fusion import build_cpg
from .git_diff import changed_files, diff_artifacts, materialize_git_ref
from .invariants import InvariantSpec, default_invariants
from .path_miner import CandidatePath, deserialize_candidate_path, mine_candidate_paths
from .ranker import RankedCandidate, rank_candidates, ranker_example
from .reasoner import HostedGemmaReasoner, load_queue_entries
from .verifier import verify_candidate


@dataclass(slots=True)
class ScoreArtifacts:
    run_id: str
    violations: list[dict[str, Any]]
    verifier_audit: list[dict[str, Any]]
    reasoner_queue: list[dict[str, Any]]
    ranker_examples: list[dict[str, Any]]
    reasoner_examples: list[dict[str, Any]]
    run_metadata: dict[str, Any]


def score_repository(
    repo_root: Path,
    out_dir: Path,
    *,
    base: str | None = None,
    head: str | None = None,
    cpg_json: Path | None = None,
    diff_json: Path | None = None,
    invariants: list[InvariantSpec] | None = None,
) -> ScoreArtifacts:
    out_dir.mkdir(parents=True, exist_ok=True)
    invariant_specs = invariants or default_invariants()
    graph, payload, diff_payload, repo_id, base_ref, head_ref = _load_analysis_inputs(
        repo_root,
        base=base,
        head=head,
        cpg_json=cpg_json,
        diff_json=diff_json,
    )
    candidates = mine_candidate_paths(graph, invariant_specs, diff_payload)
    invariant_map = {spec.id: spec for spec in invariant_specs}
    ranked = rank_candidates(candidates, invariant_map)
    reasoner = HostedGemmaReasoner()
    run_id = f"score:{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    stitcher_metrics = payload.get("summary", {}).get("stitcher_metrics", {})
    stitcher_state = (
        "low_stitcher_coverage" if stitcher_metrics.get("low_stitcher_coverage") else "healthy"
    )

    violations: list[dict[str, Any]] = []
    verifier_audit: list[dict[str, Any]] = []
    reasoner_queue: list[dict[str, Any]] = []
    ranker_examples: list[dict[str, Any]] = []
    reasoner_examples: list[dict[str, Any]] = []
    for ranked_candidate in ranked:
        spec = invariant_map[ranked_candidate.candidate.invariant_id]
        evidence_pack = build_evidence_pack(graph, ranked_candidate, spec, diff_payload)
        reasoner_result = reasoner.reason(evidence_pack)
        verification = verify_candidate(
            graph,
            spec,
            ranked_candidate.candidate,
            reasoner_result.output,
            stitcher_coverage_state=stitcher_state,
        )
        finding = {
            "finding_id": ranked_candidate.candidate.id,
            "invariant_id": spec.id,
            "severity": spec.severity,
            "rank_score": ranked_candidate.score,
            "rank_phase": ranked_candidate.phase,
            "reasoner_status": reasoner_result.status,
            "reasoner_confidence": reasoner_result.confidence,
            "verification": verification.as_dict(),
            "candidate": _candidate_payload(ranked_candidate.candidate),
            "reasoner_output": reasoner_result.output,
        }
        verifier_audit.append(finding)
        ranker_examples.append(ranker_example(ranked_candidate, repo_id, base_ref, head_ref))
        if verification.surfaced:
            violations.append(finding)
            if reasoner_result.output:
                reasoner_examples.append(
                    {
                        "example_id": ranked_candidate.candidate.id,
                        "invariant_id": spec.id,
                        "evidence_pack": evidence_pack,
                        "pack_manifest": evidence_pack["pack_manifest"],
                        "expected_output_json": reasoner_result.output,
                        "verifier_outcome": verification.outcome,
                        "label_source": "verifier_resolved",
                        "label_strength": "hard",
                        "repo_id": repo_id,
                        "base_ref": base_ref,
                        "head_ref": head_ref,
                    }
                )
        elif reasoner_result.status in {"reasoning_unavailable", "reasoner_failed"}:
            reasoner_queue.append(
                reasoner.replayable_entry(
                    evidence_pack,
                    run_id=run_id,
                    candidate_path=ranked_candidate.candidate,
                )
            )

    run_metadata = {
        "run_id": run_id,
        "repo": str(repo_root),
        "base_ref": base_ref,
        "head_ref": head_ref,
        "analysis_mode": "diff" if diff_payload else "full_repo_scan",
        "stitcher_coverage_state": stitcher_state,
        "stitcher_metrics": stitcher_metrics,
        "candidate_count": len(candidates),
        "ranked_count": len(ranked),
        "surfaced_count": len(violations),
        "reasoner_queue_count": len(reasoner_queue),
    }
    artifacts = ScoreArtifacts(
        run_id=run_id,
        violations=violations,
        verifier_audit=verifier_audit,
        reasoner_queue=reasoner_queue,
        ranker_examples=ranker_examples,
        reasoner_examples=reasoner_examples,
        run_metadata=run_metadata,
    )
    _write_score_outputs(out_dir, artifacts)
    return artifacts


def replay_reasoner_queue(
    queue_path: Path,
    out_dir: Path,
    *,
    force_stale: bool = False,
    rerank: bool = False,
    cpg_json: Path | None = None,
    re_verify: bool = False,
    training_jsonl: str | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = load_queue_entries(str(queue_path))
    reasoner = HostedGemmaReasoner()
    now_ts = datetime.now(UTC).timestamp()
    graph: nx.MultiDiGraph | None = None
    invariant_map: dict[str, InvariantSpec] | None = None
    stitcher_state = "healthy"
    if cpg_json and cpg_json.exists():
        payload = json.loads(cpg_json.read_text(encoding="utf-8"))
        graph = _graph_from_payload(payload)
        metrics = (payload.get("summary") or {}).get("stitcher_metrics") or {}
        if metrics.get("low_stitcher_coverage"):
            stitcher_state = "low_stitcher_coverage"
        invariant_map = {spec.id: spec for spec in default_invariants()}
    replayed: list[dict[str, Any]] = []
    for entry in entries:
        stale = float(entry.get("expires_at") or 0) < now_ts
        if stale and not force_stale:
            replayed.append(
                {
                    "run_id": entry.get("run_id"),
                    "status": "stale",
                    "reranked": False,
                }
            )
            continue
        evidence_pack = dict(entry.get("evidence_pack") or {})
        if rerank:
            evidence_pack["rank_phase"] = "phase0_heuristic_replay"
        if training_jsonl:
            os.environ["CPG_REASONER_TRAINING_JSONL"] = training_jsonl
        result = reasoner.reason(evidence_pack)
        row: dict[str, Any] = {
            "run_id": entry.get("run_id"),
            "status": result.status,
            "reranked": rerank,
            "reasoner_output": result.output,
            "reasoner_error": result.error,
        }
        if (
            re_verify
            and graph is not None
            and invariant_map is not None
            and entry.get("candidate_path")
            and isinstance(result.output, dict)
        ):
            cand = deserialize_candidate_path(dict(entry["candidate_path"]))
            spec = invariant_map.get(cand.invariant_id)
            if spec:
                verification = verify_candidate(
                    graph,
                    spec,
                    cand,
                    result.output,
                    stitcher_coverage_state=stitcher_state,
                )
                row["verification"] = verification.as_dict()
        replayed.append(row)
    replay_payload = {
        "queue_path": str(queue_path),
        "replayed_count": len(replayed),
        "results": replayed,
    }
    (out_dir / "replay_results.json").write_text(
        json.dumps(replay_payload, indent=2),
        encoding="utf-8",
    )
    return replay_payload


def build_evidence_pack(
    graph: nx.MultiDiGraph,
    ranked_candidate: RankedCandidate,
    spec: InvariantSpec,
    diff_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    candidate = ranked_candidate.candidate
    node_facts = [_node_fact(graph, node_id) for node_id in candidate.node_ids]
    witness_paths = [{"node_ids": candidate.node_ids, "edge_ids": candidate.edge_ids}]
    diff_excerpt = _diff_excerpt(diff_payload, candidate.changed_anchors)
    pack = {
        "invariant_id": spec.id,
        "candidate_id": candidate.id,
        "rank_score": ranked_candidate.score,
        "rank_phase": ranked_candidate.phase,
        "candidate_path_ids": candidate.node_ids,
        "witness_paths": witness_paths,
        "changed_anchors": candidate.changed_anchors,
        "facts": candidate.facts,
        "node_facts": node_facts,
        "diff_excerpt": diff_excerpt,
        "neighborhood_summary": _neighborhood_summary(graph, candidate.node_ids),
    }
    return _truncate_evidence_pack(pack, spec.max_tokens_per_pack)


def _load_analysis_inputs(
    repo_root: Path,
    *,
    base: str | None,
    head: str | None,
    cpg_json: Path | None,
    diff_json: Path | None,
) -> tuple[nx.MultiDiGraph, dict[str, Any], dict[str, Any] | None, str, str, str]:
    if cpg_json:
        payload = json.loads(cpg_json.read_text(encoding="utf-8"))
        graph = _graph_from_payload(payload)
        diff_payload = (
            json.loads(diff_json.read_text(encoding="utf-8"))
            if diff_json and diff_json.exists()
            else None
        )
        repo_id = str(payload.get("repo", {}).get("path") or repo_root)
        return graph, payload, diff_payload, repo_id, base or "", head or ""

    if base and head:
        changed = changed_files(repo_root, base, head)
        base_dir = materialize_git_ref(repo_root, base)
        head_dir = materialize_git_ref(repo_root, head)
        try:
            _base_graph, base_artifacts = build_cpg(
                base_dir.name, git_ref=base, repo_identity=repo_root
            )
            head_graph, head_artifacts = build_cpg(
                head_dir.name,
                git_ref=head,
                previous_artifacts=base_artifacts,
                changed_paths=set(changed),
                repo_identity=repo_root,
            )
            diff_payload = {
                "graph_diff": asdict(diff_artifacts(base_artifacts, head_artifacts)),
                "changed_files": changed,
            }
            payload = graph_payload(head_graph, head_artifacts)
            return head_graph, payload, diff_payload, head_artifacts.repo_index.repo_id, base, head
        finally:
            base_dir.cleanup()
            head_dir.cleanup()

    graph, artifacts = build_cpg(repo_root)
    payload = graph_payload(graph, artifacts)
    return graph, payload, None, artifacts.repo_index.repo_id, "", ""


def _graph_from_payload(payload: dict[str, Any]) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    for node in payload.get("nodes", []):
        graph.add_node(str(node["id"]), **node)
    for edge in payload.get("edges", []):
        graph.add_edge(str(edge["src"]), str(edge["dst"]), key=str(edge["id"]), **edge)
    return graph


def _candidate_payload(candidate: CandidatePath) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "invariant_id": candidate.invariant_id,
        "seed_id": candidate.seed_id,
        "node_ids": candidate.node_ids,
        "edge_ids": candidate.edge_ids,
        "seam_type": candidate.seam_type,
        "changed_anchors": candidate.changed_anchors,
        "heuristic_features": candidate.heuristic_features,
        "facts": candidate.facts,
    }


def _node_fact(graph: nx.MultiDiGraph, node_id: str) -> dict[str, Any]:
    attrs = dict(graph.nodes[node_id])
    return {
        "id": node_id,
        "label": attrs.get("label"),
        "file_path": attrs.get("file_path"),
        "name": attrs.get("name") or attrs.get("route_pattern") or attrs.get("task_name"),
        "entity_kind": attrs.get("entity_kind"),
    }


def _neighborhood_summary(graph: nx.MultiDiGraph, node_ids: list[str]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for node_id in node_ids:
        summary.append(
            {
                "node_id": node_id,
                "in_degree": int(graph.in_degree(node_id)),
                "out_degree": int(graph.out_degree(node_id)),
            }
        )
    return summary


def _diff_excerpt(
    diff_payload: dict[str, Any] | None, changed_anchors: list[str]
) -> dict[str, Any]:
    if not diff_payload:
        return {"changed_anchors": changed_anchors, "changed_files": []}
    return {
        "changed_anchors": changed_anchors,
        "changed_files": diff_payload.get("changed_files", []),
        "graph_diff_counts": {
            "added_nodes": len(diff_payload.get("graph_diff", {}).get("added_nodes", [])),
            "removed_nodes": len(diff_payload.get("graph_diff", {}).get("removed_nodes", [])),
            "changed_nodes": len(diff_payload.get("graph_diff", {}).get("changed_nodes", [])),
        },
    }


def _truncate_evidence_pack(pack: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    manifest = {"included": list(pack.keys()), "dropped": [], "truncated": []}
    candidate = dict(pack)
    for field in ("neighborhood_summary", "diff_excerpt", "witness_paths", "node_facts"):
        approx_tokens = len(json.dumps(candidate).split())
        if approx_tokens <= max_tokens:
            break
        if field not in candidate:
            continue
        if field == "neighborhood_summary":
            manifest["dropped"].append(field)
            candidate.pop(field, None)
            continue
        if field == "diff_excerpt":
            diff_excerpt = dict(candidate.get(field) or {})
            changed_files = diff_excerpt.get("changed_files") or []
            diff_excerpt["changed_files"] = changed_files[:3]
            candidate[field] = diff_excerpt
            manifest["truncated"].append(field)
            continue
        if field == "witness_paths":
            candidate[field] = (candidate.get(field) or [])[:1]
            manifest["truncated"].append(field)
            continue
        if field == "node_facts":
            candidate[field] = (candidate.get(field) or [])[:2]
            manifest["truncated"].append(field)
    candidate["pack_manifest"] = manifest
    candidate["token_budget"] = max_tokens
    candidate["truncation_events"] = manifest["dropped"] + manifest["truncated"]
    return candidate


def _write_score_outputs(out_dir: Path, artifacts: ScoreArtifacts) -> None:
    (out_dir / "violations.json").write_text(
        json.dumps(
            {"run_metadata": artifacts.run_metadata, "violations": artifacts.violations},
            indent=2,
        ),
        encoding="utf-8",
    )
    (out_dir / "verifier_audit.json").write_text(
        json.dumps(
            {"run_metadata": artifacts.run_metadata, "audit": artifacts.verifier_audit},
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_jsonl(out_dir / "reasoner_queue.jsonl", artifacts.reasoner_queue)
    _write_jsonl(out_dir / "ranker_examples.jsonl", artifacts.ranker_examples)
    _write_jsonl(out_dir / "reasoner_examples.jsonl", artifacts.reasoner_examples)
    (out_dir / "report.md").write_text(_render_report(artifacts), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    payload = "".join(json.dumps(row) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8")


def _render_report(artifacts: ScoreArtifacts) -> str:
    lines = [
        "# Offline CPG Invariant Report",
        "",
        f"- Run ID: `{artifacts.run_id}`",
        f"- Surfaced findings: `{len(artifacts.violations)}`",
        f"- Candidate count: `{artifacts.run_metadata['candidate_count']}`",
        f"- Stitcher coverage state: `{artifacts.run_metadata['stitcher_coverage_state']}`",
        "",
    ]
    for finding in artifacts.violations[:20]:
        lines.extend(
            [
                f"## {finding['invariant_id']}",
                "",
                f"- Finding ID: `{finding['finding_id']}`",
                f"- Outcome: `{finding['verification']['outcome']}`",
                f"- Rank score: `{finding['rank_score']}`",
                f"- Caveats: `{', '.join(finding['verification']['caveats']) or 'none'}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"
