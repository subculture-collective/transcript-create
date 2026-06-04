"""Label extraction schema foundation."""

from .types import (
    AssignmentSource,
    AssignmentStatus,
    CandidateSignal,
    ChapterSource,
    ChapterStatus,
    ExtractionTier,
    LabelCandidate,
    LabelKind,
    LabelSource,
    LabelStatus,
    PublishTier,
    RunScope,
    TranscriptSource,
    UnitType,
)
from .windows import (
    TranscriptWindow,
    build_windows_from_segments,
    load_source_segments,
    persist_windows,
)
from .extractors import extract_alias_candidates, extract_keyphrase_candidates
from .normalization import is_junk_phrase, normalize_label, normalized_alias, slugify_label

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
    "TranscriptWindow",
    "build_windows_from_segments",
    "extract_alias_candidates",
    "extract_keyphrase_candidates",
    "is_junk_phrase",
    "load_source_segments",
    "normalize_label",
    "normalized_alias",
    "persist_windows",
    "slugify_label",
]
