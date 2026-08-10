"""Tests for archive summary repository behavior."""

import json
import uuid
from collections import Counter
from contextlib import nullcontext
from datetime import date, datetime, timezone
from types import MappingProxyType

from sqlalchemy.exc import ProgrammingError

from app import crud
from app.archive.intelligence_repository import (
    RETIRED_NAMED_PERIOD_SLUGS,
    SEED_TOPICS,
    _month_bounds,
    _period_intelligence_from_row,
    _safe_mappings,
    _safe_video_metadata_map,
    _scope_named_period_intelligence,
    _week_bounds,
    alias_matches_text,
    autopublish_search_topics,
    merge_label_topic_cards,
    refresh_named_period_stats,
    refresh_topic_mentions,
    refresh_topic_period_stats,
    seed_archive_topics,
    seed_named_periods,
    slugify_topic,
)
from app.archive.repository import ArchiveRepository, archive_repository
from app.schemas import (
    ArchiveEvidenceMoment,
    ArchivePeriodIntelligence,
    ArchivePeriodOption,
    ArchiveTopicCard,
    VideoInfo,
)


class _ImmutableMappingResult:
    def mappings(self):
        return self

    def all(self):
        return [MappingProxyType({"video_id": "video-1", "title": "Immutable row"})]


class _ImmutableMappingDb:
    def execute(self, *args, **kwargs):
        return _ImmutableMappingResult()


def test_safe_mappings_returns_mutable_dict_rows():
    rows = _safe_mappings(_ImmutableMappingDb(), "SELECT 1")

    assert rows == [{"video_id": "video-1", "title": "Immutable row"}]
    rows[0]["people"] = []
    assert rows[0]["people"] == []


def test_safe_video_metadata_map_uses_savepoint_without_rolling_back_refresh_writes(monkeypatch):
    class _Savepoint:
        def __init__(self, db):
            self.db = db

        def __enter__(self):
            self.db.savepoints_started += 1

        def __exit__(self, exc_type, exc, traceback):
            if exc_type is not None:
                self.db.savepoints_rolled_back += 1
            return False

    class _Db:
        def __init__(self):
            self.refresh_writes = ["stats row"]
            self.rollback_count = 0
            self.savepoints_started = 0
            self.savepoints_rolled_back = 0

        def begin_nested(self):
            return _Savepoint(self)

        def rollback(self):
            self.rollback_count += 1

    def fail_metadata_lookup(*args, **kwargs):
        raise ProgrammingError("metadata lookup failed", None, None)

    monkeypatch.setattr("app.archive.intelligence_repository.get_video_metadata_map", fail_metadata_lookup)
    db = _Db()

    metadata = _safe_video_metadata_map(db, ["video-1"])

    assert metadata == {"video-1": {"people": [], "tags": []}}
    assert db.refresh_writes == ["stats row"]
    assert db.rollback_count == 0
    assert db.savepoints_started == db.savepoints_rolled_back == 1


def test_named_period_cache_drops_out_of_scope_videos_and_citations():
    july_video = VideoInfo(
        id=uuid.uuid4(),
        youtube_id="july-video",
        uploaded_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
    )
    june_video = VideoInfo(
        id=uuid.uuid4(),
        youtube_id="june-video",
        uploaded_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )

    def evidence(video, snippet):
        return ArchiveEvidenceMoment(video=video, start_ms=0, end_ms=1000, snippet=snippet)

    period = ArchivePeriodIntelligence(
        period="2026-07",
        label="July 2026",
        video_count=2,
        total_duration_seconds=200,
        videos=[july_video, june_video],
        top_topics=[
            ArchiveTopicCard(
                slug="housing",
                label="Housing",
                source="hybrid",
                evidence=[evidence(july_video, "July citation"), evidence(june_video, "June citation")],
            )
        ],
        summary="Cached summary",
        evidence=[evidence(july_video, "July citation"), evidence(june_video, "June citation")],
    )
    option = ArchivePeriodOption(
        slug="2026-07",
        label="July 2026",
        kind="month",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
    )

    scoped = _scope_named_period_intelligence(period, option)

    assert [video.youtube_id for video in scoped.videos] == ["july-video"]
    assert [moment.snippet for moment in scoped.evidence] == ["July citation"]
    assert [moment.snippet for moment in scoped.top_topics[0].evidence] == ["July citation"]


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

    def begin_nested(self):
        return nullcontext()


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
    kind_counts = Counter(row["kind"] for row in by_slug.values())
    retired_update_slugs = {
        params["slug"] for sql, params in db.calls if "UPDATE archive_named_periods" in sql and "slug = :slug" in sql
    }
    retired_update_patterns = {
        params["pattern"]
        for sql, params in db.calls
        if "UPDATE archive_named_periods" in sql and "slug ~ :pattern" in sql
    }

    assert retired_update_slugs == set(RETIRED_NAMED_PERIOD_SLUGS)
    assert r"^[0-9]{4}-august-21$" in retired_update_patterns
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
    assert "2024-august-21" not in by_slug
    assert "2025-august-21" not in by_slug
    assert by_slug["august-21"]["kind"] == "anniversary"
    assert by_slug["august-21"]["recurring_month"] == 8
    assert by_slug["august-21"]["recurring_day"] == 21
    assert by_slug["christmas"]["kind"] == "holiday"
    assert by_slug["christmas"]["recurring_month"] == 12
    assert by_slug["christmas"]["recurring_day"] == 25
    assert by_slug["new-year"]["kind"] == "holiday"
    assert by_slug["new-year"]["recurring_month"] == 1
    assert by_slug["new-year"]["recurring_day"] == 1
    assert by_slug["may-day"]["kind"] == "holiday"
    assert by_slug["may-day"]["recurring_month"] == 5
    assert by_slug["may-day"]["recurring_day"] == 1
    assert kind_counts["event"] >= 10
    assert kind_counts["leadup"] >= 5
    assert kind_counts["fallout"] >= 5
    assert kind_counts["holiday"] >= 8
    assert kind_counts["anniversary"] >= 8
    assert kind_counts["date"] >= 5
    assert by_slug["january-6-capitol-attack"]["kind"] == "event"
    assert by_slug["gamestop-saga"]["kind"] == "event"
    assert by_slug["dobbs-leadup"]["kind"] == "leadup"
    assert by_slug["2022-midterms-fallout"]["kind"] == "fallout"
    assert by_slug["juneteenth"]["recurring_month"] == 6
    assert by_slug["october-7-anniversary"]["recurring_day"] == 7
    assert by_slug["2024-election-day"]["kind"] == "date"


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
                            "recurring_month": None,
                            "recurring_day": None,
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
            if (
                "FROM archive_topic_mentions m" in sql_text
                and "COALESCE(m.occurred_at, v.uploaded_at, v.created_at) >= :start_dt" in sql_text
            ):
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


def test_refresh_named_period_stats_uses_recurring_month_day_filter():
    period_id = uuid.uuid4()

    class _RecurringDb(_FakeDb):
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
                            "slug": "august-21",
                            "label": "August 21",
                            "kind": "anniversary",
                            "date_from": date(1970, 8, 21),
                            "date_to": date(1970, 8, 21),
                            "description": "August 21 streams across every archive year",
                            "status": "published",
                            "sort_order": 0,
                            "recurring_month": 8,
                            "recurring_day": 21,
                        }
                    ]
                )
            if "FROM archive_topics t" in sql_text and "LEFT JOIN archive_topic_aliases" in sql_text:
                return _FakeResult(rows=[])
            if "FROM videos v" in sql_text and "EXTRACT(MONTH FROM v.uploaded_at)" in sql_text:
                assert params == {"recurring_month": 8, "recurring_day": 21}
                return _FakeResult(rows=[])
            if (
                "FROM archive_topic_mentions m" in sql_text
                and "EXTRACT(MONTH FROM COALESCE(m.occurred_at, v.uploaded_at, v.created_at))" in sql_text
            ):
                assert params == {"recurring_month": 8, "recurring_day": 21}
                return _FakeResult(rows=[])
            if "INSERT INTO archive_named_period_stats" in sql_text:
                self.inserted_periods.append(params)
                return _FakeResult()
            return _FakeResult()

    db = _RecurringDb()

    result = refresh_named_period_stats(db, period_slug="august-21")

    assert result["rows"] == 1
    assert db.inserted_periods[0][0]["video_count"] == 0
    assert any("EXTRACT(MONTH FROM v.uploaded_at)" in sql for sql, _ in db.calls)
    assert not any("v.uploaded_at >= :start_dt" in sql for sql, _ in db.calls)


def test_refresh_topic_mentions_uses_youtube_caption_segments():
    topic_id = uuid.uuid4()
    video_id = uuid.uuid4()

    class _TopicDb(_FakeDb):
        def __init__(self):
            super().__init__([])
            self.inserted_mentions = []

        def execute(self, sql, params=None):
            sql_text = str(sql)
            self.calls.append((sql_text, params))
            if "FROM archive_topics t" in sql_text and "LEFT JOIN archive_topic_aliases" in sql_text:
                return _FakeResult(
                    rows=[
                        {
                            "id": topic_id,
                            "slug": "gaza",
                            "label": "Gaza",
                            "description": None,
                            "source": "hybrid",
                            "status": "published",
                            "is_editable": True,
                            "aliases": [{"alias": "gaza", "weight": 1}],
                        }
                    ]
                )
            if "DELETE FROM archive_topic_mentions" in sql_text:
                return _FakeResult()
            if "FROM youtube_segments ys" in sql_text and "UNION ALL" in sql_text:
                return _FakeResult(
                    rows=[
                        {
                            "segment_id": -123,
                            "video_id": video_id,
                            "start_ms": 1000,
                            "end_ms": 4000,
                            "snippet": "A YouTube caption segment mentioning Gaza.",
                            "youtube_id": "yt123",
                            "title": "Caption-only VOD",
                            "duration_seconds": 600,
                            "state": "completed",
                            "caption_ingest_state": "completed",
                            "diarization_state": None,
                            "uploaded_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                            "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                            "channel_name": "HasanAbi",
                            "language": "en",
                            "category": None,
                            "has_whisper_transcript": False,
                            "has_youtube_transcript": True,
                        }
                    ]
                )
            if "INSERT INTO archive_topic_mentions_stage" in sql_text:
                self.inserted_mentions.extend(params or [])
                return _FakeResult()
            return _FakeResult()

    db = _TopicDb()

    result = refresh_topic_mentions(db)

    assert result == {"topics": 1, "mentions": 1}
    assert db.inserted_mentions[0]["video_id"] == video_id
    assert db.inserted_mentions[0]["segment_id"] == -123
    assert "YouTube caption segment" in db.inserted_mentions[0]["snippet"]


def test_refresh_topic_mentions_reconciles_stage_without_rewriting_unchanged_rows():
    topic_id = uuid.uuid4()
    unselected_topic_id = uuid.uuid4()

    class _ReconcileDb(_FakeDb):
        def execute(self, sql, params=None):
            sql_text = str(sql)
            self.calls.append((sql_text, params))
            if "FROM archive_topics t" in sql_text:
                return _FakeResult(
                    rows=[
                        {
                            "id": topic_id,
                            "slug": "gaza",
                            "label": "Gaza",
                            "aliases": [],
                        }
                    ]
                )
            return _FakeResult()

    db = _ReconcileDb([])

    assert refresh_topic_mentions(db) == {"topics": 1, "mentions": 0}

    sql_calls = [sql for sql, _ in db.calls]
    lock_index = next(i for i, sql in enumerate(sql_calls) if "pg_advisory_xact_lock" in sql)
    topic_index = next(i for i, sql in enumerate(sql_calls) if "FROM archive_topics t" in sql)
    assert lock_index < topic_index
    assert any("CREATE TEMP TABLE archive_topic_mentions_stage" in sql and "ON COMMIT DROP" in sql for sql in sql_calls)
    assert any("ANALYZE archive_topic_mentions_stage" in sql for sql in sql_calls)

    delete_sql, delete_params = next(
        (sql, params) for sql, params in db.calls if "DELETE FROM archive_topic_mentions m" in sql
    )
    assert "NOT EXISTS" in delete_sql
    assert delete_params == {"topic_id_0": topic_id}
    assert unselected_topic_id not in delete_params.values()

    upsert_sql = next(sql for sql in sql_calls if "INSERT INTO archive_topic_mentions AS m" in sql)
    assert "existing.id IS NULL" in upsert_sql
    for column in ("end_ms", "snippet", "score", "occurred_at"):
        assert f"existing.{column} IS DISTINCT FROM s.{column}" in upsert_sql
        assert f"m.{column} IS DISTINCT FROM EXCLUDED.{column}" in upsert_sql
    assert "ON CONFLICT (topic_id, video_id, segment_id, start_ms) DO UPDATE" in upsert_sql
    assert "created_at =" not in upsert_sql.split("DO UPDATE SET", 1)[1]


def test_refresh_topic_mentions_partial_scan_never_deletes_staged_absences():
    topic_id = uuid.uuid4()

    class _PartialDb(_FakeDb):
        def execute(self, sql, params=None):
            sql_text = str(sql)
            self.calls.append((sql_text, params))
            if "FROM archive_topics t" in sql_text:
                return _FakeResult(
                    rows=[
                        {
                            "id": topic_id,
                            "slug": "gaza",
                            "label": "Gaza",
                            "aliases": [],
                        }
                    ]
                )
            return _FakeResult()

    db = _PartialDb([])

    assert refresh_topic_mentions(db, segment_limit=100) == {"topics": 1, "mentions": 0}
    assert not any("DELETE FROM archive_topic_mentions m" in sql for sql, _ in db.calls)


def test_refresh_topic_period_stats_uses_created_at_when_uploaded_at_missing():
    topic_id = uuid.uuid4()
    video_id = uuid.uuid4()

    class _StatsDb(_FakeDb):
        def __init__(self):
            super().__init__([])
            self.inserted_stats = []

        def execute(self, sql, params=None):
            sql_text = str(sql)
            self.calls.append((sql_text, params))
            if "FROM archive_topics t" in sql_text and "LEFT JOIN archive_topic_aliases" in sql_text:
                return _FakeResult(
                    rows=[
                        {
                            "id": topic_id,
                            "slug": "gaza",
                            "label": "Gaza",
                            "description": None,
                            "source": "hybrid",
                            "status": "published",
                            "is_editable": True,
                            "aliases": [{"alias": "gaza", "weight": 1}],
                        }
                    ]
                )
            if "DELETE FROM archive_topic_period_stats" in sql_text:
                return _FakeResult()
            if (
                "FROM archive_topic_mentions m" in sql_text
                and "COALESCE(m.occurred_at, v.uploaded_at, v.created_at) AS when_at" in sql_text
            ):
                return _FakeResult(
                    rows=[
                        {
                            "topic_id": topic_id,
                            "video_id": video_id,
                            "start_ms": 1000,
                            "end_ms": 4000,
                            "snippet": "Gaza caption mention",
                            "score": 1.0,
                            "occurred_at": None,
                            "when_at": datetime(2026, 6, 4, tzinfo=timezone.utc),
                        }
                    ]
                )
            if "INSERT INTO archive_topic_period_stats" in sql_text:
                self.inserted_stats.extend(params or [])
                return _FakeResult()
            return _FakeResult()

    db = _StatsDb()

    result = refresh_topic_period_stats(db, granularity="month")

    assert result == {"rows": 1}
    assert db.inserted_stats[0]["period"] == "2026-06"


def test_search_suggestions_never_publish_archive_topics():
    class _AutoDb(_FakeDb):
        def execute(self, sql, params=None):
            sql_text = str(sql)
            self.calls.append((sql_text, params))
            if "FROM search_suggestions" in sql_text:
                return _FakeResult(
                    rows=[
                        {"term": "new topic", "frequency": 9},
                        {"term": "number", "frequency": 8},
                        {"term": "okay", "frequency": 7},
                        {"term": "that's", "frequency": 6},
                        {"term": "ICE", "frequency": 5},
                    ]
                )
            if "SELECT slug FROM archive_topics" in sql_text:
                return _FakeResult(rows=[{"slug": "ice"}])
            return _FakeResult()

    db = _AutoDb([])
    stats = autopublish_search_topics(db, limit=20)

    assert stats == {"topics": 0}
    assert not any("INSERT INTO archive_topics" in sql for sql, _params in db.calls)


def test_merge_topic_cards_excludes_untrusted_automatic_and_junk_cards():
    def card(slug: str, label: str, source: str, trend_score: float):
        return ArchiveTopicCard(
            slug=slug,
            label=label,
            source=source,
            aliases=[label],
            total_moments=10,
            total_videos=2,
            recent_mentions_90d=3,
            trend_score=trend_score,
            related_topics=[],
            evidence=[],
        )

    merged = merge_label_topic_cards(
        [card("know", "know", "automatic", 100), card("gaza", "Gaza", "hybrid", 20)],
        [card("number", "number", "automatic", 80), card("abortion", "Abortion", "admin", 15)],
        limit=8,
    )

    assert [item.slug for item in merged] == ["gaza", "abortion"]


def test_cached_period_topics_are_revalidated_before_public_use():
    cached_card = {
        "slug": "know",
        "label": "know",
        "source": "automatic",
        "aliases": ["know"],
        "total_moments": 100,
        "total_videos": 20,
        "recent_mentions_90d": 100,
        "trend_score": 100,
        "related_topics": [],
        "evidence": [],
    }
    trusted_card = {**cached_card, "slug": "gaza", "label": "Gaza", "source": "hybrid", "trend_score": 20}

    period = _period_intelligence_from_row(
        {
            "slug": "2026-06",
            "label": "June 2026",
            "video_count": 2,
            "total_duration_seconds": 100,
            "top_topics": [cached_card, trusted_card],
            "summary": "Cached snapshot",
            "evidence": [],
            "representative_videos": [],
        }
    )

    assert [item.slug for item in period.top_topics] == ["gaza"]
