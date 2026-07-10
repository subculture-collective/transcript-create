from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib import error, request

PROMPT_VERSION = "archive-evidence-summary-v1"
MAX_EVIDENCE_ITEMS = 12
MAX_SNIPPET_CHARS = 1_200
MIN_SNIPPET_WORDS = 12

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "minLength": 12, "maxLength": 220},
                    "evidence_ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 3,
                        "items": {"type": "string"},
                    },
                },
                "required": ["text", "evidence_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}


class SummaryValidationError(ValueError):
    """Raised when a generated summary lacks valid supporting evidence."""


_CAPITALIZED_GROUNDING_EXEMPTIONS = {
    "additionally",
    "archive",
    "during",
    "evidence",
    "finally",
    "however",
    "it",
    "period",
    "the",
    "this",
    "while",
}


@dataclass(frozen=True)
class SummaryClaim:
    text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class GeneratedSummary:
    summary: str
    claims: tuple[SummaryClaim, ...]
    evidence_ids: tuple[str, ...]
    model: str
    prompt_version: str = PROMPT_VERSION
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "claims": [{"text": claim.text, "evidence_ids": list(claim.evidence_ids)} for claim in self.claims],
            "evidence_ids": list(self.evidence_ids),
            "model": self.model,
            "prompt_version": self.prompt_version,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


def _stable_evidence_id(item: dict[str, Any], index: int) -> str:
    explicit = str(item.get("evidence_id") or "").strip()
    if explicit:
        return explicit
    # Short request-local IDs are easier for small local models to reproduce
    # exactly than UUIDs or hashes. They are never treated as durable database
    # identifiers; the validated result maps them back to the supplied moments.
    return f"e{index + 1}"


def normalize_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(evidence[:MAX_EVIDENCE_ITEMS]):
        snippet = " ".join(str(item.get("snippet") or "").split())[:MAX_SNIPPET_CHARS]
        if len(snippet.split()) < MIN_SNIPPET_WORDS:
            continue
        evidence_id = _stable_evidence_id(item, index)
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        normalized.append(
            {
                "evidence_id": evidence_id,
                "video_id": str(item.get("video_id") or ""),
                "title": str(item.get("title") or "")[:240],
                "topic": str(item.get("topic") or "")[:120],
                "start_ms": int(item.get("start_ms") or 0),
                "end_ms": int(item.get("end_ms") or 0),
                "snippet": snippet,
            }
        )
    return normalized


def build_summary_request(label: str, evidence: list[dict[str, Any]], *, model: str) -> dict[str, Any]:
    normalized = normalize_evidence(evidence)
    if not normalized:
        raise SummaryValidationError("summary requires at least one non-empty evidence snippet")
    system = f"""You write concise, neutral summaries for a HasanAbi stream archive.
Prompt version: {PROMPT_VERSION}
Use only the supplied evidence. Do not infer opinions, motives, outcomes, or facts absent from it.
Write one to three specific claims. Every claim must cite one or more supplied evidence_id values.
Synthesize subjects and events instead of saying that Hasan "mentioned", "referenced", or "discussed" them.
Prefer recurring or representative subjects over isolated fragments. Avoid mentioning evidence IDs in claim text.
Keep each claim under 35 words and the entire summary under 90 words. Omit phrases such as "the archive evidence shows."
Numeric dates in titles may use DD/MM/YY. Do not restate an exact date from a title; the period field is authoritative.
Summarize subject matter only. Do not infer or restate dates, chronology, locations,
or outcomes from a title or fragment.
Write each claim as a complete grammatical sentence with terminal punctuation.
Return only JSON matching the supplied schema."""
    user = {
        "period": label,
        "evidence": normalized,
        "instructions": "Summarize what the archive evidence shows was discussed during this period.",
    }
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        "stream": False,
        "think": False,
        "format": SUMMARY_SCHEMA,
        "options": {"temperature": 0, "num_predict": 320},
        "keep_alive": "10m",
    }


def parse_summary_response(payload: dict[str, Any], evidence: list[dict[str, Any]], *, model: str) -> GeneratedSummary:
    normalized = normalize_evidence(evidence)
    valid_ids = {str(item["evidence_id"]) for item in normalized}
    evidence_by_id = {str(item["evidence_id"]): item for item in normalized}
    try:
        content = payload["message"]["content"]
        parsed = json.loads(str(content))
        raw_claims = parsed["claims"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SummaryValidationError("model response was not valid summary JSON") from exc
    if not isinstance(raw_claims, list) or not 1 <= len(raw_claims) <= 3:
        raise SummaryValidationError("model response must contain one to three claims")

    claims: list[SummaryClaim] = []
    cited_ids: list[str] = []
    for item in raw_claims:
        if not isinstance(item, dict):
            raise SummaryValidationError("summary claim must be an object")
        claim_text = " ".join(str(item.get("text") or "").split())
        evidence_ids = item.get("evidence_ids")
        if len(claim_text) < 12 or len(claim_text) > 220:
            raise SummaryValidationError("summary claim has an invalid length")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise SummaryValidationError("every summary claim requires evidence")
        claim_ids = tuple(dict.fromkeys(str(value) for value in evidence_ids))
        if any(evidence_id not in valid_ids for evidence_id in claim_ids):
            raise SummaryValidationError("summary claim cited unknown evidence")
        supporting_text = " ".join(
            f"{evidence_by_id[evidence_id].get('title', '')} "
            f"{evidence_by_id[evidence_id].get('topic', '')} "
            f"{evidence_by_id[evidence_id].get('snippet', '')}"
            for evidence_id in claim_ids
        ).casefold()
        unsupported_entities = {
            token
            for token in re.findall(r"\b[A-Z][A-Za-z'-]{2,}\b", claim_text)
            if token.casefold() not in _CAPITALIZED_GROUNDING_EXEMPTIONS and token.casefold() not in supporting_text
        }
        if unsupported_entities:
            raise SummaryValidationError(
                "summary claim introduced unsupported named terms: " + ", ".join(sorted(unsupported_entities))
            )
        unsupported_numbers = {
            token for token in re.findall(r"\b\d+(?:\.\d+)?%?\b", claim_text) if token.casefold() not in supporting_text
        }
        if unsupported_numbers:
            raise SummaryValidationError(
                "summary claim introduced unsupported numbers: " + ", ".join(sorted(unsupported_numbers))
            )
        if claim_text[-1] not in ".!?":
            claim_text += "."
        claims.append(SummaryClaim(text=claim_text, evidence_ids=claim_ids))
        cited_ids.extend(claim_ids)

    summary = " ".join(claim.text for claim in claims)
    if len(summary.split()) > 120:
        raise SummaryValidationError("summary exceeded the maximum word count")

    return GeneratedSummary(
        summary=summary,
        claims=tuple(claims),
        evidence_ids=tuple(dict.fromkeys(cited_ids)),
        model=model,
        prompt_tokens=int(payload.get("prompt_eval_count") or 0),
        completion_tokens=int(payload.get("eval_count") or 0),
    )


def generate_summary(
    label: str,
    evidence: list[dict[str, Any]],
    *,
    base_url: str,
    model: str,
    timeout_seconds: float = 180.0,
) -> GeneratedSummary:
    url = f"{base_url.rstrip('/')}/api/chat"
    body = build_summary_request(label, evidence, model=model)
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
        raise RuntimeError(f"Ollama summary request failed: HTTP {exc.code}: {detail}") from exc
    except (error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Ollama summary request failed: {exc}") from exc
    return parse_summary_response(payload, evidence, model=model)


def generate_period_summary_proposals(
    db: Any,
    *,
    base_url: str,
    model: str,
    granularity: str = "month",
    period: str | None = None,
    limit: int = 3,
    apply: bool = False,
) -> list[dict[str, Any]]:
    from sqlalchemy import text

    rows = (
        db.execute(
            text(
                """
            SELECT period, granularity, summary, evidence
            FROM archive_period_summaries
            WHERE granularity = :granularity
              AND (CAST(:period AS text) IS NULL OR period = CAST(:period AS text))
              AND jsonb_array_length(evidence) > 0
            ORDER BY period DESC
            LIMIT :limit
            """
            ),
            {"granularity": granularity, "period": period, "limit": max(1, min(limit, 24))},
        )
        .mappings()
        .all()
    )

    proposals: list[dict[str, Any]] = []
    for row in rows:
        evidence = _enrich_evidence_context(
            db,
            [dict(item) for item in (row.get("evidence") or []) if isinstance(item, dict)],
        )
        try:
            result = generate_summary(
                str(row["period"]),
                evidence,
                base_url=base_url,
                model=model,
            )
        except (RuntimeError, SummaryValidationError) as exc:
            proposals.append(
                {
                    "period": str(row["period"]),
                    "granularity": str(row["granularity"]),
                    "old_summary": str(row.get("summary") or ""),
                    "model": model,
                    "prompt_version": PROMPT_VERSION,
                    "error": str(exc),
                    "applied": False,
                }
            )
            continue
        proposal = {
            "period": str(row["period"]),
            "granularity": str(row["granularity"]),
            "old_summary": str(row.get("summary") or ""),
            **result.as_dict(),
            "applied": apply,
        }
        proposals.append(proposal)
        if apply:
            db.execute(
                text(
                    """
                    UPDATE archive_period_summaries
                    SET summary = :summary,
                        calculated_at = now()
                    WHERE period = :period
                      AND granularity = :granularity
                    """
                ),
                {
                    "summary": result.summary,
                    "period": str(row["period"]),
                    "granularity": str(row["granularity"]),
                },
            )
    return proposals


def _enrich_evidence_context(
    db: Any, evidence: list[dict[str, Any]], *, context_ms: int = 45_000
) -> list[dict[str, Any]]:
    from sqlalchemy import text

    enriched: list[dict[str, Any]] = []
    statement = text(
        """
        SELECT COALESCE(
            (
                SELECT string_agg(s.text, ' ' ORDER BY s.start_ms)
                FROM segments AS s
                WHERE s.video_id = :video_id
                  AND s.end_ms >= :context_start_ms
                  AND s.start_ms <= :context_end_ms
            ),
            (
                SELECT string_agg(ys.text, ' ' ORDER BY ys.start_ms)
                FROM youtube_segments AS ys
                JOIN youtube_transcripts AS yt ON yt.id = ys.youtube_transcript_id
                WHERE yt.video_id = :video_id
                  AND ys.end_ms >= :context_start_ms
                  AND ys.start_ms <= :context_end_ms
            )
        ) AS context
        """
    )
    for item in evidence[:MAX_EVIDENCE_ITEMS]:
        video_id = str(item.get("video_id") or "")
        start_ms = int(item.get("start_ms") or 0)
        end_ms = int(item.get("end_ms") or start_ms)
        if not video_id:
            continue
        row = (
            db.execute(
                statement,
                {
                    "video_id": video_id,
                    "context_start_ms": max(0, start_ms - context_ms),
                    "context_end_ms": max(end_ms, start_ms) + context_ms,
                },
            )
            .mappings()
            .first()
        )
        context = " ".join(str((row or {}).get("context") or "").split())
        enriched.append({**item, "snippet": context or str(item.get("snippet") or "")})
    return enriched


__all__ = [
    "GeneratedSummary",
    "PROMPT_VERSION",
    "SummaryClaim",
    "SummaryValidationError",
    "build_summary_request",
    "generate_period_summary_proposals",
    "generate_summary",
    "normalize_evidence",
    "parse_summary_response",
]
