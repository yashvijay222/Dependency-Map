from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def stable_id(*parts: object) -> str:
    payload = "||".join(str(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()[:24]


def repo_node_id(repo_root: Path) -> str:
    return f"repo:{stable_id(repo_root.resolve())}"


def node_id(prefix: str, *parts: object) -> str:
    return f"{prefix}:{stable_id(prefix, *parts)}"


def edge_id(label: str, src: str, dst: str, *parts: object) -> str:
    return f"edge:{stable_id(label, src, dst, *parts)}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(data: str) -> str:
    return sha256_bytes(data.encode("utf-8", errors="ignore"))


def small_snippet(source: bytes, start_byte: int, end_byte: int, limit: int = 200) -> str:
    text = source[start_byte:end_byte].decode("utf-8", errors="ignore").strip()
    if not text:
        return ""
    return text[:limit]


def point_dict(point: tuple[int, int]) -> dict[str, int]:
    return {"row": int(point[0]), "column": int(point[1])}


def json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    return json.dumps(value, default=str)


def graph_attr_fingerprint(attrs: dict[str, Any]) -> str:
    normalized = json.dumps(json_safe(attrs), sort_keys=True, separators=(",", ":"))
    return sha256_text(normalized)
