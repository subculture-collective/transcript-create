from __future__ import annotations

import json
from typing import Any
from urllib import error, request


SYSTEM_PROMPT = """You review noisy automatic labels for a HasanAbi VOD archive.
Return only JSON. Distinguish aliases/merges from related terms.
Actions:
- keep: durable archive topic as-is.
- mark_noise: transcript fragment/filler/incomplete phrase.
- alias_to_canonical: phrase should point to an existing or proposed canonical label.
- related_label: label is not an alias, but is related to one or more labels.
Never put merely related entities into aliases. Related examples: Israel, Benjamin Netanyahu, and Gaza are related, not aliases.
"""


def build_label_review_messages(labels: list[dict[str, Any]], canonical_context: list[str] | None = None) -> list[dict[str, str]]:
    payload = {
        "labels": labels,
        "canonical_context": canonical_context or [],
        "response_schema": {
            "proposals": [
                {
                    "label_id": "string",
                    "label": "string",
                    "action": "keep|mark_noise|alias_to_canonical|related_label",
                    "canonical_label": "string|null",
                    "related_labels": ["string"],
                    "confidence": "number 0..1",
                    "rationale": "short string",
                }
            ]
        },
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _extract_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM response did not contain a JSON object")
    loaded = json.loads(stripped[start : end + 1])
    if not isinstance(loaded, dict):
        raise ValueError("LLM response JSON root must be an object")
    return loaded


def review_label_batch_openai_compatible(
    labels: list[dict[str, Any]],
    *,
    base_url: str,
    api_key: str,
    model: str,
    canonical_context: list[str] | None = None,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"
    body = {
        "model": model,
        "messages": build_label_review_messages(labels, canonical_context),
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM review request failed: HTTP {exc.code}: {detail}") from exc
    response_payload = json.loads(raw)
    content = response_payload["choices"][0]["message"]["content"]
    return _extract_json_object(str(content))


__all__ = ["build_label_review_messages", "review_label_batch_openai_compatible"]
