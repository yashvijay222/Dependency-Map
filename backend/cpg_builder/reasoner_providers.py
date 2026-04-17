"""HTTP-hosted reasoner backends (OpenAI-compatible Chat Completions, Google Gemini)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

REQUIRED_REASONER_KEYS = frozenset(
    {
        "violation",
        "confidence",
        "invariant_id",
        "witness_paths",
        "broken_contract",
        "missing_guard",
        "affected_surfaces",
        "explanation",
        "recommended_fix",
    }
)


def validate_reasoner_json(data: dict[str, Any]) -> tuple[bool, str]:
    missing = REQUIRED_REASONER_KEYS - set(data.keys())
    if missing:
        return False, f"Missing keys: {sorted(missing)}"
    if not isinstance(data.get("violation"), bool):
        return False, "violation must be boolean"
    try:
        float(data.get("confidence", 0))
    except (TypeError, ValueError):
        return False, "confidence must be numeric"
    if not isinstance(data.get("witness_paths"), list):
        return False, "witness_paths must be a list"
    if not isinstance(data.get("broken_contract"), dict):
        return False, "broken_contract must be an object"
    if not isinstance(data.get("missing_guard"), bool):
        return False, "missing_guard must be boolean"
    if not isinstance(data.get("affected_surfaces"), list):
        return False, "affected_surfaces must be a list"
    return True, ""


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    fence = re.search(r"\{[\s\S]*\}", text)
    if fence:
        try:
            parsed = json.loads(fence.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _reasoner_system_prompt() -> str:
    return (
        "You analyze code-change evidence packs for cross-system contract risk. "
        "Reply with a single JSON object only (no markdown), using exactly these keys: "
        "violation (boolean), confidence (number 0-1), invariant_id (string), "
        "witness_paths (array of objects with optional node_ids arrays), "
        "broken_contract (object), missing_guard (boolean), "
        "affected_surfaces (array of strings), explanation (string), "
        "recommended_fix (string). "
        "Base violation on whether the described seam likely breaks a real contract "
        "given the facts."
    )


def call_openai_compatible_reasoner(
    evidence_pack: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    api_key = (
        os.getenv("CPG_REASONER_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    ).strip()
    if not api_key:
        return None, "Missing CPG_REASONER_OPENAI_API_KEY or OPENAI_API_KEY"
    base = (
        os.getenv("CPG_REASONER_OPENAI_BASE_URL") or "https://api.openai.com/v1"
    ).rstrip("/")
    model = (os.getenv("CPG_REASONER_OPENAI_MODEL") or "gpt-4o-mini").strip()
    timeout = float(os.getenv("CPG_REASONER_HTTP_TIMEOUT_SEC") or "120")

    user_content = json.dumps(evidence_pack, indent=2, default=str)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _reasoner_system_prompt()},
        {
            "role": "user",
            "content": f"Invariant context:\n{user_content}\n\nReturn only the JSON object.",
        },
    ]
    body: dict[str, Any] = {
        "model": model,
        "temperature": 0.1,
        "messages": messages,
    }
    if not model.lower().startswith("o1"):
        body["response_format"] = {"type": "json_object"}

    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=body)
            if resp.status_code == 400 and "response_format" in resp.text:
                body.pop("response_format", None)
                resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as exc:
        return None, f"OpenAI HTTP error: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"OpenAI invalid JSON: {exc}"

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None, "OpenAI response missing choices[0].message.content"

    if isinstance(content, list):
        text = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    else:
        text = str(content)
    parsed = _extract_json_object(text)
    if not parsed:
        return None, "Could not parse JSON from model response"
    ok, err = validate_reasoner_json(parsed)
    if not ok:
        return None, err
    return parsed, None


def call_gemini_reasoner(evidence_pack: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    api_key = (os.getenv("CPG_REASONER_GEMINI_API_KEY") or "").strip()
    if not api_key:
        return None, "Missing CPG_REASONER_GEMINI_API_KEY"
    model = (os.getenv("CPG_REASONER_GEMINI_MODEL") or "gemini-2.0-flash").strip()
    timeout = float(os.getenv("CPG_REASONER_HTTP_TIMEOUT_SEC") or "120")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    user_text = json.dumps(evidence_pack, indent=2, default=str)
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": _reasoner_system_prompt()},
                    {"text": f"Evidence pack JSON:\n{user_text}\n\nReturn only the JSON object."},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=body)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as exc:
        return None, f"Gemini HTTP error: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"Gemini invalid JSON: {exc}"

    try:
        parts = payload["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    except (KeyError, IndexError, TypeError):
        return None, "Gemini response missing candidates[0].content.parts"

    parsed = _extract_json_object(text)
    if not parsed:
        return None, "Could not parse JSON from Gemini response"
    ok, err = validate_reasoner_json(parsed)
    if not ok:
        return None, err
    return parsed, None
