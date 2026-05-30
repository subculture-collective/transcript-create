from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.transcripts.blocks import TranscriptBlock, build_transcript_blocks
from app.transcripts.types import TranscriptSegment


YouTubeCaptionRow = tuple[int, int, str]


def youtube_rows_to_segments(rows: Iterable[YouTubeCaptionRow]) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            start_ms=int(start_ms),
            end_ms=int(end_ms),
            text=str(text or ""),
            speaker_label=None,
        )
        for start_ms, end_ms, text in rows
    ]


def build_youtube_caption_blocks(rows: Sequence[YouTubeCaptionRow]) -> list[TranscriptBlock]:
    return build_transcript_blocks(youtube_rows_to_segments(rows))


def format_youtube_caption_text(rows: Sequence[YouTubeCaptionRow]) -> str:
    blocks = build_youtube_caption_blocks(rows)
    return "\n\n".join(block.text for block in blocks if block.text.strip())
