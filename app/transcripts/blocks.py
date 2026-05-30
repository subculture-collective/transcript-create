from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from worker.formatter import TranscriptFormatter

from .types import TranscriptSegment


FORMATTER_VERSION = "rule-v3"


@dataclass(frozen=True)
class TranscriptBlock:
    block_index: int
    start_ms: int
    end_ms: int
    speaker_label: str | None
    text: str
    segment_ids: list[int]
    kind: Literal["paragraph", "speaker_turn"]
    formatter_version: str = FORMATTER_VERSION


def _formatter() -> TranscriptFormatter:
    return TranscriptFormatter(
        config={
            "enabled": True,
            "normalize_unicode": True,
            "normalize_whitespace": True,
            "remove_special_tokens": True,
            "remove_fillers": True,
            "filler_level": 1,
            "add_sentence_punctuation": True,
            "punctuation_mode": "rule-based",
            "add_internal_punctuation": True,
            "capitalize_sentences": True,
            "fix_all_caps": True,
            "detect_hallucinations": True,
            "segment_by_sentences": False,
            "merge_short_segments": False,
            "speaker_format": "inline",
            "language_specific_rules": True,
        }
    )


def _clean_segments(segments: Sequence[TranscriptSegment]) -> list[dict]:
    formatted = _formatter().format_segments(
        [
            {
                "start": segment.start_ms,
                "end": segment.end_ms,
                "text": segment.text,
                "speaker": segment.speaker_label,
                "speaker_label": segment.speaker_label,
                "source_index": idx,
            }
            for idx, segment in enumerate(segments)
        ]
    )
    return [segment for segment in formatted if segment.get("text", "").strip()]


def _ends_sentence(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?"))


def _should_break_unlabeled(previous: dict | None, current: dict, current_text: str) -> bool:
    if previous is None:
        return True
    gap_ms = int(current["start"]) - int(previous["end"])
    previous_text = str(previous.get("text", ""))
    return gap_ms >= 1200 or (_ends_sentence(previous_text) and len(previous_text.split()) >= 14 and len(current_text.split()) >= 3)


def _join_text(parts: Sequence[str]) -> str:
    return " ".join(part.strip() for part in parts if part.strip()).strip()


def build_transcript_blocks(segments: Sequence[TranscriptSegment]) -> list[TranscriptBlock]:
    cleaned_segments = _clean_segments(segments)
    blocks: list[TranscriptBlock] = []
    current: list[dict] = []
    current_speaker: str | None = None

    def flush() -> None:
        nonlocal current
        if not current:
            return
        blocks.append(
            TranscriptBlock(
                block_index=len(blocks),
                start_ms=int(current[0]["start"]),
                end_ms=int(current[-1]["end"]),
                speaker_label=current_speaker,
                text=_join_text([str(segment["text"]) for segment in current]),
                segment_ids=[int(segment["source_index"]) for segment in current],
                kind="speaker_turn" if current_speaker else "paragraph",
            )
        )
        current = []

    for segment in cleaned_segments:
        speaker = segment.get("speaker_label") or segment.get("speaker") or None
        text = str(segment.get("text", "")).strip()

        if speaker:
            if current and current_speaker != speaker:
                flush()
            current_speaker = str(speaker)
            current.append(segment)
            continue

        if current_speaker is not None:
            flush()
            current_speaker = None

        previous = current[-1] if current else None
        if current and _should_break_unlabeled(previous, segment, text):
            flush()
        current_speaker = None
        current.append(segment)

    flush()
    return blocks
