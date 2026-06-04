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
from .policy import classify_candidate
from .repository import (
    ASSIGNMENT_SOURCES,
    assignment_key,
    create_extraction_run,
    finish_extraction_run,
    insert_assignment,
    upsert_label_candidate,
)

__all__ = [
    "AssignmentSource",
    "AssignmentStatus",
    "ASSIGNMENT_SOURCES",
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
    "assignment_key",
    "classify_candidate",
    "create_extraction_run",
    "finish_extraction_run",
    "TranscriptWindow",
    "build_windows_from_segments",
    "extract_alias_candidates",
    "extract_keyphrase_candidates",
    "is_junk_phrase",
    "load_source_segments",
    "normalize_label",
    "normalized_alias",
    "insert_assignment",
    "persist_windows",
    "upsert_label_candidate",
    "slugify_label",
]
