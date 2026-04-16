from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from .invariants import InvariantSpec
from .path_miner import CandidatePath


@dataclass(slots=True)
class RankedCandidate:
    candidate: CandidatePath
    score: float
    phase: str
    label_source: str
    label_strength: str
    score_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class GraphCodeBERTRanker:
    model_name: str = "microsoft/graphcodebert-base"
    max_length: int = 512
    _tokenizer: Any | None = field(init=False, default=None, repr=False)
    _model: Any | None = field(init=False, default=None, repr=False)
    _torch: Any | None = field(init=False, default=None, repr=False)
    _embedding_cache: dict[str, Any] = field(init=False, default_factory=dict, repr=False)
    _available: bool = field(init=False, default=False, repr=False)
    _load_error: str | None = field(init=False, default=None, repr=False)
    _device: str = field(init=False, default="cpu", repr=False)

    def __post_init__(self) -> None:
        self._load_model()

    @property
    def available(self) -> bool:
        return self._available

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def score(self, candidate: CandidatePath, spec: InvariantSpec | None = None) -> float:
        if not self.available:
            raise RuntimeError("GraphCodeBERTRanker is unavailable")

        candidate_embedding = self._embed_text(serialize_candidate(candidate, spec))
        query_embedding = self._embed_text(_invariant_query(candidate, spec))
        cosine = self._cosine_similarity(candidate_embedding, query_embedding)
        return round((cosine + 1.0) / 2.0, 4)

    def _load_model(self) -> None:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except Exception as exc:  # pragma: no cover - dependency import guard
            self._load_error = str(exc)
            return

        try:
            self._torch = torch
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModel.from_pretrained(self.model_name)
            self._model.to(self._device)
            self._model.eval()
            self._available = True
        except Exception as exc:  # pragma: no cover - runtime/model load guard
            self._load_error = str(exc)
            self._available = False

    def _embed_text(self, text: str) -> Any:
        cached = self._embedding_cache.get(text)
        if cached is not None:
            return cached
        assert self._tokenizer is not None
        assert self._model is not None
        assert self._torch is not None
        encoded = self._tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_length,
            padding=False,
        )
        encoded = {key: value.to(self._device) for key, value in encoded.items()}
        with self._torch.no_grad():
            outputs = self._model(**encoded)
        hidden = outputs.last_hidden_state
        mask = encoded["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
        pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1.0)
        embedding = pooled.squeeze(0).cpu()
        self._embedding_cache[text] = embedding
        return embedding

    def _cosine_similarity(self, left: Any, right: Any) -> float:
        assert self._torch is not None
        similarity = self._torch.nn.functional.cosine_similarity(left, right, dim=0)
        return float(similarity.item())


def rank_candidates(
    candidates: list[CandidatePath],
    invariants: dict[str, InvariantSpec] | None = None,
) -> list[RankedCandidate]:
    backend = (os.getenv("CPG_RANKER_BACKEND") or "graphcodebert").strip().lower()
    ranker = _build_graphcodebert_ranker() if backend != "heuristic" else None
    ranked: list[RankedCandidate] = []
    for candidate in candidates:
        spec = (invariants or {}).get(candidate.invariant_id)
        heuristic_score = _heuristic_score(candidate)
        if ranker and ranker.available:
            model_score = ranker.score(candidate, spec)
            blended_score = round((0.65 * model_score) + (0.35 * heuristic_score), 4)
            ranked.append(
                RankedCandidate(
                    candidate=candidate,
                    score=blended_score,
                    phase="phase0_graphcodebert_blend",
                    label_source="graphcodebert_inference",
                    label_strength="weak",
                    score_breakdown={
                        "heuristic_score": heuristic_score,
                        "model_score": model_score,
                    },
                )
            )
            continue
        ranked.append(
            RankedCandidate(
                candidate=candidate,
                score=heuristic_score,
                phase="phase0_heuristic",
                label_source="heuristic_only",
                label_strength="weak",
                score_breakdown={
                    "heuristic_score": heuristic_score,
                    "model_score": 0.0,
                },
            )
        )
    return sorted(ranked, key=lambda item: (-item.score, item.candidate.id))


def serialize_candidate(candidate: CandidatePath, spec: InvariantSpec | None = None) -> str:
    path_nodes = " -> ".join(candidate.node_ids)
    path_edges = " -> ".join(candidate.edge_ids) if candidate.edge_ids else "none"
    changed = ", ".join(candidate.changed_anchors) if candidate.changed_anchors else "none"
    facts = ", ".join(
        f"{key}={candidate.facts[key]!r}" for key in sorted(candidate.facts.keys())
    ) or "none"
    features = ", ".join(
        f"{key}={candidate.heuristic_features[key]!r}"
        for key in sorted(candidate.heuristic_features.keys())
    ) or "none"
    description = spec.description if spec else ""
    return "\n".join(
        [
            f"invariant: {candidate.invariant_id}",
            f"description: {description}",
            f"seam_type: {candidate.seam_type}",
            f"seed_id: {candidate.seed_id}",
            f"path_nodes: {path_nodes}",
            f"path_edges: {path_edges}",
            f"changed_anchors: {changed}",
            f"facts: {facts}",
            f"heuristics: {features}",
        ]
    )


def _invariant_query(candidate: CandidatePath, spec: InvariantSpec | None = None) -> str:
    description = spec.description if spec else candidate.invariant_id.replace("_", " ")
    return (
        "Rank this candidate path for likely invariant violation. "
        f"Invariant: {candidate.invariant_id}. "
        f"Description: {description}. "
        f"Seam type: {candidate.seam_type}."
    )


@lru_cache(maxsize=1)
def _build_graphcodebert_ranker() -> GraphCodeBERTRanker | None:
    model_name = (os.getenv("CPG_GRAPHCODEBERT_MODEL") or "microsoft/graphcodebert-base").strip()
    max_length = int(os.getenv("CPG_GRAPHCODEBERT_MAX_LENGTH") or "512")
    ranker = GraphCodeBERTRanker(model_name=model_name, max_length=max_length)
    return ranker if ranker.available else None


def _heuristic_score(candidate: CandidatePath) -> float:
    score = 0.2
    score += 0.15 * min(3, candidate.heuristic_features.get("changed_anchor_count", 0))
    if candidate.invariant_id == "schema_entity_still_referenced":
        if candidate.facts.get("referenced_in_code"):
            score += 0.3
        if not candidate.facts.get("defined_in_migration", True):
            score += 0.35
    if candidate.invariant_id == "frontend_route_binding":
        if not candidate.facts.get("matched_route_id"):
            score += 0.55
    if candidate.invariant_id == "missing_guard_or_rls_gap":
        if candidate.facts.get("auth_mode") != "explicit_guard":
            score += 0.35
        if candidate.facts.get("uses_service_role"):
            score += 0.15
    if candidate.invariant_id == "celery_task_binding":
        if candidate.facts.get("target_unresolved"):
            score += 0.5
    return round(min(score, 0.99), 4)


def ranker_example(
    rank: RankedCandidate, repo_id: str, base_ref: str, head_ref: str
) -> dict[str, Any]:
    candidate = rank.candidate
    return {
        "example_id": candidate.id,
        "invariant_id": candidate.invariant_id,
        "candidate_path": candidate.node_ids,
        "edge_sequence": candidate.edge_ids,
        "node_attrs": candidate.facts,
        "diff_features": candidate.heuristic_features,
        "label": None,
        "label_source": rank.label_source,
        "label_strength": rank.label_strength,
        "rank_phase": rank.phase,
        "score_breakdown": rank.score_breakdown,
        "repo_id": repo_id,
        "base_ref": base_ref,
        "head_ref": head_ref,
    }
