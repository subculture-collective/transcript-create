from __future__ import annotations

import re
from typing import Any, Iterable

DEFAULT_CHAPTER_MS = 10 * 60 * 1000
LOW_INFORMATION_WORDS = {
    "anyway",
    "do",
    "here",
    "it",
    "mr",
    "on",
    "that",
    "there",
    "this",
    "well",
    "yeah",
    "yep",
    "yes",
    "you",
    "yup",
}


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace(">>", " ")).strip()


def _truncate(value: str, limit: int) -> str:
    value = _clean_text(value)
    if len(value) <= limit:
        return value
    shortened = value[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{shortened or value[: limit - 1]}…"


def _chapter_title(text: str, index: int) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", _clean_text(text), maxsplit=1)[0]
    title = _truncate(sentence, 72)
    words = re.findall(r"[a-z0-9]+", title.lower())
    content_words = [word for word in words if word not in LOW_INFORMATION_WORDS]
    if not title or not content_words:
        return "Opening" if index == 0 else f"Transcript section {index + 1}"
    return f"Opening: {title}" if index == 0 else title


def _representative_evidence(group: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    filler = {"again", "okay", "ok", "wow", "yeah", "right", "anyway", "so"}
    for block in group:
        sentences = re.split(r"(?<=[.!?])\s+", _clean_text(str(block.get("text") or "")))
        for sentence in sentences:
            words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", sentence)
            normalized = " ".join(words).casefold()
            if len(words) < 4 or normalized in filler:
                continue
            return block, sentence
    first = group[0]
    return first, _clean_text(str(first.get("text") or ""))


def build_grounded_chapters(
    blocks: Iterable[dict[str, Any]],
    *,
    duration_ms: int | None = None,
    target_chapter_ms: int = DEFAULT_CHAPTER_MS,
) -> list[dict[str, Any]]:
    """Build navigable chapters whose title and summary quote transcript evidence.

    This fallback makes no semantic claims beyond the source text. Persisted,
    reviewed chapters can replace it without changing the API contract.
    """

    ordered = sorted(
        (dict(block) for block in blocks if _clean_text(str(block.get("text") or ""))),
        key=lambda block: (int(block.get("start_ms") or 0), int(block.get("block_index") or 0)),
    )
    if not ordered:
        return []

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    group_start = int(ordered[0].get("start_ms") or 0)
    for block in ordered:
        start_ms = int(block.get("start_ms") or 0)
        if current and start_ms - group_start >= target_chapter_ms:
            groups.append(current)
            current = []
            group_start = start_ms
        current.append(block)
    if current:
        groups.append(current)

    chapters: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        evidence, representative_text = _representative_evidence(group)
        start_ms = int(group[0].get("start_ms") or 0)
        next_start = int(groups[index + 1][0].get("start_ms") or 0) if index + 1 < len(groups) else None
        natural_end = int(group[-1].get("end_ms") or start_ms)
        end_ms = next_start if next_start is not None else max(natural_end, duration_ms or 0)
        quote = _truncate(representative_text, 280)
        chapters.append(
            {
                "chapter_index": index,
                "start_ms": start_ms,
                "end_ms": max(end_ms, start_ms + 1),
                "title": _chapter_title(quote, index),
                "summary": quote,
                "confidence_score": 1.0,
                "status": "published",
                "source": "transcript",
                "evidence": [
                    {
                        "block_index": int(evidence.get("block_index") or 0),
                        "start_ms": int(evidence.get("start_ms") or 0),
                        "end_ms": int(evidence.get("end_ms") or 0),
                        "text": quote,
                    }
                ],
            }
        )
    return chapters


__all__ = ["DEFAULT_CHAPTER_MS", "build_grounded_chapters"]
