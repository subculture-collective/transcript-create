"""Tests for archive summary repository behavior."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import ProgrammingError

from app import crud
from app.archive.repository import ArchiveRepository, archive_repository
from app.archive.intelligence_repository import SEED_TOPICS, alias_matches_text, autopublish_search_topics, seed_archive_topics, slugify_topic


class _FakeResult:
    def __init__(self, *, first=None, rows=None, scalar=None):
        self._first = first
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._rows

    def one(self):
        return self._first

    def scalar_one(self):
        return self._scalar


class _FakeDb:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.rollback_count = 0

    def execute(self, sql, params=None):
        sql_text = str(sql)
        self.calls.append((sql_text, params))
        for predicate, result in self.responses:
            if predicate(sql_text, params):
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"Unexpected query: {sql_text}")

    def rollback(self):
        self.rollback_count += 1


def test_get_summary_uses_cached_stats_when_available():
    video_id = uuid.uuid4()
    cached_stats = _FakeResult(
        first={
            "video_count": 12,
            "total_duration_seconds": 3456,
            "transcript_word_count": 7890,
            "updated_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
        }
    )
    recent_rows = _FakeResult(
        rows=[
            {
                "id": video_id,
                "youtube_id": "caption-only",
                "title": "Caption Only VOD",
                "duration_seconds": 300,
                "state": "completed",
                "caption_ingest_state": "completed",
                "diarization_state": None,
                "uploaded_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
                "created_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
                "channel_name": "HasanAbi",
                "language": "en",
                "category": None,
                "has_whisper_transcript": False,
                "has_youtube_transcript": True,
            },
            {
                "id": uuid.uuid4(),
                "youtube_id": "filtered-out",
                "title": "No Transcript Yet",
                "duration_seconds": 120,
                "state": "completed",
                "caption_ingest_state": "waiting",
                "diarization_state": None,
                "uploaded_at": datetime(2026, 6, 2, tzinfo=timezone.utc),
                "created_at": datetime(2026, 6, 2, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 6, 2, tzinfo=timezone.utc),
                "channel_name": "HasanAbi",
                "language": "en",
                "category": None,
                "has_whisper_transcript": False,
                "has_youtube_transcript": False,
            },
        ]
    )
    popular_rows = _FakeResult(rows=[{"term": "archive query", "frequency": 11}])

    db = _FakeDb(
        [
            (lambda sql, params: "FROM archive_summary_stats" in sql, cached_stats),
            (lambda sql, params: "FROM videos v" in sql and "LIMIT :limit" in sql, recent_rows),
            (lambda sql, params: "FROM search_suggestions" in sql, popular_rows),
        ]
    )

    summary = archive_repository.get_summary(db, recent_limit=5, popular_limit=5)

    assert summary.video_count == 12
    assert summary.total_duration_seconds == 3456
    assert summary.transcript_word_count == 7890
    assert len(summary.recent_videos) == 1
    assert summary.recent_videos[0].youtube_id == "caption-only"
    assert summary.recent_videos[0].has_youtube_transcript is True
    assert summary.popular_searches[0].term == "archive query"


def test_get_summary_falls_back_when_cached_stats_missing():
    fallback_stats = _FakeResult(
        first={
            "video_count": 2,
            "total_duration_seconds": 600,
            "transcript_word_count": 0,
            "updated_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
        }
    )
    recent_rows = _FakeResult(rows=[])
    popular_rows = _FakeResult(rows=[])

    db = _FakeDb(
        [
            (
                lambda sql, params: "FROM archive_summary_stats" in sql,
                ProgrammingError("missing table", None, None),
            ),
            (lambda sql, params: "FROM videos v" in sql and "COUNT(*) AS video_count" in sql, fallback_stats),
            (lambda sql, params: "FROM videos v" in sql and "LIMIT :limit" in sql, recent_rows),
            (lambda sql, params: "FROM search_suggestions" in sql, popular_rows),
        ]
    )

    summary = ArchiveRepository().get_summary(db)

    assert summary.video_count == 2
    assert summary.transcript_word_count == 0
    assert db.rollback_count == 1


def test_crud_wrapper_delegates_to_archive_repository(monkeypatch):
    sentinel = object()

    def fake_get_summary(db, recent_limit, popular_limit):
        assert db == "db"
        assert recent_limit == 3
        assert popular_limit == 4
        return sentinel

    monkeypatch.setattr(archive_repository, "get_summary", fake_get_summary)

    assert crud.get_archive_summary("db", recent_limit=3, popular_limit=4) is sentinel


def test_slugify_topic_normalizes_labels():
    assert slugify_topic("New Jersey!!!") == "new-jersey"
    assert slugify_topic("   ") == "topic"


def test_alias_matches_text_uses_word_boundaries():
    assert alias_matches_text("ice", "ICE Delaney protest") is True
    assert alias_matches_text("new jersey", "rally in New   Jersey today") is True
    assert alias_matches_text("ice", "anti-Semite price") is False


def test_seed_archive_topics_uses_publishable_defaults():
    class _SeedDb(_FakeDb):
        def execute(self, sql, params=None):
            sql_text = str(sql)
            self.calls.append((sql_text, params))
            if "SELECT slug FROM archive_topics" in sql_text:
                return _FakeResult(rows=[])
            return _FakeResult()

    db = _SeedDb([])
    stats = seed_archive_topics(db)

    assert stats["topics"] == len(SEED_TOPICS)
    assert any("'hybrid'" in sql and "'published'" in sql for sql, _ in db.calls if "INSERT INTO archive_topics" in sql)
    assert any("INSERT INTO archive_topic_aliases" in sql for sql, _ in db.calls)


def test_autopublish_search_topics_skips_existing_slugs():
    class _AutoDb(_FakeDb):
        def execute(self, sql, params=None):
            sql_text = str(sql)
            self.calls.append((sql_text, params))
            if "FROM search_suggestions" in sql_text:
                return _FakeResult(rows=[{"term": "new topic", "frequency": 9}, {"term": "ICE", "frequency": 5}])
            if "SELECT slug FROM archive_topics" in sql_text:
                return _FakeResult(rows=[{"slug": "ice"}])
            return _FakeResult()

    db = _AutoDb([])
    stats = autopublish_search_topics(db, limit=20)

    assert stats["topics"] == 1
    assert any("'automatic'" in sql and "new topic" in str(params) for sql, params in db.calls if "INSERT INTO archive_topics" in sql)
