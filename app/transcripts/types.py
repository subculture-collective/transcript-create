from dataclasses import dataclass
from enum import Enum


class TranscriptViewMode(str, Enum):
    RAW = "raw"
    CLEANED = "cleaned"
    FORMATTED = "formatted"


@dataclass(frozen=True)
class TranscriptSegment:
    start_ms: int
    end_ms: int
    text: str
    speaker_label: str | None
