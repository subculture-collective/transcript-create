from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Literal

from app.archive.labeling.normalization import is_junk_phrase, normalized_alias


QualityAction = Literal["keep", "review", "mark_noise"]

_WEAK_OPENERS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "because",
    "but",
    "for",
    "from",
    "if",
    "in",
    "into",
    "like",
    "of",
    "on",
    "or",
    "so",
    "that",
    "the",
    "then",
    "to",
    "with",
}
_CONTEXT_OPENERS = {"about"}
_WEAK_CLOSERS = {
    "a",
    "am",
    "and",
    "an",
    "are",
    "as",
    "be",
    "been",
    "but",
    "can",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "in",
    "is",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
    "would",
}
_HELPER_VERBS = {
    "am",
    "are",
    "be",
    "been",
    "being",
    "can",
    "could",
    "did",
    "do",
    "does",
    "going",
    "got",
    "had",
    "has",
    "have",
    "is",
    "may",
    "might",
    "must",
    "should",
    "was",
    "were",
    "will",
    "would",
}
_GENERIC_SINGLETONS = {
    "absolute",
    "absolutely",
    "actual",
    "actually",
    "bad",
    "basically",
    "better",
    "brief",
    "caused",
    "considering",
    "existing",
    "figured",
    "good",
    "happening",
    "insanely",
    "necessary",
    "obviously",
    "officially",
    "option",
    "overwhelming",
    "really",
    "regularly",
    "staying",
    "terrifying",
    "uses",
    "very",
    "whereas",
}
_DOMAIN_KEEP_SINGLETONS = {
    "abortion",
    "abortions",
    "autism",
    "biden",
    "ceasefire",
    "covid",
    "destiny",
    "fauci",
    "gaza",
    "iran",
    "iraq",
    "israel",
    "netanyahu",
    "palestine",
    "trump",
    "ukraine",
    "vaccination",
    "vaccine",
    "vaccines",
}
_ENTITY_HINTS = {
    "biden",
    "china",
    "covid",
    "fauci",
    "gaza",
    "iran",
    "iraq",
    "israel",
    "netanyahu",
    "palestine",
    "russia",
    "trump",
    "ukraine",
}
_VACCINE_TERMS = {"vaccinated", "vaccination", "vaccine", "vaccines"}


@dataclass(frozen=True)
class LabelQualityAssessment:
    label: str
    action: QualityAction
    score: float
    reasons: tuple[str, ...]
    canonical_hint: str | None = None
    needs_llm_review: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _terms(label: str) -> list[str]:
    normalized = normalized_alias(label)
    return normalized.split() if normalized else []


def _title_terms(label: str) -> list[str]:
    return [term for term in re.split(r"\s+", str(label or "").strip()) if term]


def _looks_like_acronym(label: str) -> bool:
    compact = re.sub(r"[^A-Za-z0-9]", "", label)
    return 2 <= len(compact) <= 8 and compact.upper() == compact and any(char.isalpha() for char in compact)


def canonical_hint_for_label(label: str) -> str | None:
    terms = _terms(label)
    if not terms:
        return None

    def safe_remainder(start: int) -> str | None:
        remainder_terms = terms[start:]
        if not remainder_terms or remainder_terms[-1] in _WEAK_CLOSERS:
            return None
        title_terms = _title_terms(label)[start:]
        return " ".join(title_terms) or None

    if terms[0] in _CONTEXT_OPENERS and len(terms) > 1:
        return safe_remainder(1)
    if terms[0] in {"the", "a", "an"} and len(terms) > 1:
        return safe_remainder(1)
    if any(term in _VACCINE_TERMS for term in terms):
        return "Vaccination"
    for hint in _ENTITY_HINTS:
        if hint in terms:
            return " ".join(part.capitalize() for part in hint.split())
    return None


def assess_label_quality(
    label: str,
    *,
    source: str | None = None,
    assignment_count: int = 0,
    distinct_videos: int = 0,
    existing_canonical: bool = False,
) -> LabelQualityAssessment:
    terms = _terms(label)
    reasons: list[str] = []
    score = 0.55

    if not terms:
        return LabelQualityAssessment(label=label, action="mark_noise", score=0.0, reasons=("empty_label",))

    if is_junk_phrase(label):
        reasons.append("existing_junk_phrase")
        score -= 0.55

    if terms[0] in _WEAK_OPENERS:
        reasons.append("weak_opener")
        score -= 0.22
    elif terms[0] in _CONTEXT_OPENERS:
        reasons.append("context_opener")
        score -= 0.12

    if terms[-1] in _WEAK_CLOSERS:
        reasons.append("weak_closer")
        score -= 0.25

    if len(terms) <= 4 and all(term in _WEAK_OPENERS | _CONTEXT_OPENERS | _WEAK_CLOSERS | _HELPER_VERBS for term in terms):
        reasons.append("mostly_function_words")
        score -= 0.40

    if len(terms) >= 2 and terms[0] in _HELPER_VERBS and terms[1] in _WEAK_CLOSERS | _HELPER_VERBS:
        reasons.append("helper_verb_fragment")
        score -= 0.25

    if len(terms) == 1 and terms[0] in _GENERIC_SINGLETONS and terms[0] not in _DOMAIN_KEEP_SINGLETONS:
        reasons.append("generic_singleton")
        score -= 0.35

    if len(terms) <= 3 and any(term.isdigit() for term in terms) and not any(term in _ENTITY_HINTS for term in terms):
        reasons.append("numeric_fragment")
        score -= 0.25

    if source == "keyphrase":
        reasons.append("keyphrase_source")
        score -= 0.10
    elif source in {"alias", "title", "llm", "metadata"}:
        score += 0.10

    if existing_canonical:
        score += 0.20
    if distinct_videos >= 3:
        score += 0.08
    if assignment_count >= 10:
        score += 0.04

    title_terms = _title_terms(label)
    if len(title_terms) >= 2 and any(term[:1].isupper() for term in title_terms[1:]):
        score += 0.08
    if len(terms) == 1 and (terms[0] in _DOMAIN_KEEP_SINGLETONS or _looks_like_acronym(label)):
        score += 0.30

    hint = canonical_hint_for_label(label)
    if hint and normalized_alias(hint) != normalized_alias(label):
        reasons.append("canonical_hint_available")

    score = max(0.0, min(1.0, round(score, 4)))
    if score < 0.35:
        action: QualityAction = "mark_noise"
    elif score < 0.68 or "canonical_hint_available" in reasons:
        action = "review"
    else:
        action = "keep"

    needs_llm = action == "review" or (0.35 <= score <= 0.78 and bool(hint))
    return LabelQualityAssessment(
        label=label,
        action=action,
        score=score,
        reasons=tuple(reasons),
        canonical_hint=hint,
        needs_llm_review=needs_llm,
    )


def apply_quality_gate(
    label: str,
    publish_tier: str,
    assignment_status: str,
    *,
    source: str | None = None,
    assignment_count: int = 0,
    distinct_videos: int = 0,
    existing_canonical: bool = False,
) -> tuple[str, str, LabelQualityAssessment]:
    assessment = assess_label_quality(
        label,
        source=source,
        assignment_count=assignment_count,
        distinct_videos=distinct_videos,
        existing_canonical=existing_canonical,
    )
    if assessment.action == "mark_noise":
        return "shadow", "shadow", assessment
    if assignment_status == "auto_published" and assessment.action == "review":
        return "bronze", "candidate", assessment
    return publish_tier, assignment_status, assessment


__all__ = [
    "LabelQualityAssessment",
    "apply_quality_gate",
    "assess_label_quality",
    "canonical_hint_for_label",
]
