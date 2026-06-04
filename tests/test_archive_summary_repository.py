"""Tests for archive summary repository behavior."""

import json
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.exc import ProgrammingError

from app import crud
from app.archive.repository import ArchiveRepository, archive_repository
from app.archive.intelligence_repository import (
    SEED_TOPICS,
    RETIRED_NAMED_PERIOD_SLUGS,
    _month_bounds,
    _week_bounds,
    alias_matches_text,
    autopublish_search_topics,
    seed_archive_topics,
    seed_named_periods,
    refresh_named_period_stats,
    slugify_topic,
)


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


class _SeedDb(_FakeDb):
    def __init__(self):
        super().__init__([])
        self.inserted_periods = []
        self.retired_periods = []

    def execute(self, sql, params=None):
        sql_text = str(sql)
        self.calls.append((sql_text, params))
        if "UPDATE archive_named_periods" in sql_text and "SET status = 'hidden'" in sql_text:
            self.retired_periods.append(params)
            return _FakeResult()
        if "SELECT DISTINCT date_trunc('month'" in sql_text or "SELECT DISTINCT date_trunc('week'" in sql_text:
            return _FakeResult(rows=[])
        if "SELECT DISTINCT EXTRACT(YEAR FROM v.uploaded_at)::int AS archive_year" in sql_text:
            return _FakeResult(rows=[{"archive_year": 2024}, {"archive_year": 2025}])
        if "INSERT INTO archive_named_periods" in sql_text:
            self.inserted_periods.append(params)
            return _FakeResult()
        raise AssertionError(f"Unexpected query: {sql_text}")


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


def test_named_period_bounds_helpers_cover_calendar_edges():
    month_start, month_end = _month_bounds(datetime(2026, 6, 4, tzinfo=timezone.utc).date())
    week_start, week_end = _week_bounds(datetime(2026, 6, 4, tzinfo=timezone.utc).date())

    assert month_start.isoformat() == "2026-06-01"
    assert month_end.isoformat() == "2026-06-30"
    assert week_start.weekday() == 0
    assert week_end.weekday() == 6


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


def test_seed_named_periods_corrects_current_curated_windows(monkeypatch):
    monkeypatch.setattr("app.archive.intelligence_repository._seed_today", lambda: date(2026, 11, 10))

    db = _SeedDb()

    seed_named_periods(db)

    by_slug = {row["slug"]: row for row in db.inserted_periods}
    retired_update_slugs = {params["slug"] for sql, params in db.calls if "UPDATE archive_named_periods" in sql and "SET status = 'hidden'" in sql}

    assert retired_update_slugs == set(RETIRED_NAMED_PERIOD_SLUGS)
    assert "october-7-leadup" not in by_slug
    assert by_slug["russia-ukraine-invasion-leadup"]["kind"] == "leadup"
    assert str(by_slug["russia-ukraine-invasion-leadup"]["date_from"]) == "2021-11-01"
    assert str(by_slug["russia-ukraine-invasion-leadup"]["date_to"]) == "2022-02-23"
    assert by_slug["russia-ukraine-invasion"]["kind"] == "event"
    assert str(by_slug["russia-ukraine-invasion"]["date_from"]) == "2022-02-24"
    assert by_slug["russia-ukraine-invasion-fallout"]["kind"] == "fallout"
    assert str(by_slug["russia-ukraine-invasion-fallout"]["date_to"]) == "2022-12-31"
    assert by_slug["2026-midterms-leadup"]["kind"] == "leadup"
    assert str(by_slug["2026-midterms-leadup"]["date_from"]) == "2026-11-03"
    assert str(by_slug["2026-midterms-leadup"]["date_to"]) == "2026-11-03"
    assert by_slug["2024-august-21"]["kind"] == "anniversary"
    assert by_slug["2025-august-21"]["kind"] == "anniversary"
    assert by_slug["2026-august-21"]["kind"] == "anniversary"


def test_refresh_named_period_stats_includes_metadata_in_public_payloads():
    video_id = uuid.uuid4()
    period_id = uuid.uuid4()
    topic_id = uuid.uuid4()
    person_slug = "guest-one"
    tag_slug = "chadvice"

    class _RefreshDb(_FakeDb):
        def __init__(self):
            super().__init__([])
            self.inserted_periods = []

        def execute(self, sql, params=None):
            sql_text = str(sql)
            self.calls.append((sql_text, params))
            if "FROM archive_named_periods p" in sql_text and "ORDER BY p.sort_order DESC" in sql_text:
                return _FakeResult(
                    rows=[
                        {
                            "id": period_id,
                            "slug": "test-period",
                            "label": "Test Period",
                            "kind": "month",
                            "date_from": date(2026, 5, 1),
                            "date_to": date(2026, 5, 31),
                            "description": None,
                            "status": "published",
                            "sort_order": 0,
                        }
                    ]
                )
            if "FROM archive_topics t" in sql_text and "LEFT JOIN archive_topic_aliases" in sql_text:
                return _FakeResult(
                    rows=[
                        {
                            "id": topic_id,
                            "slug": "ice",
                            "label": "ICE",
                            "description": None,
                            "source": "hybrid",
                            "status": "published",
                            "is_editable": True,
                            "aliases": [],
                        }
                    ]
                )
            if "FROM videos v" in sql_text and "v.uploaded_at >= :start_dt" in sql_text:
                return _FakeResult(
                    rows=[
                        {
                            "video_id": video_id,
                            "youtube_id": "meta1",
                            "title": "Metadata VOD",
                            "duration_seconds": 180,
                            "state": "completed",
                            "caption_ingest_state": "completed",
                            "diarization_state": None,
                            "uploaded_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
                            "created_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
                            "updated_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
                            "channel_name": "HasanAbi",
                            "language": "en",
                            "category": None,
                            "has_whisper_transcript": True,
                            "has_youtube_transcript": False,
                            "when_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
                        }
                    ]
                )
            if "FROM archive_topic_mentions m" in sql_text and "COALESCE(m.occurred_at, v.uploaded_at) >= :start_dt" in sql_text:
                return _FakeResult(
                    rows=[
                        {
                            "topic_id": topic_id,
                            "topic_slug": "ice",
                            "topic_label": "ICE",
                            "description": None,
                            "source": "hybrid",
                            "status": "published",
                            "is_editable": True,
                            "video_id": video_id,
                            "youtube_id": "meta1",
                            "title": "Metadata VOD",
                            "duration_seconds": 180,
                            "state": "completed",
                            "caption_ingest_state": "completed",
                            "diarization_state": None,
                            "uploaded_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
                            "created_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
                            "updated_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
                            "channel_name": "HasanAbi",
                            "language": "en",
                            "category": None,
                            "segment_id": uuid.uuid4(),
                            "start_ms": 1000,
                            "end_ms": 3000,
                            "snippet": "ICE said something about the border.",
                            "score": 1.0,
                            "when_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
                            "has_whisper_transcript": True,
                            "has_youtube_transcript": False,
                        }
                    ]
                )
            if "FROM archive_video_people vp" in sql_text:
                return _FakeResult(
                    rows=[
                        {
                            "video_id": video_id,
                            "slug": person_slug,
                            "display_name": "Guest One",
                            "aliases": [],
                            "description": None,
                            "role": "guest",
                            "confidence": "admin",
                            "notes": None,
                            "sort_order": 0,
                        }
                    ]
                )
            if "FROM archive_video_taggings vt" in sql_text:
                return _FakeResult(
                    rows=[
                        {
                            "video_id": video_id,
                            "slug": tag_slug,
                            "label": "Chadvice",
                            "kind": "category",
                            "description": None,
                            "confidence": "admin",
                            "notes": None,
                            "sort_order": 0,
                        }
                    ]
                )
            if "INSERT INTO archive_named_period_stats" in sql_text:
                self.inserted_periods.append(params)
                return _FakeResult()
            return _FakeResult()

    db = _RefreshDb()

    result = refresh_named_period_stats(db, period_slug="test-period")

    assert result["rows"] == 1
    inserted = db.inserted_periods[0][0]
    representative_videos = json.loads(inserted["representative_videos"])
    evidence = json.loads(inserted["evidence"])
    assert representative_videos[0]["people"][0]["slug"] == person_slug
    assert representative_videos[0]["tags"][0]["slug"] == tag_slug
    assert evidence[0]["video"]["people"][0]["slug"] == person_slug
    assert evidence[0]["video"]["tags"][0]["slug"] == tag_slug


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
