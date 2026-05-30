from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from worker.formatter import TranscriptFormatter

from app.schemas import (
    CleanedSegment,
    CleanedTranscriptResponse,
    CleanupConfig,
    CleanupStats,
    Segment,
    TranscriptResponse,
)

from .types import TranscriptSegment


def _cleaned_formatter_config() -> dict[str, object]:
    return {
        "enabled": True,
        "normalize_unicode": True,
        "normalize_whitespace": True,
        "remove_special_tokens": True,
        "remove_fillers": True,
        "filler_level": 1,
        "add_sentence_punctuation": True,
        "punctuation_mode": "rule-based",
        "capitalize_sentences": True,
        "fix_all_caps": True,
        "detect_hallucinations": True,
        "segment_by_sentences": False,
        "merge_short_segments": False,
        "speaker_format": "structured",
    }


def _cleanup_config_from_formatter(formatter: TranscriptFormatter) -> CleanupConfig:
    config = formatter.config
    return CleanupConfig(
        normalize_unicode=config.get("normalize_unicode", True),
        normalize_whitespace=config.get("normalize_whitespace", True),
        remove_special_tokens=config.get("remove_special_tokens", True),
        preserve_sound_events=config.get("preserve_sound_events", False),
        add_punctuation=config.get("add_sentence_punctuation", True),
        punctuation_mode=config.get("punctuation_mode", "rule-based"),
        add_internal_punctuation=config.get("add_internal_punctuation", False),
        capitalize=config.get("capitalize_sentences", True),
        fix_all_caps=config.get("fix_all_caps", True),
        remove_fillers=config.get("remove_fillers", True),
        filler_level=config.get("filler_level", 1),
        segment_sentences=config.get("segment_by_sentences", False),
        merge_short_segments=config.get("merge_short_segments", False),
        min_segment_length_ms=config.get("min_segment_length_ms", 1000),
        max_gap_for_merge_ms=config.get("max_gap_for_merge_ms", 500),
        speaker_format=config.get("speaker_format", "structured"),
        detect_hallucinations=config.get("detect_hallucinations", True),
        language_specific_rules=config.get("language_specific_rules", True),
    )


class TranscriptPresentationService:
    def __init__(self, formatter: TranscriptFormatter | None = None):
        self._cleaned_formatter = formatter or TranscriptFormatter(config=_cleaned_formatter_config())

    @staticmethod
    def from_db_row(row) -> TranscriptSegment:
        return TranscriptSegment(start_ms=row[0], end_ms=row[1], text=row[2], speaker_label=row[3])

    def present_raw(self, video_id, segments: Sequence[TranscriptSegment]) -> TranscriptResponse:
        return TranscriptResponse(
            video_id=video_id,
            segments=[
                Segment(
                    start_ms=s.start_ms,
                    end_ms=s.end_ms,
                    text=s.text,
                    speaker_label=s.speaker_label,
                )
                for s in segments
            ],
            source="whisper",
            source_label="Whisper transcript",
        )

    def present_cleaned(self, video_id, segments: Sequence[TranscriptSegment]) -> CleanedTranscriptResponse:
        formatter = self._cleaned_formatter
        formatter_input: list[dict[str, Any]] = [
            {
                "start": s.start_ms,
                "end": s.end_ms,
                "text": s.text,
                "speaker": s.speaker_label,
                "speaker_label": s.speaker_label,
            }
            for s in segments
        ]
        formatted_segments = formatter.format_segments(formatter_input)
        orig_segments_by_start = {s.start_ms: s for s in segments}
        cleaned_segments = []
        for seg in formatted_segments:
            orig_seg = orig_segments_by_start.get(seg["start"])
            cleaned_segments.append(
                CleanedSegment(
                    start_ms=seg["start"],
                    end_ms=seg["end"],
                    text_raw=orig_seg.text if orig_seg else seg["text"],
                    text_cleaned=seg["text"],
                    speaker_label=seg.get("speaker_label"),
                    sentence_boundary=seg["text"].rstrip().endswith((".", "!", "?")),
                    likely_hallucination=False,
                )
            )
        orig_filler_count = sum(1 for s in segments if any(f in s.text.lower() for f in ["um", "uh", "er"]))
        cleaned_filler_count = sum(
            1 for s in formatted_segments if any(f in s["text"].lower() for f in ["um", "uh", "er"])
        )
        orig_token_count = sum(1 for s in segments if any(t in s.text for t in ["[MUSIC]", "[APPLAUSE]", "[LAUGHTER]"]))
        cleaned_token_count = sum(
            1
            for s in formatted_segments
            if any(t in s["text"] for t in ["[MUSIC]", "[APPLAUSE]", "[LAUGHTER]"])
        )
        stats = CleanupStats(
            fillers_removed=max(0, orig_filler_count - cleaned_filler_count),
            special_tokens_removed=max(0, orig_token_count - cleaned_token_count),
            segments_merged=0,
            segments_split=max(0, len(formatted_segments) - len(segments)),
            hallucinations_detected=0,
            punctuation_added=sum(1 for s in formatted_segments if s["text"].endswith(".")),
        )
        return CleanedTranscriptResponse(
            video_id=video_id,
            segments=cleaned_segments,
            cleanup_config=_cleanup_config_from_formatter(formatter),
            stats=stats,
        )
