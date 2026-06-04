from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text


@dataclass(frozen=True)
class TranscriptWindow:
    source: str
    start_ms: int
    end_ms: int
    segment_ids: list[int]
    text: str
    token_count: int
    text_hash: str


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _hash_window(source: str, start_ms: int, end_ms: int, text: str) -> str:
    normalized_text = _normalize_text(text)
    payload = f"{source}|{start_ms}|{end_ms}|{normalized_text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_windows_from_segments(segments: list[dict], source: str, window_ms: int = 120_000) -> list[TranscriptWindow]:
    if source not in {"whisper", "youtube"}:
        raise ValueError(f"unsupported transcript source: {source}")
    if window_ms <= 0:
        raise ValueError("window_ms must be positive")

    ordered_segments = sorted(
        (segment for segment in segments if str(segment.get("text", "")).strip()),
        key=lambda segment: int(segment.get("start_ms") or 0),
    )

    windows: list[TranscriptWindow] = []
    current_segments: list[dict[str, Any]] = []
    current_start: int | None = None

    def flush_window() -> None:
        nonlocal current_segments, current_start
        if not current_segments or current_start is None:
            return
        text_parts = [str(segment["text"]).strip() for segment in current_segments if str(segment.get("text", "")).strip()]
        text = _normalize_text(" ".join(text_parts))
        start_ms = current_start
        natural_end_ms = max(int(segment.get("end_ms") or segment.get("start_ms") or start_ms) for segment in current_segments)
        end_ms = min(natural_end_ms, start_ms + window_ms)
        segment_ids = [int(segment["id"]) for segment in current_segments if segment.get("id") is not None]
        windows.append(
            TranscriptWindow(
                source=source,
                start_ms=start_ms,
                end_ms=end_ms,
                segment_ids=segment_ids,
                text=text,
                token_count=len(text.split()),
                text_hash=_hash_window(source, start_ms, end_ms, text),
            )
        )
        current_segments = []
        current_start = None

    for segment in ordered_segments:
        segment_start = int(segment["start_ms"])
        if current_start is None:
            current_start = segment_start
        elif segment_start - current_start >= window_ms:
            flush_window()
            current_start = segment_start
        current_segments.append(segment)

    flush_window()
    return windows


def load_source_segments(db: Any, video_id: str, source: str) -> list[dict]:
    if source == "whisper":
        statement = text("SELECT id, start_ms, end_ms, text FROM segments WHERE video_id = :video_id ORDER BY start_ms")
    elif source == "youtube":
        statement = text(
            """
            SELECT ys.id, ys.start_ms, ys.end_ms, ys.text
            FROM youtube_segments AS ys
            JOIN youtube_transcripts AS yt ON ys.youtube_transcript_id = yt.id
            WHERE yt.video_id = :video_id
            ORDER BY ys.start_ms
            """
        )
    else:
        raise ValueError(f"unsupported transcript source: {source}")

    result = db.execute(statement, {"video_id": video_id})
    if hasattr(result, "mappings"):
        rows = result.mappings().all()
    else:
        rows = result.all()
    return [dict(row) for row in rows]


def persist_windows(db: Any, video_id: str, windows: list[TranscriptWindow]) -> int:
    if not windows:
        return 0

    statement = text(
        """
        INSERT INTO archive_transcript_windows (
            video_id, source, start_ms, end_ms, segment_ids, text_hash, text, token_count, transcript_quality, created_at
        ) VALUES (
            :video_id, :source, :start_ms, :end_ms, CAST(:segment_ids AS jsonb), :text_hash, :text, :token_count, 1, now()
        ) ON CONFLICT (video_id, source, start_ms, end_ms, text_hash) DO UPDATE SET
            text = EXCLUDED.text,
            token_count = EXCLUDED.token_count,
            segment_ids = EXCLUDED.segment_ids
        """
    )

    for window in windows:
        db.execute(
            statement,
            {
                "video_id": video_id,
                "source": window.source,
                "start_ms": window.start_ms,
                "end_ms": window.end_ms,
                "segment_ids": json.dumps(window.segment_ids),
                "text_hash": window.text_hash,
                "text": window.text,
                "token_count": window.token_count,
            },
        )
    return len(windows)
