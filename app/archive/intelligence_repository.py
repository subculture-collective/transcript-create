from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from typing import Iterable, Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.archive.repository import ARCHIVE_VIDEO_FILTER_SQL, archive_repository
from app.schemas import (
    ArchiveEvidenceMoment,
    ArchiveIntelligenceResponse,
    ArchivePeriodIntelligence,
    ArchiveTopicCard,
    ArchiveTrendingSearch,
    VideoInfo,
)


@dataclass(frozen=True)
class SeedTopic:
    slug: str
    label: str
    aliases: tuple[str, ...]


SEED_TOPICS: tuple[SeedTopic, ...] = (
    SeedTopic("ice", "ICE", ("ice", "immigration", "deportation")),
    SeedTopic("gaza", "Gaza", ("gaza", "palestine", "israel")),
    SeedTopic("trump", "Trump", ("trump", "maga", "republicans")),
    SeedTopic("dsa", "DSA", ("dsa", "zohran", "socialists")),
    SeedTopic("epstein", "Epstein", ("epstein", "maxwell", "files")),
    SeedTopic("new-jersey", "New Jersey", ("new jersey", "newark", "delaney")),
)

AUTO_TOPIC_STOP_TERMS = {
    "hasan",
    "hasanabi",
    "hassan",
    "abi",
    "vod",
    "vods",
    "stream",
    "streams",
    "twitch",
    "youtube",
}


def slugify_topic(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "topic"


def alias_matches_text(alias: str, text_value: str) -> bool:
    """Match topic aliases as words/phrases, not substrings inside words.

    This prevents short aliases like "ice" from matching unrelated words such
    as "price" while still allowing phrase aliases like "new jersey" across
    ordinary whitespace.
    """
    alias_value = re.sub(r"\s+", " ", alias.strip().lower())
    text_value = re.sub(r"\s+", " ", text_value.lower())
    if not alias_value or not text_value:
        return False
    escaped = re.escape(alias_value).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text_value) is not None


def _safe_mappings(db, sql: str, params: dict | None = None):
    try:
        return db.execute(text(sql), params or {}).mappings().all()
    except (OperationalError, ProgrammingError):
        db.rollback()
        return []


def _safe_scalar(db, sql: str, params: dict | None = None):
    try:
        return db.execute(text(sql), params or {}).scalar_one()
    except (OperationalError, ProgrammingError):
        db.rollback()
        return None


def _safe_execute(db, sql: str, params: dict | None = None):
    try:
        return db.execute(text(sql), params or {})
    except (OperationalError, ProgrammingError):
        db.rollback()
        return None


def _safe_execute_many(db, sql: str, rows: Sequence[dict]):
    if not rows:
        return None
    try:
        return db.execute(text(sql), list(rows))
    except (OperationalError, ProgrammingError):
        db.rollback()
        return None


def _in_clause(prefix: str, values: Sequence[object]) -> tuple[str, dict[str, object]]:
    params: dict[str, object] = {}
    placeholders: list[str] = []
    for idx, value in enumerate(values):
        key = f"{prefix}_{idx}"
        placeholders.append(f":{key}")
        params[key] = value
    return ", ".join(placeholders), params


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return loaded if isinstance(loaded, list) else [loaded]
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_datetime(value: date | datetime | None, *, end: bool = False) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.combine(value, datetime.min.time())
        if end:
            dt = dt + timedelta(days=1)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _period_key(value: datetime | date | None, granularity: str) -> str | None:
    if value is None:
        return None
    dt = value if isinstance(value, datetime) else datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if granularity == "week":
        return dt.strftime("%G-W%V")
    return dt.strftime("%Y-%m")


def _period_start(period: str, granularity: str) -> datetime | None:
    try:
        if granularity == "week":
            return datetime.strptime(f"{period}-1", "%G-W%V-%u").replace(tzinfo=timezone.utc)
        return datetime.strptime(period, "%Y-%m").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _period_label(period: str, granularity: str) -> str:
    start = _period_start(period, granularity)
    if start is None:
        return period
    if granularity == "week":
        return f"Week of {start.strftime('%Y-%m-%d')}"
    return start.strftime("%B %Y")


def _within_period_range(period: str, granularity: str, date_from: date | datetime | None, date_to: date | datetime | None) -> bool:
    start = _period_start(period, granularity)
    if start is None:
        return True
    if date_from is not None:
        lower = _coerce_datetime(date_from)
        if lower is not None and start < lower:
            return False
    if date_to is not None:
        upper = _coerce_datetime(date_to, end=True)
        if upper is not None and start >= upper:
            return False
    return True


def _video_from_row(row) -> VideoInfo:
    return VideoInfo(
        id=row["video_id"],
        youtube_id=row["youtube_id"],
        title=row["title"],
        duration_seconds=row["duration_seconds"],
        state=row.get("state"),
        caption_ingest_state=row.get("caption_ingest_state"),
        diarization_state=row.get("diarization_state"),
        uploaded_at=row.get("uploaded_at"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        channel_name=row.get("channel_name"),
        language=row.get("language"),
        category=row.get("category"),
        has_whisper_transcript=bool(row.get("has_whisper_transcript")),
        has_youtube_transcript=bool(row.get("has_youtube_transcript")),
    )


def _evidence_from_row(row, *, topic: str | None = None) -> ArchiveEvidenceMoment:
    return ArchiveEvidenceMoment(
        video=_video_from_row(row),
        start_ms=int(row["start_ms"] or 0),
        end_ms=int(row["end_ms"] or 0),
        snippet=row["snippet"],
        topic=topic,
    )


def _public_topic_evidence_rows(rows: Iterable[dict], topic_label: str, limit: int) -> list[dict]:
    """Return public citation rows that visibly contain the displayed topic.

    Topic stats may use aliases for recall, but public citations should not look
    unrelated. If the card says "Gaza", its cited snippets need to contain
    "Gaza" rather than only an alias like "Israel".
    """
    matches = [row for row in rows if alias_matches_text(topic_label, row.get("snippet") or "")]
    return matches[:limit]


def _get_topics(db, topic_slug: str | None = None):
    params: dict[str, object] = {}
    where_parts = ["t.status = 'published'"]
    if topic_slug:
        where_parts.append("t.slug = :topic_slug")
        params["topic_slug"] = topic_slug
    where_sql = "WHERE " + " AND ".join(where_parts)

    rows = _safe_mappings(
        db,
        f"""
        SELECT
            t.id, t.slug, t.label, t.description, t.source, t.status, t.is_editable,
            COALESCE(
                json_agg(
                    json_build_object('alias', a.alias, 'weight', a.weight)
                    ORDER BY a.weight DESC, a.alias ASC
                ) FILTER (WHERE a.id IS NOT NULL),
                '[]'::json
            ) AS aliases
        FROM archive_topics t
        LEFT JOIN archive_topic_aliases a ON a.topic_id = t.id
        {where_sql}
        GROUP BY t.id
        ORDER BY t.label ASC
        """,
        params,
    )
    return rows


def _table_has_rows(db, table_name: str) -> bool:
    try:
        row = db.execute(text(f"SELECT 1 FROM {table_name} LIMIT 1")).first()
        return row is not None
    except (OperationalError, ProgrammingError):
        db.rollback()
        return False


def seed_archive_topics(db):
    inserted = 0
    updated = 0
    for seed in SEED_TOPICS:
        result = _safe_execute(
            db,
            """
            INSERT INTO archive_topics (slug, label, description, source, status, is_editable, created_at, updated_at)
            VALUES (:slug, :label, NULL, 'hybrid', 'published', true, now(), now())
            ON CONFLICT (slug) DO UPDATE SET
                label = EXCLUDED.label,
                source = 'hybrid',
                status = 'published',
                is_editable = true,
                updated_at = now()
            """,
            {"slug": seed.slug, "label": seed.label},
        )
        if result is None:
            continue
        inserted += 1
        for alias in dict.fromkeys(seed.aliases):
            _safe_execute(
                db,
                """
                INSERT INTO archive_topic_aliases (topic_id, alias, weight, created_at)
                SELECT id, :alias, 1, now() FROM archive_topics WHERE slug = :slug
                ON CONFLICT DO NOTHING
                """,
                {"slug": seed.slug, "alias": alias},
            )
        updated += 1
    return {"topics": inserted, "aliases": updated}


def autopublish_search_topics(db, limit: int = 20):
    rows = _safe_mappings(
        db,
        """
        SELECT term, frequency
        FROM search_suggestions
        ORDER BY frequency DESC, last_used DESC NULLS LAST, term ASC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    if not rows:
        return {"topics": 0}

    existing = {
        row["slug"]
        for row in _safe_mappings(db, "SELECT slug FROM archive_topics")
    }
    inserted = 0
    for row in rows:
        term = row["term"]
        slug = slugify_topic(term)
        if slug in AUTO_TOPIC_STOP_TERMS or term.strip().lower() in AUTO_TOPIC_STOP_TERMS:
            continue
        if slug in existing:
            continue
        result = _safe_execute(
            db,
            """
            INSERT INTO archive_topics (slug, label, description, source, status, is_editable, created_at, updated_at)
            VALUES (:slug, :label, NULL, 'automatic', 'published', true, now(), now())
            ON CONFLICT (slug) DO UPDATE SET
                label = EXCLUDED.label,
                source = 'automatic',
                status = 'published',
                is_editable = true,
                updated_at = now()
            """,
            {"slug": slug, "label": term},
        )
        if result is None:
            continue
        inserted += 1
        _safe_execute(
            db,
            """
            INSERT INTO archive_topic_aliases (topic_id, alias, weight, created_at)
            SELECT id, :alias, 1, now() FROM archive_topics WHERE slug = :slug
            ON CONFLICT DO NOTHING
            """,
            {"slug": slug, "alias": term},
        )
    return {"topics": inserted}


def hide_automatic_stop_topics(db):
    placeholders, params = _in_clause("stop_slug", sorted(AUTO_TOPIC_STOP_TERMS))
    result = _safe_execute(
        db,
        f"""
        UPDATE archive_topics
        SET status = 'hidden', updated_at = now()
        WHERE source = 'automatic' AND slug IN ({placeholders})
        """,
        params,
    )
    _ = result
    return {"topics": 0}


def refresh_topic_mentions(db, topic_slug: str | None = None, segment_limit: int | None = None):
    topics = _get_topics(db, topic_slug=topic_slug)
    if not topics:
        return {"topics": 0, "mentions": 0}

    topic_ids = [row["id"] for row in topics]
    topic_placeholders, topic_params = _in_clause("topic_id", topic_ids)
    _safe_execute(
        db,
        f"""
        DELETE FROM archive_topic_mentions
        WHERE topic_id IN ({topic_placeholders})
        """,
        topic_params,
    )

    alias_map: dict[str, list[tuple[str, float]]] = {}
    for row in topics:
        aliases = []
        for alias_row in _as_list(row.get("aliases")):
            alias = (alias_row or {}).get("alias")
            if alias:
                aliases.append((alias.lower(), float((alias_row or {}).get("weight") or 1)))
        alias_map[str(row["id"])] = aliases

    params: dict[str, object] = {}
    limit_sql = ""
    if segment_limit is not None:
        limit_sql = "LIMIT :segment_limit"
        params["segment_limit"] = segment_limit

    segment_rows = _safe_mappings(
        db,
        f"""
        SELECT
            s.id AS segment_id,
            s.video_id,
            s.start_ms,
            s.end_ms,
            s.text AS snippet,
            v.youtube_id,
            v.title,
            v.duration_seconds,
            v.state,
            v.caption_ingest_state,
            v.diarization_state,
            v.uploaded_at,
            v.created_at,
            v.updated_at,
            v.channel_name,
            v.language,
            v.category,
            EXISTS (SELECT 1 FROM segments s2 WHERE s2.video_id = v.id) AS has_whisper_transcript,
            EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id) AS has_youtube_transcript
        FROM segments s
        JOIN videos v ON v.id = s.video_id
        ORDER BY COALESCE(v.uploaded_at, v.created_at) DESC NULLS LAST, s.start_ms ASC
        {limit_sql}
        """,
        params,
    )

    mentions_by_key: dict[tuple[str, str, int, int], dict] = {}
    for row in segment_rows:
        snippet = (row["snippet"] or "").lower()
        if not snippet:
            continue
        for topic in topics:
            topic_id = str(topic["id"])
            best_weight = 0.0
            matched = False
            for alias, weight in alias_map.get(topic_id, []):
                if alias and alias_matches_text(alias, snippet):
                    matched = True
                    best_weight = max(best_weight, weight)
            if not matched:
                continue
            key = (topic_id, str(row["video_id"]), int(row["segment_id"]), int(row["start_ms"]))
            existing = mentions_by_key.get(key)
            mention = {
                "topic_id": topic["id"],
                "video_id": row["video_id"],
                "segment_id": int(row["segment_id"]),
                "start_ms": int(row["start_ms"]),
                "end_ms": int(row["end_ms"]),
                "snippet": row["snippet"],
                "score": best_weight or 1,
                "occurred_at": row.get("uploaded_at"),
            }
            if existing is None or float(mention["score"]) > float(existing["score"]):
                mentions_by_key[key] = mention

    mention_rows = list(mentions_by_key.values())
    _safe_execute_many(
        db,
        """
        INSERT INTO archive_topic_mentions (
            topic_id, video_id, segment_id, start_ms, end_ms, snippet, score, occurred_at, created_at
        ) VALUES (
            :topic_id, :video_id, :segment_id, :start_ms, :end_ms, :snippet, :score, :occurred_at, now()
        )
        """,
        mention_rows,
    )
    return {"topics": len(topics), "mentions": len(mention_rows)}


def refresh_topic_period_stats(db, granularity: str = "month"):
    if granularity not in {"month", "week"}:
        granularity = "month"

    topics = _get_topics(db)
    if not topics:
        return {"rows": 0}

    topic_ids = [row["id"] for row in topics]
    topic_placeholders, topic_params = _in_clause("topic_id", topic_ids)
    _safe_execute(
        db,
        f"""
        DELETE FROM archive_topic_period_stats
        WHERE topic_id IN ({topic_placeholders}) AND granularity = :granularity
        """,
        {**topic_params, "granularity": granularity},
    )

    rows = _safe_mappings(
        db,
        f"""
        SELECT
            m.topic_id,
            m.video_id,
            m.start_ms,
            m.end_ms,
            m.snippet,
            m.score,
            m.occurred_at,
            COALESCE(m.occurred_at, v.uploaded_at) AS when_at
        FROM archive_topic_mentions m
        JOIN videos v ON v.id = m.video_id
        WHERE m.topic_id IN ({topic_placeholders})
        ORDER BY COALESCE(m.occurred_at, v.uploaded_at, v.created_at) DESC NULLS LAST, m.start_ms ASC
        """,
        topic_params,
    )

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        when_at = row.get("when_at")
        period = _period_key(when_at, granularity)
        if period is None:
            continue
        grouped[(str(row["topic_id"]), period)].append(row)

    insert_rows: list[dict] = []
    for (topic_id, period), mention_rows in grouped.items():
        mention_count = len(mention_rows)
        video_ids = list(dict.fromkeys(str(row["video_id"]) for row in mention_rows))
        recent_cutoff = _utc_now() - timedelta(days=90)
        recent_mentions_90d = sum(1 for row in mention_rows if row.get("when_at") and row["when_at"] >= recent_cutoff)
        trend_score = mention_count + (recent_mentions_90d * 2)
        top_video_ids = []
        video_counts = Counter(str(row["video_id"]) for row in mention_rows)
        for video_id, _count in video_counts.most_common(5):
            top_video_ids.append(video_id)
        insert_rows.append(
            {
                "topic_id": topic_id,
                "period": period,
                "granularity": granularity,
                "mention_count": mention_count,
                "video_count": len(video_ids),
                "recent_mentions_90d": recent_mentions_90d,
                "trend_score": trend_score,
                "top_video_ids": json.dumps(top_video_ids),
            }
        )

    _safe_execute_many(
        db,
        """
        INSERT INTO archive_topic_period_stats (
            topic_id, period, granularity, mention_count, video_count, recent_mentions_90d,
            trend_score, top_video_ids, calculated_at
        ) VALUES (
            :topic_id, :period, :granularity, :mention_count, :video_count, :recent_mentions_90d,
            :trend_score, CAST(:top_video_ids AS jsonb), now()
        )
        """,
        insert_rows,
    )
    return {"rows": len(insert_rows)}


def refresh_search_trends(db, granularity: str = "week"):
    if granularity not in {"month", "week"}:
        granularity = "week"

    deleted = _safe_execute(
        db,
        "DELETE FROM archive_search_trends WHERE granularity = :granularity",
        {"granularity": granularity},
    )
    _ = deleted

    rows = _safe_mappings(
        db,
        f"""
        SELECT
            LOWER(query) AS term,
            date_trunc('{granularity}', created_at) AS period_start,
            COUNT(*)::int AS search_count,
            MAX(result_count) AS result_count,
            COUNT(*)::numeric AS trend_score
        FROM user_searches
        GROUP BY LOWER(query), date_trunc('{granularity}', created_at)
        ORDER BY date_trunc('{granularity}', created_at) DESC, COUNT(*) DESC, LOWER(query) ASC
        """,
    )

    insert_rows: list[dict] = []
    if rows:
        for row in rows:
            period_start = row["period_start"]
            period = _period_key(period_start, granularity)
            if period is None:
                continue
            insert_rows.append(
                {
                    "term": row["term"],
                    "period": period,
                    "granularity": granularity,
                    "search_count": int(row["search_count"] or 0),
                    "result_count": row["result_count"],
                    "trend_score": float(row["trend_score"] or 0),
                    "source": "search",
                }
            )
    else:
        suggestion_rows = _safe_mappings(
            db,
            """
            SELECT term, frequency
            FROM search_suggestions
            ORDER BY frequency DESC, last_used DESC NULLS LAST, term ASC
            LIMIT 50
            """,
        )
        current_period = _period_key(_utc_now(), granularity)
        for row in suggestion_rows:
            insert_rows.append(
                {
                    "term": row["term"],
                    "period": current_period,
                    "granularity": granularity,
                    "search_count": int(row["frequency"] or 0),
                    "result_count": None,
                    "trend_score": float(row["frequency"] or 0),
                    "source": "search",
                }
            )

    _safe_execute_many(
        db,
        """
        INSERT INTO archive_search_trends (
            term, period, granularity, search_count, result_count, trend_score, source, calculated_at
        ) VALUES (
            :term, :period, :granularity, :search_count, :result_count, :trend_score, :source, now()
        )
        """,
        insert_rows,
    )
    return {"rows": len(insert_rows)}


def refresh_period_summaries(db, granularity: str = "month", limit: int = 120):
    if granularity not in {"month", "week"}:
        granularity = "month"

    _safe_execute(
        db,
        "DELETE FROM archive_period_summaries WHERE granularity = :granularity",
        {"granularity": granularity},
    )

    video_rows = _safe_mappings(
        db,
        f"""
        SELECT
            v.id AS video_id,
            v.youtube_id,
            v.title,
            v.duration_seconds,
            v.state,
            v.caption_ingest_state,
            v.diarization_state,
            v.uploaded_at,
            v.created_at,
            v.updated_at,
            v.channel_name,
            v.language,
            v.category,
            EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id) AS has_whisper_transcript,
            EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id) AS has_youtube_transcript,
            COALESCE(v.uploaded_at, v.created_at) AS when_at
        FROM videos v
        WHERE ({ARCHIVE_VIDEO_FILTER_SQL})
          AND v.uploaded_at IS NOT NULL
        ORDER BY v.uploaded_at DESC NULLS LAST
        """,
    )

    mention_rows = _safe_mappings(
        db,
        """
        SELECT
            m.topic_id,
            t.slug AS topic_slug,
            t.label AS topic_label,
            m.video_id,
            v.youtube_id,
            v.title,
            v.duration_seconds,
            v.state,
            v.caption_ingest_state,
            v.diarization_state,
            v.uploaded_at,
            v.created_at,
            v.updated_at,
            v.channel_name,
            v.language,
            v.category,
            m.segment_id,
            m.start_ms,
            m.end_ms,
            m.snippet,
            m.score,
            COALESCE(m.occurred_at, v.uploaded_at) AS when_at,
            EXISTS (SELECT 1 FROM segments s2 WHERE s2.video_id = v.id) AS has_whisper_transcript,
            EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id) AS has_youtube_transcript
        FROM archive_topic_mentions m
        JOIN archive_topics t ON t.id = m.topic_id
        JOIN videos v ON v.id = m.video_id
        WHERE t.status = 'published'
        ORDER BY COALESCE(m.occurred_at, v.uploaded_at) DESC NULLS LAST, m.start_ms ASC
        """,
    )

    mentions_by_period: dict[str, list[dict]] = defaultdict(list)
    mentions_by_period_topic: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in mention_rows:
        period = _period_key(row.get("when_at"), granularity)
        if period is None:
            continue
        mentions_by_period[period].append(row)
        mentions_by_period_topic[(period, str(row["topic_id"]))].append(row)

    videos_by_period: dict[str, list[dict]] = defaultdict(list)
    for row in video_rows:
        period = _period_key(row.get("when_at"), granularity)
        if period is None:
            continue
        videos_by_period[period].append(row)

    periods = sorted(set(videos_by_period) | set(mentions_by_period), reverse=True)[:limit]
    insert_rows: list[dict] = []
    for period in periods:
        videos = videos_by_period.get(period, [])
        mentions = mentions_by_period.get(period, [])
        evidence_payload = []
        public_mentions = [row for row in mentions if alias_matches_text(row.get("topic_label") or "", row.get("snippet") or "")]
        for row in public_mentions[:5]:
            evidence_payload.append(
                {
                    "topic": row.get("topic_label"),
                    "video_id": str(row["video_id"]),
                    "youtube_id": row.get("youtube_id"),
                    "title": row.get("title"),
                    "start_ms": int(row["start_ms"] or 0),
                    "end_ms": int(row["end_ms"] or 0),
                    "snippet": row.get("snippet"),
                }
            )
        snippets = [entry["snippet"] for entry in evidence_payload if entry.get("snippet")]
        topic_names = list(dict.fromkeys(row.get("topic_label") for row in public_mentions if row.get("topic_label")))
        summary_parts = [f"{_period_label(period, granularity)}: {len(videos)} videos."]
        if topic_names:
            summary_parts.append(f"Topics: {', '.join(topic_names[:3])}.")
        if snippets:
            summary_parts.append("Evidence: " + " | ".join(snippets[:3]))
        insert_rows.append(
            {
                "period": period,
                "granularity": granularity,
                "video_count": len(videos),
                "total_duration_seconds": int(sum(int(row.get("duration_seconds") or 0) for row in videos)),
                "summary": " ".join(summary_parts),
                "evidence": json.dumps(evidence_payload),
            }
        )

    _safe_execute_many(
        db,
        """
        INSERT INTO archive_period_summaries (
            period, granularity, video_count, total_duration_seconds, summary, evidence, calculated_at
        ) VALUES (
            :period, :granularity, :video_count, :total_duration_seconds, :summary, CAST(:evidence AS jsonb), now()
        )
        """,
        insert_rows,
    )
    return {"rows": len(insert_rows)}


def refresh_archive_intelligence(db, quick: bool = False):
    stats = {}
    for prefix, result in (
        ("seed", seed_archive_topics(db)),
        ("hide_stop", hide_automatic_stop_topics(db)),
        ("auto", autopublish_search_topics(db, limit=20)),
        ("mentions", refresh_topic_mentions(db, segment_limit=1000 if quick else None)),
        ("topic_stats", refresh_topic_period_stats(db, granularity="month")),
        ("topic_stats_week", refresh_topic_period_stats(db, granularity="week")),
        ("search_trends", refresh_search_trends(db, granularity="week")),
        ("period_summaries", refresh_period_summaries(db, granularity="month", limit=120 if not quick else 72)),
        ("period_summaries_week", refresh_period_summaries(db, granularity="week", limit=120 if not quick else 72)),
    ):
        for key, value in result.items():
            stats[f"{prefix}_{key}"] = value
    return stats


def _topic_evidence_for_period(db, topic_id, period: str, granularity: str, limit: int = 2):
    rows = _safe_mappings(
        db,
        """
        SELECT
            m.topic_id,
            m.video_id,
            v.youtube_id,
            v.title,
            v.duration_seconds,
            v.state,
            v.caption_ingest_state,
            v.diarization_state,
            v.uploaded_at,
            v.created_at,
            v.updated_at,
            v.channel_name,
            v.language,
            v.category,
            m.start_ms,
            m.end_ms,
            m.snippet,
            EXISTS (SELECT 1 FROM segments s2 WHERE s2.video_id = v.id) AS has_whisper_transcript,
            EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id) AS has_youtube_transcript,
            COALESCE(m.occurred_at, v.uploaded_at) AS when_at
        FROM archive_topic_mentions m
        JOIN videos v ON v.id = m.video_id
        WHERE m.topic_id = :topic_id
        ORDER BY COALESCE(m.occurred_at, v.uploaded_at) DESC NULLS LAST, m.start_ms ASC
        """,
        {"topic_id": topic_id},
    )
    filtered = [row for row in rows if _period_key(row.get("when_at"), granularity) == period]
    return [_evidence_from_row(row, topic=None) for row in filtered[:limit]]


def get_durable_archive_intelligence(
    db,
    *,
    topic_limit: int = 8,
    period_limit: int = 8,
    granularity: str = "month",
    date_from: date | datetime | None = None,
    date_to: date | datetime | None = None,
) -> ArchiveIntelligenceResponse | None:
    if granularity not in {"month", "week"}:
        granularity = "month"
    if not (_table_has_rows(db, "archive_topics") and _table_has_rows(db, "archive_topic_mentions") and _table_has_rows(db, "archive_topic_period_stats") and _table_has_rows(db, "archive_period_summaries")):
        return None

    summary = archive_repository.get_summary(db, recent_limit=6, popular_limit=max(topic_limit, 8))
    topics = _get_topics(db)
    if not topics:
        return None

    topic_ids = [row["id"] for row in topics]
    topic_placeholders, topic_params = _in_clause("topic_id", topic_ids)
    stats_rows = _safe_mappings(
        db,
        f"""
        SELECT
            s.topic_id,
            s.period,
            s.granularity,
            s.mention_count,
            s.video_count,
            s.recent_mentions_90d,
            s.trend_score,
            s.top_video_ids,
            s.calculated_at,
            t.slug,
            t.label,
            t.description,
            t.source,
            t.status,
            t.is_editable
        FROM archive_topic_period_stats s
        JOIN archive_topics t ON t.id = s.topic_id
        WHERE s.topic_id IN ({topic_placeholders}) AND s.granularity = :granularity
        ORDER BY s.period DESC, s.trend_score DESC, t.label ASC
        """,
        {**topic_params, "granularity": granularity},
    )
    stats_rows = [row for row in stats_rows if _within_period_range(row["period"], granularity, date_from, date_to)]

    mentions_rows = _safe_mappings(
        db,
        f"""
        SELECT
            m.topic_id,
            t.slug AS topic_slug,
            t.label AS topic_label,
            t.description,
            t.source,
            t.status,
            t.is_editable,
            m.video_id,
            v.youtube_id,
            v.title,
            v.duration_seconds,
            v.state,
            v.caption_ingest_state,
            v.diarization_state,
            v.uploaded_at,
            v.created_at,
            v.updated_at,
            v.channel_name,
            v.language,
            v.category,
            m.segment_id,
            m.start_ms,
            m.end_ms,
            m.snippet,
            m.score,
            m.occurred_at,
            EXISTS (SELECT 1 FROM segments s2 WHERE s2.video_id = v.id) AS has_whisper_transcript,
            EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id) AS has_youtube_transcript,
            COALESCE(m.occurred_at, v.uploaded_at) AS when_at
        FROM archive_topic_mentions m
        JOIN archive_topics t ON t.id = m.topic_id
        JOIN videos v ON v.id = m.video_id
        WHERE m.topic_id IN ({topic_placeholders})
          AND t.status = 'published'
        ORDER BY COALESCE(m.occurred_at, v.uploaded_at) DESC NULLS LAST, m.start_ms ASC
        """,
        topic_params,
    )
    if date_from is not None:
        lower = _coerce_datetime(date_from)
        mentions_rows = [row for row in mentions_rows if row.get("when_at") is not None and row["when_at"] >= lower]
    if date_to is not None:
        upper = _coerce_datetime(date_to, end=True)
        mentions_rows = [row for row in mentions_rows if row.get("when_at") is not None and row["when_at"] < upper]

    mentions_by_topic: dict[str, list[dict]] = defaultdict(list)
    mentions_by_period: dict[str, list[dict]] = defaultdict(list)
    for row in mentions_rows:
        mentions_by_topic[str(row["topic_id"])].append(row)
        period = _period_key(row.get("when_at"), granularity)
        if period:
            mentions_by_period[period].append(row)

    topic_rows_by_id = {str(row["id"]): row for row in topics}
    topic_aggregate: dict[str, dict] = defaultdict(lambda: {"mention_count": 0, "video_ids": set(), "recent_mentions_90d": 0, "trend_score": 0.0, "periods": set()})
    for row in stats_rows:
        agg = topic_aggregate[str(row["topic_id"])]
        agg["mention_count"] += int(row.get("mention_count") or 0)
        agg["video_ids"].update(_as_list(row.get("top_video_ids")))
        agg["recent_mentions_90d"] += int(row.get("recent_mentions_90d") or 0)
        agg["trend_score"] += float(row.get("trend_score") or 0)
        agg["periods"].add(row["period"])

    topic_cards: list[ArchiveTopicCard] = []
    for topic_id, agg in sorted(topic_aggregate.items(), key=lambda item: item[1]["trend_score"], reverse=True)[:topic_limit]:
        topic_row = topic_rows_by_id.get(topic_id)
        if topic_row is None:
            continue
        evidence_rows = _public_topic_evidence_rows(mentions_by_topic.get(topic_id, []), topic_row["label"], 2)
        evidence = [_evidence_from_row(row, topic=topic_row["label"]) for row in evidence_rows]
        snippets = [moment.snippet for moment in evidence]
        related_topics = []
        haystack = " ".join(snippets).lower()
        for other in topics:
            if str(other["id"]) == topic_id:
                continue
            if any(alias_matches_text((alias_row or {}).get("alias", ""), haystack) for alias_row in _as_list(other.get("aliases"))):
                related_topics.append(other["label"])
        topic_cards.append(
            ArchiveTopicCard(
                slug=topic_row["slug"],
                label=topic_row["label"],
                source=topic_row["source"],
                status=topic_row.get("status") or "published",
                is_editable=bool(topic_row.get("is_editable", True)),
                aliases=[(alias_row or {}).get("alias") for alias_row in _as_list(topic_row.get("aliases")) if (alias_row or {}).get("alias")],
                total_moments=int(agg["mention_count"]),
                total_videos=len({str(video_id) for video_id in agg["video_ids"]}),
                recent_mentions_90d=int(agg["recent_mentions_90d"]),
                trend_score=float(agg["trend_score"]),
                related_topics=related_topics[:3],
                evidence=evidence,
            )
        )

    topic_cards = sorted(topic_cards, key=lambda topic: topic.trend_score, reverse=True)[:topic_limit]

    topic_search_trends = [
        ArchiveTrendingSearch(term=topic.label, frequency=topic.total_moments, trend_score=topic.trend_score, source="hybrid")
        for topic in topic_cards
    ]
    search_trends_rows = _safe_mappings(
        db,
        """
        SELECT term, period, granularity, search_count, result_count, trend_score, source
        FROM archive_search_trends
        WHERE granularity = :granularity
        ORDER BY trend_score DESC, search_count DESC, term ASC
        """,
        {"granularity": granularity},
    )
    search_trends_rows = [row for row in search_trends_rows if _within_period_range(row["period"], granularity, date_from, date_to)]
    search_trends = [
        ArchiveTrendingSearch(
            term=row["term"],
            frequency=int(row.get("search_count") or 0),
            trend_score=float(row.get("trend_score") or 0),
            source=row.get("source") or "search",
        )
        for row in search_trends_rows
    ]
    trending_searches: list[ArchiveTrendingSearch] = []
    seen_terms: set[str] = set()
    for item in [*search_trends, *topic_search_trends]:
        key = item.term.lower()
        if key in seen_terms:
            continue
        trending_searches.append(item)
        seen_terms.add(key)
    trending_searches = sorted(trending_searches, key=lambda item: item.trend_score, reverse=True)[: max(topic_limit, 8)]

    suggested_searches: list[ArchiveTrendingSearch] = []
    seen_terms.clear()
    for item in [*topic_search_trends, *search_trends]:
        key = item.term.lower()
        if key in seen_terms:
            continue
        suggested_searches.append(ArchiveTrendingSearch(term=item.term, frequency=item.frequency, trend_score=item.trend_score, source=item.source))
        seen_terms.add(key)
        if len(suggested_searches) >= max(topic_limit, len(SEED_TOPICS)):
            break

    period_rows = _safe_mappings(
        db,
        """
        SELECT period, granularity, video_count, total_duration_seconds, summary, evidence, calculated_at
        FROM archive_period_summaries
        WHERE granularity = :granularity
        ORDER BY period DESC, calculated_at DESC
        """,
        {"granularity": granularity},
    )
    period_rows = [row for row in period_rows if _within_period_range(row["period"], granularity, date_from, date_to)]
    periods: list[ArchivePeriodIntelligence] = []
    for row in period_rows[:period_limit]:
        period = row["period"]
        period_topic_stats = [s for s in stats_rows if s["period"] == period]
        period_top_topics: list[ArchiveTopicCard] = []
        for stat_row in sorted(period_topic_stats, key=lambda item: float(item.get("trend_score") or 0), reverse=True)[:3]:
            topic_row = topic_rows_by_id.get(str(stat_row["topic_id"]))
            if topic_row is None:
                continue
            evidence_rows = _public_topic_evidence_rows(
                [ev_row for ev_row in mentions_by_period.get(period, []) if str(ev_row["topic_id"]) == str(stat_row["topic_id"])],
                topic_row["label"],
                1,
            )
            evidence = [_evidence_from_row(ev_row, topic=topic_row["label"]) for ev_row in evidence_rows]
            period_top_topics.append(
                ArchiveTopicCard(
                    slug=topic_row["slug"],
                    label=topic_row["label"],
                    source=topic_row["source"],
                    status=topic_row.get("status") or "published",
                    is_editable=bool(topic_row.get("is_editable", True)),
                    aliases=[(alias_row or {}).get("alias") for alias_row in _as_list(topic_row.get("aliases")) if (alias_row or {}).get("alias")],
                    total_moments=int(stat_row.get("mention_count") or 0),
                    total_videos=int(stat_row.get("video_count") or 0),
                    recent_mentions_90d=int(stat_row.get("recent_mentions_90d") or 0),
                    trend_score=float(stat_row.get("trend_score") or 0),
                    related_topics=[],
                    evidence=evidence,
                )
            )
        evidence_payload = _as_list(row.get("evidence"))
        period_evidence: list[ArchiveEvidenceMoment] = []
        for item in evidence_payload:
            video_row = next((candidate for candidate in mentions_by_period.get(period, []) if str(candidate["video_id"]) == str(item.get("video_id")) and int(candidate["start_ms"] or 0) == int(item.get("start_ms") or 0)), None)
            if video_row is None:
                continue
            period_evidence.append(
                _evidence_from_row(
                    {
                        **video_row,
                        "start_ms": item.get("start_ms"),
                        "end_ms": item.get("end_ms"),
                        "snippet": item.get("snippet"),
                    },
                    topic=item.get("topic"),
                )
            )
        if not period_evidence:
            period_evidence = [_evidence_from_row(row_item, topic=row_item.get("topic_label")) for row_item in mentions_by_period.get(period, [])[:5]]
        period_videos: list[dict] = []
        seen_video_ids: set[str] = set()
        for row_item in mentions_by_period.get(period, []):
            video_id = str(row_item["video_id"])
            if video_id in seen_video_ids:
                continue
            seen_video_ids.add(video_id)
            period_videos.append(row_item)
        periods.append(
            ArchivePeriodIntelligence(
                period=period,
                label=_period_label(period, granularity),
                video_count=int(row.get("video_count") or 0),
                total_duration_seconds=int(row.get("total_duration_seconds") or 0),
                videos=[_video_from_row(video_row) for video_row in period_videos[:3]],
                top_topics=period_top_topics,
                summary=row.get("summary") or "",
                evidence=period_evidence,
            )
        )

    return ArchiveIntelligenceResponse(
        summary=summary,
        exploration_modes=["timeline", "topics", "trending", "suggested"],
        trending_searches=trending_searches,
        suggested_searches=suggested_searches,
        topic_cards=topic_cards,
        periods=periods,
        query_time_ms=None,
    )
