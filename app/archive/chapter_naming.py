from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from .semantic_chapters import SemanticChapterProposal

PROMPT_VERSION = "archive-chapter-naming-v1"
logger = logging.getLogger(__name__)

CHAPTER_NAMING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "minLength": 8, "maxLength": 100},
        "summary": {"type": "string", "minLength": 12, "maxLength": 300},
        "subjects": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string", "minLength": 2, "maxLength": 80},
        },
        "keywords": {
            "type": "array",
            "maxItems": 10,
            "items": {"type": "string", "minLength": 2, "maxLength": 100},
        },
        "evidence_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {"type": "string"},
        },
    },
    "required": ["title", "summary", "subjects", "keywords", "evidence_ids"],
    "additionalProperties": False,
}


class ChapterNamingValidationError(ValueError):
    """Raised when a chapter name or citation is not grounded in supplied evidence."""


@dataclass(frozen=True)
class NamedChapter:
    start_ms: int
    end_ms: int
    title: str
    summary: str
    subjects: tuple[str, ...]
    keywords: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    model: str
    prompt_version: str = PROMPT_VERSION
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "title": self.title,
            "summary": self.summary,
            "subjects": list(self.subjects),
            "keywords": list(self.keywords),
            "evidence_ids": list(self.evidence_ids),
            "model": self.model,
            "prompt_version": self.prompt_version,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


def _evidence_for_proposal(proposal: SemanticChapterProposal, windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for index in proposal.evidence_window_indexes:
        if index < 0 or index >= len(windows):
            raise ChapterNamingValidationError("chapter proposal references an unknown transcript window")
        window = windows[index]
        text = " ".join(str(window.get("text") or "").split())
        if not text:
            continue
        evidence.append(
            {
                "evidence_id": f"w{index}",
                "start_ms": int(window.get("start_ms") or 0),
                "end_ms": int(window.get("end_ms") or 0),
                "text": text[:1_500],
            }
        )
    if not evidence:
        raise ChapterNamingValidationError("chapter naming requires transcript evidence")
    return evidence


def build_chapter_naming_request(
    proposal: SemanticChapterProposal,
    windows: list[dict[str, Any]],
    *,
    model: str,
) -> dict[str, Any]:
    evidence = _evidence_for_proposal(proposal, windows)
    system = f"""You name and summarize chapters for a broadcast archive.
Prompt version: {PROMPT_VERSION}
Use only the supplied transcript evidence. Do not invent people, places, events, numbers, outcomes, or opinions.
Write a specific editorial title, not a transcript quote, filler phrase, or sentence fragment.
Subjects are the few material entities/issues in this span. Keywords are grounded retrieval phrases.
Every subject and keyword must be directly supported by the cited evidence text.
Cite one to three supplied evidence_id values. Return only JSON matching the supplied schema."""
    user = {
        "span": {"start_ms": proposal.start_ms, "end_ms": proposal.end_ms},
        "evidence": evidence,
        "instructions": "Name this chapter and identify its grounded subjects and retrieval keywords.",
    }
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        "stream": False,
        "think": False,
        "format": CHAPTER_NAMING_SCHEMA,
        "options": {"temperature": 0, "num_predict": 320},
        "keep_alive": "10m",
    }


def _clean_string(value: Any, *, field: str, minimum: int, maximum: int) -> str:
    cleaned = " ".join(str(value or "").split())
    if not minimum <= len(cleaned) <= maximum:
        raise ChapterNamingValidationError(f"chapter {field} has an invalid length")
    return cleaned


def _clean_list(value: Any, *, field: str, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ChapterNamingValidationError(f"chapter {field} must be a list with at most {maximum} items")
    cleaned = tuple(dict.fromkeys(" ".join(str(item).split()) for item in value if str(item).strip()))
    return cleaned


_GROUNDING_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
}


def _stem(token: str) -> str:
    lowered = token.casefold()
    for suffix in ("ization", "ation", "ing", "ers", "er", "ed", "s"):
        if len(lowered) > len(suffix) + 3 and lowered.endswith(suffix):
            return lowered[: -len(suffix)]
    return lowered


def _phrase_is_grounded(phrase: str, evidence_text: str) -> bool:
    evidence_stems = {_stem(token) for token in re.findall(r"[A-Za-z0-9'-]+", evidence_text)}
    phrase_stems = {
        _stem(token) for token in re.findall(r"[A-Za-z0-9'-]+", phrase) if token.casefold() not in _GROUNDING_STOPWORDS
    }
    return bool(phrase_stems) and phrase_stems <= evidence_stems


_EDITORIAL_TITLE_STEMS = {
    "analysi",
    "breakdown",
    "debate",
    "discus",
    "discussion",
    "explain",
    "prepare",
    "react",
    "response",
    "update",
}


def _title_is_grounded(title: str, evidence_text: str) -> bool:
    evidence_stems = {_stem(token) for token in re.findall(r"[A-Za-z0-9'-]+", evidence_text)}
    title_stems = {
        _stem(token) for token in re.findall(r"[A-Za-z0-9'-]+", title) if token.casefold() not in _GROUNDING_STOPWORDS
    }
    return bool(title_stems) and title_stems <= evidence_stems | _EDITORIAL_TITLE_STEMS


def _unsupported_summary_entities(summary: str, evidence_text: str) -> set[str]:
    evidence_stems = {_stem(token) for token in re.findall(r"[A-Za-z0-9'-]+", evidence_text)}
    exemptions = {"Additionally", "However", "It", "The", "They", "This", "Workers"}
    return {
        token
        for token in re.findall(r"\b[A-Z][A-Za-z'-]{2,}\b", summary)
        if token not in exemptions and _stem(token) not in evidence_stems
    }


_EXTRACTIVE_STOPWORDS = _GROUNDING_STOPWORDS | {
    "about",
    "again",
    "anyway",
    "like",
    "okay",
    "over",
    "really",
    "right",
    "so",
    "that",
    "this",
    "yeah",
}


def _extractive_fallback(
    payload: dict[str, Any],
    proposal: SemanticChapterProposal,
    windows: list[dict[str, Any]],
    *,
    model: str,
) -> NamedChapter:
    evidence = _evidence_for_proposal(proposal, windows)
    candidates: list[tuple[int, int, int, int, str, str, list[str]]] = []
    for evidence_position, item in enumerate(evidence):
        sentences = re.split(r"(?<=[.!?])\s+", str(item["text"]))
        for sentence_position, sentence in enumerate(sentences):
            cleaned = " ".join(sentence.split()).strip()
            words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", cleaned)
            content_words = [word for word in words if word.casefold() not in _EXTRACTIVE_STOPWORDS]
            if not content_words:
                continue
            score = len({_stem(word) for word in content_words})
            candidates.append(
                (
                    score,
                    len(content_words),
                    -evidence_position,
                    -sentence_position,
                    str(item["evidence_id"]),
                    cleaned,
                    content_words,
                )
            )
    if not candidates:
        item = evidence[0]
        cleaned = " ".join(str(item["text"]).split())
        content_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", cleaned)
        candidates.append((0, len(content_words), 0, 0, str(item["evidence_id"]), cleaned, content_words))

    _score, _word_count, _evidence_position, _sentence_position, evidence_id, summary, content_words = max(candidates)
    title = " ".join(content_words[:9]).strip() or summary
    if len(title) > 100:
        title = title[:100].rsplit(" ", 1)[0].rstrip(" ,;:-")
    if len(summary) > 300:
        summary = summary[:300].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return NamedChapter(
        start_ms=proposal.start_ms,
        end_ms=proposal.end_ms,
        title=title,
        summary=summary,
        subjects=(),
        keywords=(),
        evidence_ids=(evidence_id,),
        model=f"{model}:extractive-fallback",
        prompt_tokens=int(payload.get("prompt_eval_count") or 0),
        completion_tokens=int(payload.get("eval_count") or 0),
    )


def parse_chapter_naming_response(
    payload: dict[str, Any],
    proposal: SemanticChapterProposal,
    windows: list[dict[str, Any]],
    *,
    model: str,
) -> NamedChapter:
    evidence = _evidence_for_proposal(proposal, windows)
    evidence_by_id = {str(item["evidence_id"]): item for item in evidence}
    try:
        parsed = json.loads(str(payload["message"]["content"]))
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ChapterNamingValidationError("model response was not valid chapter JSON") from exc
    if not isinstance(parsed, dict):
        raise ChapterNamingValidationError("model response must be a chapter object")

    title = _clean_string(parsed.get("title"), field="title", minimum=8, maximum=100)
    summary = _clean_string(parsed.get("summary"), field="summary", minimum=12, maximum=300)
    subjects = _clean_list(parsed.get("subjects"), field="subjects", maximum=5)
    keywords = _clean_list(parsed.get("keywords"), field="keywords", maximum=10)
    evidence_ids = _clean_list(parsed.get("evidence_ids"), field="evidence_ids", maximum=3)
    if not evidence_ids or any(evidence_id not in evidence_by_id for evidence_id in evidence_ids):
        raise ChapterNamingValidationError("chapter cited unknown or missing evidence")

    cited_text = " ".join(str(evidence_by_id[evidence_id]["text"]) for evidence_id in evidence_ids)
    if not _title_is_grounded(title, cited_text):
        raise ChapterNamingValidationError("chapter title is unsupported by cited evidence")
    unsupported_entities = _unsupported_summary_entities(summary, cited_text)
    if unsupported_entities:
        raise ChapterNamingValidationError(
            "chapter summary introduced unsupported named terms: " + ", ".join(sorted(unsupported_entities))
        )
    for field, phrases in (("subject", subjects), ("keyword", keywords)):
        unsupported = [phrase for phrase in phrases if not _phrase_is_grounded(phrase, cited_text)]
        if unsupported:
            raise ChapterNamingValidationError(f"chapter {field} is unsupported by cited evidence: {unsupported[0]}")
    unsupported_numbers = {
        number for number in re.findall(r"\b\d+(?:\.\d+)?%?\b", f"{title} {summary}") if number not in cited_text
    }
    if unsupported_numbers:
        raise ChapterNamingValidationError("chapter introduced unsupported numbers")

    return NamedChapter(
        start_ms=proposal.start_ms,
        end_ms=proposal.end_ms,
        title=title,
        summary=summary,
        subjects=subjects,
        keywords=keywords,
        evidence_ids=evidence_ids,
        model=model,
        prompt_tokens=int(payload.get("prompt_eval_count") or 0),
        completion_tokens=int(payload.get("eval_count") or 0),
    )


def generate_chapter_name(
    proposal: SemanticChapterProposal,
    windows: list[dict[str, Any]],
    *,
    base_url: str,
    model: str,
    timeout_seconds: float = 180.0,
) -> NamedChapter:
    url = f"{base_url.rstrip('/')}/api/chat"
    body = build_chapter_naming_request(proposal, windows, model=model)
    req = request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama chapter naming request failed: HTTP {exc.code}: {detail}") from exc
    except (error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Ollama chapter naming request failed: {exc}") from exc
    try:
        return parse_chapter_naming_response(payload, proposal, windows, model=model)
    except ChapterNamingValidationError as exc:
        logger.warning(
            "Using extractive chapter fallback after rejected model output",
            extra={
                "model": model,
                "start_ms": proposal.start_ms,
                "end_ms": proposal.end_ms,
                "validation_error": str(exc),
            },
        )
        return _extractive_fallback(payload, proposal, windows, model=model)


__all__ = [
    "CHAPTER_NAMING_SCHEMA",
    "ChapterNamingValidationError",
    "NamedChapter",
    "PROMPT_VERSION",
    "build_chapter_naming_request",
    "generate_chapter_name",
    "parse_chapter_naming_response",
]
