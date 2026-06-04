from dataclasses import dataclass, field
from typing import Any, Literal

RunScope = Literal["video", "batch", "period", "backfill"]
ExtractionTier = Literal["cheap", "balanced", "premium"]
LabelKind = Literal["topic", "person", "series", "category", "event", "game", "org", "meme", "place", "issue"]
LabelStatus = Literal["candidate", "review", "published", "hidden", "rejected", "merged"]
LabelSource = Literal["admin", "automatic", "hybrid", "seed"]
PublishTier = Literal["gold", "silver", "bronze", "shadow"]
TranscriptSource = Literal["whisper", "youtube"]
ChapterStatus = Literal["candidate", "published", "rejected", "hidden"]
ChapterSource = Literal["automatic", "manual", "hybrid"]
UnitType = Literal["vod", "chapter", "window", "segment"]
AssignmentStatus = Literal["candidate", "auto_published", "admin_approved", "rejected", "shadow"]
AssignmentSource = Literal["alias", "keyphrase", "search", "title", "embedding_cluster", "llm", "metadata", "admin", "hybrid"]


@dataclass(frozen=True)
class CandidateSignal:
    source: str
    label: str
    alias: str
    score: float
    evidence: dict[str, Any]


@dataclass(frozen=True)
class LabelCandidate:
    label: str
    kind: str
    aliases: tuple[str, ...]
    confidence_score: float
    component_scores: dict[str, float] = field(default_factory=dict)
    evidence: tuple[dict[str, Any], ...] = ()


__all__ = [
    "AssignmentSource",
    "AssignmentStatus",
    "CandidateSignal",
    "ChapterSource",
    "ChapterStatus",
    "ExtractionTier",
    "LabelCandidate",
    "LabelKind",
    "LabelSource",
    "LabelStatus",
    "PublishTier",
    "RunScope",
    "TranscriptSource",
    "UnitType",
]
