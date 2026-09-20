from __future__ import annotations

import json
import math
import time
from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib import error, request

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .enrichment_runner import EpisodeInput, TranscriptBlockInput
from .labeling.benchmark import EpisodePrediction, PredictedChapter

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
PROMPT_VERSION = "archive-episode-enrichment-v7"

CATEGORY_LABELS: dict[str, str] = {
    "chadvice": "Chadvice",
    "okbuddy": "OKBuddy",
    "gaming": "Gaming",
    "guests": "Guests",
    "news": "News",
    "politics": "Politics",
    "react": "React",
    "debate": "Debate",
    "interview": "Interview",
    "irl": "IRL",
}
CATEGORY_GUIDANCE: dict[str, str] = {
    "chadvice": "Only the explicitly named recurring Chadvice advice segment; ordinary advice or relationship talk does not qualify.",
    "okbuddy": "Only the explicitly named OKBuddy subreddit/reaction segment.",
    "gaming": "Sustained video-game play or discussion; sports, billiards, and other physical/table games do not qualify.",
    "guests": "One or more guests materially appear or participate in the stream; a person discussed but absent does not qualify.",
    "news": "Sustained coverage of current news reporting or events, not a brief news tangent.",
    "politics": "Sustained political analysis or political-event coverage, not a brief political tangent.",
    "react": "Sustained viewing and commentary on external media, not ordinary conversation or chat responses.",
    "debate": "A sustained adversarial debate between participants, not casual disagreement.",
    "interview": "A sustained, structured interview with a guest, not ordinary guest conversation.",
    "irl": "A substantial real-world, away-from-desk stream such as travel, events, venues, or street activity.",
}

EPISODE_ENRICHMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subjects": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {"type": "string", "minLength": 2, "maxLength": 80},
        },
        "keywords": {
            "type": "array",
            "minItems": 1,
            "maxItems": 24,
            "items": {"type": "string", "minLength": 2, "maxLength": 100},
        },
        "categories": {
            "type": "array",
            "minItems": 0,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "enum": list(CATEGORY_LABELS)},
                    "evidence_block_indexes": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 3,
                        "items": {"type": "integer", "minimum": 0},
                    },
                },
                "required": ["slug", "evidence_block_indexes"],
                "additionalProperties": False,
            },
        },
        "chapters": {
            "type": "array",
            "minItems": 2,
            "maxItems": 40,
            "items": {
                "type": "object",
                "properties": {
                    "start_ms": {"type": "integer", "minimum": 0},
                    "title": {"type": "string", "minLength": 8, "maxLength": 100},
                    "summary": {"type": "string", "minLength": 12, "maxLength": 300},
                    "evidence_block_indexes": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 3,
                        "items": {"type": "integer", "minimum": 0},
                    },
                },
                "required": ["start_ms", "title", "summary", "evidence_block_indexes"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["subjects", "keywords", "categories", "chapters"],
    "additionalProperties": False,
}


class EpisodeChapterCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_ms: int = Field(ge=0)
    title: str = Field(min_length=8, max_length=100)
    summary: str = Field(min_length=12, max_length=300)
    evidence_block_indexes: list[int] = Field(min_length=1, max_length=3)


class EpisodeCategoryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    evidence_block_indexes: list[int] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_slug(self) -> EpisodeCategoryCandidate:
        if self.slug not in CATEGORY_LABELS:
            raise ValueError("unknown category slug")
        return self


class EpisodeEnrichmentCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subjects: list[str] = Field(min_length=1, max_length=12)
    keywords: list[str] = Field(min_length=1, max_length=24)
    categories: list[EpisodeCategoryCandidate] = Field(max_length=3)
    # Each bounded provider response is capped at 40 chapters by the request
    # schema. The merged episode may legitimately contain more than that.
    chapters: list[EpisodeChapterCandidate] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_chapter_starts(self) -> EpisodeEnrichmentCandidate:
        starts = [chapter.start_ms for chapter in self.chapters]
        if starts[0] != 0:
            raise ValueError("first chapter must start at zero")
        if starts != sorted(set(starts)):
            raise ValueError("chapter starts must be unique and increasing")
        return self


class OpenRouterResponseValidationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        elapsed_seconds: float,
        failure_details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cost_usd = cost_usd
        self.elapsed_seconds = elapsed_seconds
        self.failure_details = failure_details or {}


class OpenRouterBudgetExceededError(RuntimeError):
    """Report cumulative usage when a hierarchical run reaches its budget."""

    def __init__(
        self,
        *,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        elapsed_seconds: float,
        max_cost_usd: float,
        window_count: int,
        attempted_window_count: int,
    ) -> None:
        super().__init__(
            "archive enrichment cost reached the configured per-video limit " f"({cost_usd:.6f} >= {max_cost_usd:.6f})"
        )
        self.provider = provider
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cost_usd = cost_usd
        self.elapsed_seconds = elapsed_seconds
        self.max_cost_usd = max_cost_usd
        self.window_count = window_count
        self.attempted_window_count = attempted_window_count


class OpenRouterHierarchicalGenerationError(RuntimeError):
    """Preserve measured usage when a later provider window fails."""

    failure_details: dict[str, Any]

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        elapsed_seconds: float,
        window_count: int,
        attempted_window_count: int,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cost_usd = cost_usd
        self.elapsed_seconds = elapsed_seconds
        self.window_count = window_count
        self.attempted_window_count = attempted_window_count


class OpenRouterEpisodeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    video_id: str
    model: str
    provider: str
    prompt_version: str
    candidate: EpisodeEnrichmentCandidate
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    elapsed_seconds: float
    first_boundary_normalized: bool = False
    summaries_truncated: int = 0
    label_values_trimmed: int = 0
    evidence_citations_trimmed: int = 0
    chapter_boundaries_reordered: bool = False
    chapter_boundaries_deduplicated: int = 0
    chapter_boundaries_realigned: int = 0
    categories_dropped: int = 0
    category_rejections: list[dict[str, str]] = Field(default_factory=list)
    evidence_overlap_violations: int = 0
    window_count: int = 1

    def prediction(self, duration_ms: int) -> EpisodePrediction:
        chapters: list[PredictedChapter] = []
        for index, chapter in enumerate(self.candidate.chapters):
            end_ms = (
                self.candidate.chapters[index + 1].start_ms if index + 1 < len(self.candidate.chapters) else duration_ms
            )
            chapters.append(PredictedChapter(start_ms=chapter.start_ms, end_ms=end_ms, title=chapter.title))
        return EpisodePrediction(
            video_id=self.video_id,
            subjects=list(dict.fromkeys(self.candidate.subjects)),
            keywords=list(dict.fromkeys(self.candidate.keywords)),
            chapters=chapters,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "model": self.model,
            "provider": self.provider,
            "prompt_version": self.prompt_version,
            "candidate": self.candidate.model_dump(mode="json"),
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "cost_usd": self.cost_usd,
                "elapsed_seconds": round(self.elapsed_seconds, 4),
            },
            "normalizations": {
                "first_boundary_to_zero": self.first_boundary_normalized,
                "summaries_truncated": self.summaries_truncated,
                "label_values_trimmed": self.label_values_trimmed,
                "evidence_citations_trimmed": self.evidence_citations_trimmed,
                "chapter_boundaries_reordered": self.chapter_boundaries_reordered,
                "chapter_boundaries_deduplicated": self.chapter_boundaries_deduplicated,
                "chapter_boundaries_realigned": self.chapter_boundaries_realigned,
                "categories_dropped": self.categories_dropped,
                "category_rejections": self.category_rejections,
            },
            "validation": {"evidence_overlap_violations": self.evidence_overlap_violations},
            "window_count": self.window_count,
        }


def _target_chapter_count(duration_ms: int) -> int:
    return max(6, min(30, round(duration_ms / (25 * 60 * 1000))))


def build_openrouter_episode_request(
    episode: EpisodeInput,
    *,
    model: str,
    allow_provider_fallbacks: bool = False,
    provider_only: list[str] | None = None,
) -> dict[str, Any]:
    target_count = _target_chapter_count(episode.duration_ms)
    response_schema = deepcopy(EPISODE_ENRICHMENT_SCHEMA)
    chapter_schema = response_schema["properties"]["chapters"]
    chapter_schema["minItems"] = max(2, target_count - 2)
    chapter_schema["maxItems"] = min(40, target_count + 2)
    evidence_schema = response_schema["properties"]["chapters"]["items"]["properties"]["evidence_block_indexes"][
        "items"
    ]
    evidence_schema["maximum"] = max(block.block_index for block in episode.blocks)
    category_evidence_schema = response_schema["properties"]["categories"]["items"]["properties"][
        "evidence_block_indexes"
    ]["items"]
    category_evidence_schema["maximum"] = max(block.block_index for block in episode.blocks)
    transcript = [
        {
            "block_index": block.block_index,
            "start_ms": block.start_ms,
            "end_ms": block.end_ms,
            "text": block.text,
        }
        for block in episode.blocks
    ]
    system = f"""You are the senior archive editor for a broadcast archive.
Prompt version: {PROMPT_VERSION}
Create useful navigation chapters and grounded retrieval metadata from the supplied timestamped transcript.
Use only the transcript. Do not invent people, events, claims, games, places, or outcomes.
Prefer coherent editorial sections over brief conversational shifts. Merge adjacent discussion of the same subject.
Titles must be specific, concise, safe to publish, and understandable without surrounding transcript text.
Do not reproduce slurs, insults, profanity, sponsor copy, chat filler, or sentence fragments in titles.
Subjects are the episode's sustained primary entities or issues. Keywords are specific phrases a user might search.
Choose zero to three episode-defining categories only from the supplied controlled taxonomy and definitions.
A category must characterize a substantial portion of the episode; do not classify from a short tangent.
Return an empty category list when no controlled category fits instead of choosing a weak match.
Cite blocks from distinct parts of the episode that directly support each category when possible.
Every chapter must cite one to three block indexes whose text directly demonstrates its subject.
Return only JSON matching the supplied schema."""
    user = {
        "video_id": episode.video_id,
        "video_title": episode.title,
        "duration_ms": episode.duration_ms,
        "transcript_source": episode.transcript_source,
        "transcript_coverage": episode.transcript_coverage,
        "transcript_selection_reason": episode.transcript_selection_reason,
        "target_chapter_count": target_count,
        "category_taxonomy": CATEGORY_LABELS,
        "category_definitions": CATEGORY_GUIDANCE,
        "chapter_guidance": {
            "preferred_duration_minutes": "15-35",
            "first_start_ms": 0,
            "maximum_chapters": 40,
            "instructions": "Choose chapter starts; the system derives each end from the next start.",
        },
        "transcript_blocks": transcript,
    }
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False, separators=(",", ":"))},
        ],
        "stream": False,
        "temperature": 0,
        "max_tokens": 8_000,
        "reasoning": {"enabled": False, "exclude": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "hasanara_episode_enrichment",
                "strict": True,
                "schema": response_schema,
            },
        },
        "provider": {
            **({"only": provider_only} if provider_only else {}),
            "allow_fallbacks": allow_provider_fallbacks,
            "data_collection": "deny",
            "require_parameters": True,
        },
        "usage": {"include": True},
    }


def _validation_summary(exc: ValidationError) -> str:
    messages = []
    for item in exc.errors(include_input=False)[:3]:
        location = ".".join(str(part) for part in item.get("loc", ())) or "response"
        messages.append(f"{location}: {item.get('msg', 'invalid value')}")
    return "; ".join(messages)


def _category_rejection_reason(category: dict[str, Any], episode: EpisodeInput) -> str | None:
    slug = category.get("slug")
    indexes = category.get("evidence_block_indexes")
    if not isinstance(slug, str) or not isinstance(indexes, list):
        return "invalid_category_payload"
    block_by_index = {block.block_index: block for block in episode.blocks}
    if any(isinstance(index, int) and index not in block_by_index for index in indexes):
        # Preserve the category so the strict unknown-evidence check below can
        # reject the complete provider response instead of silently repairing it.
        return None
    blocks = [block_by_index[index] for index in indexes if isinstance(index, int) and index in block_by_index]
    title = (episode.title or "").casefold()
    if slug in {"chadvice", "okbuddy"}:
        marker = CATEGORY_LABELS[slug].casefold()
        evidence_text = " ".join(block.text for block in blocks).casefold()
        return None if marker in title or marker in evidence_text else "required_segment_marker_missing"
    if CATEGORY_LABELS.get(slug, "").casefold() in title:
        return None
    if len(blocks) < 2:
        return "insufficient_evidence_blocks"
    evidence_span_ms = max(block.start_ms for block in blocks) - min(block.start_ms for block in blocks)
    if evidence_span_ms < episode.duration_ms * 0.2:
        return "insufficient_evidence_span"
    return None


def _category_rejection(category: dict[str, Any], reason: str) -> dict[str, str]:
    slug = category.get("slug")
    return {"slug": slug if isinstance(slug, str) else "unknown", "reason": reason}


def _deduplicate_and_limit_labels(values: Any, limit: int, max_length: int) -> tuple[Any, int]:
    """Repair only well-typed model label lists, preserving strict validation otherwise."""
    if not isinstance(values, list) or not all(
        isinstance(value, str) and 2 <= len(value) <= max_length for value in values
    ):
        return values, 0
    retained: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(value.casefold().split())
        if normalized in seen:
            continue
        seen.add(normalized)
        retained.append(value)
        if len(retained) == limit:
            break
    return retained, len(values) - len(retained)


def _parse_response(
    payload: dict[str, Any],
    episode: EpisodeInput,
    *,
    model: str,
    elapsed: float,
    defer_category_sustained_validation: bool = False,
) -> OpenRouterEpisodeResult:
    raw_usage = payload.get("usage")
    usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
    provider = str(payload.get("provider") or "unknown")
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    cost_usd = float(usage.get("cost") or 0.0)

    def invalid(message: str, details: dict[str, Any] | None = None) -> OpenRouterResponseValidationError:
        return OpenRouterResponseValidationError(
            message,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            elapsed_seconds=elapsed,
            failure_details=details,
        )

    provider_error = payload.get("error")
    if isinstance(provider_error, dict):
        # Never persist raw provider text/metadata: it may echo request contents.
        code = provider_error.get("code")
        safe_code = str(code) if isinstance(code, int) and 100 <= code <= 599 else "unknown"
        metadata = provider_error.get("metadata")
        error_type = metadata.get("error_type") if isinstance(metadata, dict) else None
        generation_id = payload.get("id")
        details = {
            "error_code": safe_code,
            "usage_reported": isinstance(usage.get("cost"), (int, float)) and not isinstance(usage.get("cost"), bool),
            "transient": code in (502, 503) and error_type in (None, "server", "overloaded", "provider_unavailable"),
        }
        if error_type in ("server", "overloaded", "provider_unavailable", "rate_limit_exceeded"):
            details["error_type"] = error_type
        if (
            isinstance(generation_id, str)
            and generation_id.startswith("gen-")
            and len(generation_id) <= 128
            and all(char.isalnum() or char in "-_" for char in generation_id)
        ):
            details["generation_id"] = generation_id
        raise invalid(f"OpenRouter request failed: response error code {safe_code}", details)
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise invalid("OpenRouter request failed: response did not contain assistant content") from exc
    if not isinstance(content, str) or not content.strip():
        raise invalid("OpenRouter request failed: assistant content was empty or not text")
    try:
        raw_candidate = json.loads(content)
    except json.JSONDecodeError as exc:
        raise invalid("OpenRouter response was not JSON") from exc
    first_boundary_normalized = False
    summaries_truncated = 0
    label_values_trimmed = 0
    evidence_citations_trimmed = 0
    chapter_boundaries_reordered = False
    chapter_boundaries_deduplicated = 0
    categories_dropped = 0
    category_rejections: list[dict[str, str]] = []
    if isinstance(raw_candidate, dict):
        for field, limit, max_length in (("subjects", 12, 80), ("keywords", 24, 100)):
            repaired, trimmed = _deduplicate_and_limit_labels(raw_candidate.get(field), limit, max_length)
            raw_candidate[field] = repaired
            label_values_trimmed += trimmed
        chapters = raw_candidate.get("chapters")
        if isinstance(chapters, list) and chapters and all(isinstance(chapter, dict) for chapter in chapters):
            starts = [chapter.get("start_ms") for chapter in chapters]
            if all(isinstance(start, int) for start in starts):
                ordered = sorted(chapters, key=lambda chapter: chapter["start_ms"])
                chapter_boundaries_reordered = ordered != chapters
                chapters = []
                seen_starts: set[int] = set()
                for chapter in ordered:
                    start_ms = chapter["start_ms"]
                    if start_ms in seen_starts:
                        chapter_boundaries_deduplicated += 1
                        continue
                    seen_starts.add(start_ms)
                    chapters.append(chapter)
                raw_candidate["chapters"] = chapters
            first_start = chapters[0].get("start_ms")
            if isinstance(first_start, int) and first_start > 0:
                chapters[0]["start_ms"] = 0
                first_boundary_normalized = True
            for chapter in chapters:
                if not isinstance(chapter, dict):
                    continue
                summary = chapter.get("summary")
                if isinstance(summary, str) and len(summary) > 300:
                    chapter["summary"] = summary[:300].rsplit(" ", 1)[0].rstrip(" ,;:-")
                    summaries_truncated += 1
                evidence = chapter.get("evidence_block_indexes")
                if isinstance(evidence, list) and len(evidence) > 3:
                    chapter["evidence_block_indexes"] = list(dict.fromkeys(evidence))[:3]
                    evidence_citations_trimmed += len(evidence) - len(chapter["evidence_block_indexes"])
        categories = raw_candidate.get("categories")
        if isinstance(categories, list):
            for category in categories:
                if not isinstance(category, dict):
                    continue
                evidence = category.get("evidence_block_indexes")
                if isinstance(evidence, list) and len(evidence) > 3:
                    category["evidence_block_indexes"] = list(dict.fromkeys(evidence))[:3]
                    evidence_citations_trimmed += len(evidence) - len(category["evidence_block_indexes"])
            if not defer_category_sustained_validation:
                retained_categories = []
                for category in categories:
                    if not isinstance(category, dict):
                        categories_dropped += 1
                        category_rejections.append({"slug": "unknown", "reason": "invalid_category_payload"})
                        continue
                    reason = _category_rejection_reason(category, episode)
                    if reason is None:
                        retained_categories.append(category)
                    else:
                        categories_dropped += 1
                        category_rejections.append(_category_rejection(category, reason))
                raw_candidate["categories"] = retained_categories
    try:
        candidate = EpisodeEnrichmentCandidate.model_validate(raw_candidate)
    except ValidationError as exc:
        raise invalid(f"OpenRouter episode enrichment failed validation: {_validation_summary(exc)}") from exc

    if candidate.chapters[-1].start_ms >= episode.duration_ms:
        raise invalid("final chapter starts outside the episode")
    block_by_index = {block.block_index: block for block in episode.blocks}
    for category in candidate.categories:
        if any(block_index not in block_by_index for block_index in category.evidence_block_indexes):
            raise invalid("category cites an unknown transcript block")
    evidence_overlap_violations = 0
    chapter_boundaries_realigned = 0
    for index, chapter in enumerate(candidate.chapters):
        end_ms = candidate.chapters[index + 1].start_ms if index + 1 < len(candidate.chapters) else episode.duration_ms
        if chapter.start_ms >= episode.duration_ms:
            raise invalid("chapter starts outside the episode")
        if any(block_index not in block_by_index for block_index in chapter.evidence_block_indexes):
            raise invalid("chapter cites an unknown transcript block")
        overlaps = any(
            block_by_index[block_index].end_ms > chapter.start_ms and block_by_index[block_index].start_ms < end_ms
            for block_index in chapter.evidence_block_indexes
        )
        if not overlaps and index > 0 and len(chapter.evidence_block_indexes) == 1:
            cited = block_by_index[chapter.evidence_block_indexes[0]]
            previous = candidate.chapters[index - 1]
            # Some responses use the cited block's END as the chapter start.
            # Use its actual start, never manufacture a one-millisecond overlap
            # or substitute an uncited block. Preserve the preceding chapter's
            # ordering and evidence before applying this narrow repair.
            if (
                cited.end_ms == chapter.start_ms
                and previous.start_ms < cited.start_ms < chapter.start_ms
                and any(
                    block_by_index[block_index].end_ms > previous.start_ms
                    and block_by_index[block_index].start_ms < cited.start_ms
                    for block_index in previous.evidence_block_indexes
                )
            ):
                candidate.chapters[index] = chapter.model_copy(update={"start_ms": cited.start_ms})
                chapter_boundaries_realigned += 1
                overlaps = True
        if not overlaps:
            evidence_overlap_violations += 1

    return OpenRouterEpisodeResult(
        video_id=episode.video_id,
        model=model,
        provider=provider,
        prompt_version=PROMPT_VERSION,
        candidate=candidate,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        elapsed_seconds=elapsed,
        first_boundary_normalized=first_boundary_normalized,
        summaries_truncated=summaries_truncated,
        label_values_trimmed=label_values_trimmed,
        evidence_citations_trimmed=evidence_citations_trimmed,
        chapter_boundaries_reordered=chapter_boundaries_reordered,
        chapter_boundaries_deduplicated=chapter_boundaries_deduplicated,
        categories_dropped=categories_dropped,
        category_rejections=category_rejections,
        evidence_overlap_violations=evidence_overlap_violations,
        chapter_boundaries_realigned=chapter_boundaries_realigned,
    )


def generate_openrouter_episode_enrichment(
    episode: EpisodeInput,
    *,
    api_key: str,
    model: str,
    timeout_seconds: float = 300.0,
    allow_provider_fallbacks: bool = False,
    provider_only: list[str] | None = None,
    max_retries: int = 2,
    app_url: str = "http://localhost:5173",
    defer_category_sustained_validation: bool = False,
) -> OpenRouterEpisodeResult:
    if not api_key.strip():
        raise ValueError("OpenRouter API key is required")
    body = build_openrouter_episode_request(
        episode,
        model=model,
        allow_provider_fallbacks=allow_provider_fallbacks,
        provider_only=provider_only,
    )
    req = request.Request(
        OPENROUTER_CHAT_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": app_url,
            "X-Title": "Transcript Archive enrichment",
        },
        method="POST",
    )
    started = time.monotonic()
    for attempt in range(max_retries + 1):
        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                try:
                    payload = json.loads(response.read().decode("utf-8"))
                except (ValueError, UnicodeError) as exc:
                    raise RuntimeError("OpenRouter request failed: invalid response envelope") from exc
            if not isinstance(payload, dict):
                raise RuntimeError("OpenRouter request failed: response envelope was not an object")
            return _parse_response(
                payload,
                episode,
                model=model,
                elapsed=time.monotonic() - started,
                defer_category_sustained_validation=defer_category_sustained_validation,
            )
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1_000]
            if exc.code in (502, 503):
                failure = RuntimeError(f"OpenRouter request failed: HTTP {exc.code}")
                transient = True
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if retry_after:
                    try:
                        try:
                            requested_delay = float(retry_after)
                        except ValueError:
                            requested_delay = (
                                parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)
                            ).total_seconds()
                        transient = math.isfinite(requested_delay) and requested_delay <= 900
                    except (ValueError, TypeError, OverflowError):
                        transient = False
                failure.__dict__["failure_details"] = {
                    "error_code": str(exc.code),
                    "http_status": exc.code,
                    "usage_reported": False,
                    "transient": transient,
                }
                failure.__dict__["elapsed_seconds"] = time.monotonic() - started
                raise failure from exc
            retryable = exc.code == 429 or (exc.code == 413 and "rate limit" in detail.casefold())
            if not retryable or attempt >= max_retries:
                raise RuntimeError(f"OpenRouter request failed: HTTP {exc.code}: {detail}") from exc
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            delay = 15.0 * 2**attempt
            if retry_after:
                try:
                    requested_delay = float(retry_after)
                except ValueError:
                    try:
                        requested_delay = (
                            parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)
                        ).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        requested_delay = delay
                if not math.isfinite(requested_delay) or requested_delay > 60:
                    raise RuntimeError(
                        "OpenRouter rate limit requires a longer cooldown; stop before another request"
                    ) from exc
                delay = max(delay, requested_delay)
            time.sleep(min(60.0, delay))
        except (error.URLError, TimeoutError) as exc:
            # A lost response may already have incurred provider usage. Never
            # automatically replay an uncertain paid request.
            failure = RuntimeError("OpenRouter request outcome uncertain: transport response unavailable")
            failure.__dict__["failure_details"] = {
                "error_code": "transport_uncertain",
                "usage_reported": False,
                "transient": False,
            }
            failure.__dict__["elapsed_seconds"] = time.monotonic() - started
            raise failure from exc
    raise RuntimeError("OpenRouter request failed after retries")


def _rank_window_labels(values: list[list[str]], limit: int) -> list[str]:
    counts: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    display: dict[str, str] = {}
    position = 0
    for group in values:
        for value in dict.fromkeys(group):
            normalized = " ".join(value.casefold().split())
            if not normalized:
                continue
            counts[normalized] += 1
            first_seen.setdefault(normalized, position)
            display.setdefault(normalized, value)
            position += 1
    ranked = sorted(counts, key=lambda value: (-counts[value], first_seen[value], value))
    return [display[value] for value in ranked[:limit]]


def _spread_category_evidence(indexes: list[int], episode: EpisodeInput, limit: int = 3) -> list[int]:
    """Retain citations spread across the full episode instead of the first window."""
    block_by_index = {block.block_index: block for block in episode.blocks}
    unique = list(dict.fromkeys(indexes))
    if any(index not in block_by_index for index in unique):
        return unique[:limit]
    ordered = sorted(unique, key=lambda index: (block_by_index[index].start_ms, index))
    if len(ordered) <= limit:
        return ordered
    selected = [ordered[0], ordered[-1]]
    if limit > 2:
        midpoint_ms = episode.duration_ms / 2
        middle = min(
            ordered[1:-1],
            key=lambda index: (abs(block_by_index[index].start_ms - midpoint_ms), block_by_index[index].start_ms),
        )
        selected.append(middle)
    return sorted(selected[:limit], key=lambda index: (block_by_index[index].start_ms, index))


def _balanced_episode_windows(episode: EpisodeInput, max_window_ms: int) -> list[tuple[int, EpisodeInput]]:
    if max_window_ms <= 0:
        raise ValueError("max enrichment window must be positive")
    window_count = max(1, math.ceil(episode.duration_ms / max_window_ms))
    windows: list[tuple[int, EpisodeInput]] = []
    for index in range(window_count):
        start_ms = round(index * episode.duration_ms / window_count)
        end_ms = round((index + 1) * episode.duration_ms / window_count)
        blocks: list[TranscriptBlockInput] = []
        for block in episode.blocks:
            if block.end_ms <= start_ms or block.start_ms >= end_ms:
                continue
            relative_start = max(0, block.start_ms - start_ms)
            relative_end = min(end_ms - start_ms, block.end_ms - start_ms)
            if relative_end <= relative_start:
                continue
            blocks.append(
                TranscriptBlockInput(
                    block_index=block.block_index,
                    start_ms=relative_start,
                    end_ms=relative_end,
                    text=block.text,
                )
            )
        if not blocks:
            raise ValueError("enrichment window contains no transcript blocks")
        windows.append(
            (
                start_ms,
                EpisodeInput(
                    video_id=episode.video_id,
                    title=episode.title,
                    duration_ms=end_ms - start_ms,
                    transcript_source=episode.transcript_source,
                    transcript_coverage=episode.transcript_coverage,
                    transcript_selection_reason=episode.transcript_selection_reason,
                    blocks=blocks,
                ),
            )
        )
    return windows


def generate_hierarchical_openrouter_enrichment(
    episode: EpisodeInput,
    *,
    generate_window: Callable[[EpisodeInput], OpenRouterEpisodeResult],
    max_window_ms: int = 90 * 60 * 1000,
    max_cost_usd: float | None = None,
) -> OpenRouterEpisodeResult:
    """Generate bounded window outlines and merge them into one complete candidate."""
    if max_cost_usd is not None and max_cost_usd <= 0:
        raise ValueError("max enrichment cost must be positive")
    windows = _balanced_episode_windows(episode, max_window_ms)
    window_results: list[tuple[int, OpenRouterEpisodeResult]] = []
    for index, (offset_ms, window) in enumerate(windows):
        try:
            window_result = generate_window(window)
        except Exception as exc:
            providers = [result.provider for _offset, result in window_results]
            failed_provider = getattr(exc, "provider", None)
            if failed_provider:
                providers.append(str(failed_provider))
            failure = OpenRouterHierarchicalGenerationError(
                str(exc),
                provider=", ".join(dict.fromkeys(providers)),
                prompt_tokens=sum(result.prompt_tokens for _offset, result in window_results)
                + int(getattr(exc, "prompt_tokens", 0) or 0),
                completion_tokens=sum(result.completion_tokens for _offset, result in window_results)
                + int(getattr(exc, "completion_tokens", 0) or 0),
                cost_usd=sum(result.cost_usd for _offset, result in window_results)
                + float(getattr(exc, "cost_usd", 0.0) or 0.0),
                elapsed_seconds=sum(result.elapsed_seconds for _offset, result in window_results)
                + float(getattr(exc, "elapsed_seconds", 0.0) or 0.0),
                window_count=len(window_results),
                attempted_window_count=index + 1,
            )
            failure.failure_details = getattr(exc, "failure_details", {})
            raise failure from exc
        window_results.append((offset_ms, window_result))
        cumulative_cost = sum(result.cost_usd for _offset, result in window_results)
        if max_cost_usd is not None and (
            cumulative_cost > max_cost_usd or (cumulative_cost >= max_cost_usd and index + 1 < len(windows))
        ):
            providers = list(dict.fromkeys(result.provider for _offset, result in window_results))
            raise OpenRouterBudgetExceededError(
                provider=", ".join(providers),
                prompt_tokens=sum(result.prompt_tokens for _offset, result in window_results),
                completion_tokens=sum(result.completion_tokens for _offset, result in window_results),
                cost_usd=cumulative_cost,
                elapsed_seconds=sum(result.elapsed_seconds for _offset, result in window_results),
                max_cost_usd=max_cost_usd,
                window_count=len(window_results),
                attempted_window_count=index + 1,
            )

    models = {result.model for _offset, result in window_results}
    prompt_versions = {result.prompt_version for _offset, result in window_results}
    if len(models) != 1 or len(prompt_versions) != 1:
        raise ValueError("hierarchical enrichment windows must use one model and prompt version")

    chapters: list[EpisodeChapterCandidate] = []
    for offset_ms, result in window_results:
        chapters.extend(
            chapter.model_copy(update={"start_ms": offset_ms + chapter.start_ms})
            for chapter in result.candidate.chapters
        )
    category_counts: Counter[str] = Counter()
    category_evidence: dict[str, list[int]] = {}
    for _offset_ms, result in window_results:
        for category in result.candidate.categories:
            category_counts[category.slug] += 1
            evidence = category_evidence.setdefault(category.slug, [])
            evidence.extend(index for index in category.evidence_block_indexes if index not in evidence)
    ranked_categories = category_counts.most_common()
    category_rejections = [rejection for _offset, result in window_results for rejection in result.category_rejections]
    window_rejection_count = len(category_rejections)
    categories: list[EpisodeCategoryCandidate] = []
    for slug, _count in ranked_categories[:3]:
        raw_category = {
            "slug": slug,
            "evidence_block_indexes": _spread_category_evidence(category_evidence[slug], episode),
        }
        reason = _category_rejection_reason(raw_category, episode)
        if reason is None:
            categories.append(EpisodeCategoryCandidate.model_validate(raw_category))
        else:
            category_rejections.append(_category_rejection(raw_category, reason))
    category_rejections.extend(
        {"slug": slug, "reason": "hierarchical_rank_limit"} for slug, _count in ranked_categories[3:]
    )
    candidate = EpisodeEnrichmentCandidate(
        subjects=_rank_window_labels([result.candidate.subjects for _offset, result in window_results], 12),
        keywords=_rank_window_labels([result.candidate.keywords for _offset, result in window_results], 24),
        categories=categories,
        chapters=chapters,
    )
    providers = list(dict.fromkeys(result.provider for _offset, result in window_results))
    first_result = window_results[0][1]
    return OpenRouterEpisodeResult(
        video_id=episode.video_id,
        model=first_result.model,
        provider=", ".join(providers),
        prompt_version=first_result.prompt_version,
        candidate=candidate,
        prompt_tokens=sum(result.prompt_tokens for _offset, result in window_results),
        completion_tokens=sum(result.completion_tokens for _offset, result in window_results),
        cost_usd=sum(result.cost_usd for _offset, result in window_results),
        elapsed_seconds=sum(result.elapsed_seconds for _offset, result in window_results),
        first_boundary_normalized=any(result.first_boundary_normalized for _offset, result in window_results),
        summaries_truncated=sum(result.summaries_truncated for _offset, result in window_results),
        label_values_trimmed=sum(result.label_values_trimmed for _offset, result in window_results),
        evidence_citations_trimmed=sum(result.evidence_citations_trimmed for _offset, result in window_results),
        chapter_boundaries_reordered=any(result.chapter_boundaries_reordered for _offset, result in window_results),
        chapter_boundaries_deduplicated=sum(
            result.chapter_boundaries_deduplicated for _offset, result in window_results
        ),
        categories_dropped=sum(result.categories_dropped for _offset, result in window_results)
        + len(category_rejections)
        - window_rejection_count,
        category_rejections=category_rejections,
        evidence_overlap_violations=sum(result.evidence_overlap_violations for _offset, result in window_results),
        chapter_boundaries_realigned=sum(result.chapter_boundaries_realigned for _offset, result in window_results),
        window_count=len(window_results),
    )


__all__ = [
    "EPISODE_ENRICHMENT_SCHEMA",
    "CATEGORY_LABELS",
    "CATEGORY_GUIDANCE",
    "OPENROUTER_CHAT_URL",
    "PROMPT_VERSION",
    "EpisodeChapterCandidate",
    "EpisodeCategoryCandidate",
    "EpisodeEnrichmentCandidate",
    "OpenRouterBudgetExceededError",
    "OpenRouterHierarchicalGenerationError",
    "OpenRouterEpisodeResult",
    "OpenRouterResponseValidationError",
    "build_openrouter_episode_request",
    "generate_hierarchical_openrouter_enrichment",
    "generate_openrouter_episode_enrichment",
]
