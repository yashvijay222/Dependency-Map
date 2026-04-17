"""Layer 2: semantic embeddings for AST nodes (OpenAI + optional local fallback)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from supabase import create_client

from app.config import settings

log = logging.getLogger(__name__)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def embed_ast_nodes(
    org_id: str,
    repo_id: str,
    commit_sha: str,
    ast_graph: dict[str, Any],
    *,
    batch_size: int = 64,
) -> None:
    """Upsert embeddings into node_embeddings when OpenAI key is configured."""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return
    if not settings.openai_api_key.strip():
        log.debug("embed_ast_nodes: OPENAI_API_KEY not set; skip")
        return

    try:
        from openai import OpenAI
    except ImportError:
        return

    client = OpenAI(api_key=settings.openai_api_key)
    sb = create_client(settings.supabase_url, settings.supabase_service_role_key)
    nodes = [n for n in (ast_graph.get("nodes") or []) if isinstance(n, dict)]
    texts: list[tuple[str, str]] = []
    for n in nodes:
        nid = str(n.get("id", ""))
        kind = str(n.get("kind", ""))
        name = str(n.get("name", ""))
        file = str(n.get("file", ""))
        snippet = str(n.get("code_snippet", ""))[:800]
        body = f"{kind} {name} in {file}: {snippet}"
        texts.append((nid, body))

    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        if not chunk:
            continue
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=[c[1] for c in chunk],
        )
        rows: list[dict[str, Any]] = []
        for (nid, body), item in zip(chunk, resp.data, strict=False):
            ch = _hash_text(body)
            vec = list(item.embedding)
            rows.append(
                {
                    "node_id": nid,
                    "repo_id": repo_id,
                    "commit_sha": commit_sha or None,
                    "embedding": vec,
                    "content_hash": ch,
                    "search_text": body[:2000],
                },
            )
        if rows:
            sb.table("node_embeddings").upsert(
                rows,
                on_conflict="repo_id,node_id,content_hash",
            ).execute()


def embed_with_codebert_fallback(texts: list[str]) -> list[list[float]] | None:
    """Optional local embeddings when torch extra installed.

    Returns None if the dependency is missing, the model cannot be downloaded
    (e.g. offline environment or proxy error), or any other runtime error
    occurs while initializing the transformer model. Callers treat None as
    "local fallback unavailable" and proceed without embeddings.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None
    try:
        model = SentenceTransformer("microsoft/codebert-base")
        out = model.encode(texts, convert_to_numpy=True)
    except Exception as exc:
        log.debug("embed_with_codebert_fallback unavailable: %s", exc)
        return None
    return [list(map(float, row)) for row in out]
