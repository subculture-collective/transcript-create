import json

import pytest
from sqlalchemy.sql.elements import TextClause

from app.archive.labeling.windows import _hash_window, build_windows_from_segments, load_source_segments, persist_windows


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class FakeDB:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((statement, params))
        if self.results:
            return FakeResult(self.results.pop(0))
        return FakeResult([])


def test_build_windows_merges_segments_into_stable_windows():
    segments = [
        {"id": 10, "start_ms": 0, "end_ms": 1000, "text": "Hello"},
        {"id": 11, "start_ms": 60_000, "end_ms": 61_000, "text": "world"},
        {"id": 12, "start_ms": 120_000, "end_ms": 121_000, "text": "   "},
        {"id": 13, "start_ms": 135_000, "end_ms": 136_500, "text": "next window"},
        {"start_ms": 136_000, "end_ms": 137_000, "text": "missing id"},
    ]

    windows = build_windows_from_segments(segments, source="whisper", window_ms=120_000)

    assert len(windows) == 2
    assert windows[0].source == "whisper"
    assert windows[0].start_ms == 0
    assert windows[0].end_ms == 61_000
    assert windows[0].segment_ids == [10, 11]
    assert windows[0].text == "Hello world"
    assert windows[0].token_count == 2
    assert len(windows[0].text_hash) == 64

    assert windows[1].start_ms == 135_000
    assert windows[1].end_ms == 137_000
    assert windows[1].segment_ids == [13]
    assert windows[1].text == "next window missing id"
    assert windows[1].token_count == 4


def test_window_hash_is_stable_for_same_text_and_bounds():
    first = _hash_window("whisper", 0, 10_000, " Hello   world ")
    second = _hash_window("whisper", 0, 10_000, "Hello world")

    assert first == second
    assert first == _hash_window("whisper", 0, 10_000, "Hello world")


def test_builder_and_loader_reject_unsupported_source():
    with pytest.raises(ValueError, match="unsupported transcript source"):
        build_windows_from_segments([], source="bad-source")

    with pytest.raises(ValueError, match="unsupported transcript source"):
        load_source_segments(FakeDB(), video_id="video-1", source="bad-source")


def test_build_windows_clamps_overlong_segments_to_non_overlapping_bounds():
    segments = [
        {"id": 1, "start_ms": 0, "end_ms": 200_000, "text": "very long segment"},
        {"id": 2, "start_ms": 130_000, "end_ms": 131_000, "text": "next bucket"},
    ]

    windows = build_windows_from_segments(segments, source="whisper", window_ms=120_000)

    assert len(windows) == 2
    assert windows[0].start_ms == 0
    assert windows[0].end_ms == 120_000
    assert windows[1].start_ms == 130_000
    assert windows[1].end_ms == 131_000
    assert windows[0].end_ms <= windows[1].start_ms


def test_load_source_segments_handles_whisper_and_youtube_paths():
    whisper_db = FakeDB(results=[[{"id": 1, "start_ms": 0, "end_ms": 1000, "text": "hello"}]])
    whisper_rows = load_source_segments(whisper_db, video_id="video-1", source="whisper")

    assert isinstance(whisper_db.calls[0][0], TextClause)
    assert "FROM segments" in str(whisper_db.calls[0][0])
    assert whisper_db.calls[0][1] == {"video_id": "video-1"}
    assert isinstance(whisper_rows[0], dict)
    whisper_rows[0]["text"] = "changed"
    assert whisper_rows[0]["text"] == "changed"

    youtube_db = FakeDB(results=[[{"id": 9, "start_ms": 2000, "end_ms": 3000, "text": "hola"}]])
    youtube_rows = load_source_segments(youtube_db, video_id="video-2", source="youtube")

    assert isinstance(youtube_db.calls[0][0], TextClause)
    assert "youtube_segments" in str(youtube_db.calls[0][0])
    assert "youtube_transcripts" in str(youtube_db.calls[0][0])
    assert youtube_db.calls[0][1] == {"video_id": "video-2"}
    assert isinstance(youtube_rows[0], dict)
    youtube_rows[0]["text"] = "changed"
    assert youtube_rows[0]["text"] == "changed"


def test_persist_windows_serializes_segment_ids_and_skips_empty_input():
    db = FakeDB()
    window = build_windows_from_segments(
        [{"id": 7, "start_ms": 0, "end_ms": 1000, "text": "hello there"}],
        source="whisper",
    )[0]

    count = persist_windows(db, video_id="video-3", windows=[window])

    assert count == 1
    assert len(db.calls) == 1
    statement, params = db.calls[0]
    assert isinstance(statement, TextClause)
    assert "archive_transcript_windows" in str(statement)
    assert "CAST(:segment_ids AS jsonb)" in str(statement)
    assert "ON CONFLICT (video_id, source, start_ms, end_ms, text_hash)" in str(statement)
    assert params["video_id"] == "video-3"
    assert params["segment_ids"] == json.dumps([7])
    assert params["text"] == "hello there"
    assert params["token_count"] == 2

    empty_db = FakeDB()
    assert persist_windows(empty_db, video_id="video-4", windows=[]) == 0
    assert empty_db.calls == []
