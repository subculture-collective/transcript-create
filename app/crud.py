import functools
import json
import time
import uuid

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.cache import cache
from app.logging_config import get_logger
from app.settings import settings
from sqlalchemy import bindparam

logger = get_logger(__name__)

# Database retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 0.5  # seconds


def _retry_on_transient_error(func):
    """Decorator to retry database operations on transient errors."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except OperationalError as e:
                last_error = e
                error_msg = str(e).lower()
                # Check if it's a transient error worth retrying
                if any(
                    pattern in error_msg
                    for pattern in ["connection", "timeout", "deadlock", "could not connect", "server closed"]
                ):
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAY * (2**attempt)  # Exponential backoff
                        logger.warning(
                            "Database transient error - retrying",
                            extra={
                                "attempt": attempt + 1,
                                "max_retries": MAX_RETRIES,
                                "retry_delay": delay,
                                "error": str(e),
                            },
                        )
                        time.sleep(delay)
                        continue
                # Not a transient error or max retries reached
                logger.error(
                    "Database error after retries",
                    extra={"attempts": attempt + 1, "error": str(e)},
                )
                raise
            except Exception:
                # For non-transient errors, raise immediately
                raise
        # Should not reach here, but just in case
        if last_error:
            raise last_error

    return wrapper


@_retry_on_transient_error
def create_job(db, kind: str, url: str, meta: dict | None = None):
    import json

    from app.metrics import jobs_created_total

    job_id = uuid.uuid4()
    meta_json = json.dumps(meta) if meta else "{}"
    db.execute(
        text("INSERT INTO jobs (id, kind, input_url, meta) VALUES (:i,:k,:u,:m)"),
        {"i": str(job_id), "k": kind, "u": url, "m": meta_json},
    )
    db.commit()

    # Track job creation metric
    jobs_created_total.labels(kind=kind).inc()

    return job_id


@_retry_on_transient_error
def fetch_job(db, job_id: uuid.UUID):
    # Pass UUID directly to ensure proper binding/casting
    row = db.execute(text("SELECT * FROM jobs WHERE id=:i"), {"i": job_id}).mappings().first()
    return row


@_retry_on_transient_error
@cache(prefix="segments", ttl=settings.CACHE_TRANSCRIPT_TTL if settings.ENABLE_CACHING else 0)
def list_segments(db, video_id):
    # Support both schemas: segments linked directly to video_id, or indirectly via transcripts
    sql = """
        SELECT s.start_ms, s.end_ms, s.text, s.speaker_label
        FROM segments s
        LEFT JOIN transcripts t ON t.id = s.transcript_id
        WHERE s.video_id = :v OR (s.transcript_id IS NOT NULL AND t.video_id = :v)
        ORDER BY s.start_ms
    """
    rows = db.execute(text(sql), {"v": str(video_id)}).all()
    return rows


@_retry_on_transient_error
@cache(prefix="video", ttl=settings.CACHE_VIDEO_TTL if settings.ENABLE_CACHING else 0)
def get_video(db, video_id: uuid.UUID):
    return (
        db.execute(
            text(
                """
                SELECT
                    v.id, v.youtube_id, v.title, v.duration_seconds, v.state,
                    v.caption_ingest_state, v.diarization_state, v.uploaded_at,
                    v.created_at, v.updated_at, v.channel_name, v.language, v.category,
                    EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id) AS has_whisper_transcript,
                    EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id) AS has_youtube_transcript
                FROM videos v
                WHERE v.id=:v
                """
            ),
            {"v": str(video_id)},
        )
        .mappings()
        .first()
    )


@_retry_on_transient_error
def list_videos(
    db,
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    date_field: str = "uploaded_at",
    date_from=None,
    date_to=None,
    completed_only: bool = False,
    category: str | None = None,
):
    date_column = date_field if date_field in {"uploaded_at", "created_at", "updated_at"} else "uploaded_at"
    where_clauses = []
    params: dict[str, object] = {"limit": limit, "offset": offset}

    if q:
        where_clauses.append("(v.title ILIKE :q OR v.youtube_id ILIKE :q OR v.channel_name ILIKE :q)")
        params["q"] = f"%{q}%"
    if date_from is not None:
        where_clauses.append(f"v.{date_column} >= CAST(:date_from AS timestamptz)")
        params["date_from"] = date_from
    if date_to is not None:
        where_clauses.append(f"v.{date_column} < CAST(:date_to AS timestamptz) + INTERVAL '1 day'")
        params["date_to"] = date_to
    if completed_only:
        where_clauses.append("v.state = 'completed'")
    if category:
        where_clauses.append("v.category ILIKE :category")
        params["category"] = category

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    sql = f"""
        SELECT
            v.id, v.youtube_id, v.title, v.duration_seconds, v.state,
            v.caption_ingest_state, v.diarization_state, v.uploaded_at,
            v.created_at, v.updated_at, v.channel_name, v.language, v.category,
            EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id) AS has_whisper_transcript,
            EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id) AS has_youtube_transcript
        FROM videos v
        {where_sql}
        ORDER BY COALESCE(v.uploaded_at, v.created_at) DESC, v.created_at DESC
        LIMIT :limit OFFSET :offset
    """
    return db.execute(text(sql), params).mappings().all()


@_retry_on_transient_error
def count_videos(
    db,
    q: str | None = None,
    date_field: str = "uploaded_at",
    date_from=None,
    date_to=None,
    completed_only: bool = False,
    category: str | None = None,
):
    date_column = date_field if date_field in {"uploaded_at", "created_at", "updated_at"} else "uploaded_at"
    where_clauses = []
    params = {}
    if q:
        where_clauses.append("(v.title ILIKE :q OR v.youtube_id ILIKE :q OR v.channel_name ILIKE :q)")
        params["q"] = f"%{q}%"
    if date_from is not None:
        where_clauses.append(f"v.{date_column} >= CAST(:date_from AS timestamptz)")
        params["date_from"] = date_from
    if date_to is not None:
        where_clauses.append(f"v.{date_column} < CAST(:date_to AS timestamptz) + INTERVAL '1 day'")
        params["date_to"] = date_to
    if completed_only:
        where_clauses.append("v.state = 'completed'")
    if category:
        where_clauses.append("v.category ILIKE :category")
        params["category"] = category
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    return db.execute(text(f"SELECT count(*) AS count FROM videos v {where_sql}"), params).mappings().first()["count"]


def _video_info_rows_to_models(rows):
    from app.schemas import VideoInfo

    return [VideoInfo(**dict(row)) for row in rows]


@_retry_on_transient_error
def get_videos_by_ids(db, video_ids):
    if not video_ids:
        return []

    sql = text(
        """
        SELECT
            v.id, v.youtube_id, v.title, v.duration_seconds, v.state,
            v.caption_ingest_state, v.diarization_state, v.uploaded_at,
            v.created_at, v.updated_at, v.channel_name, v.language, v.category,
            EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id) AS has_whisper_transcript,
            EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id) AS has_youtube_transcript
        FROM videos v
        WHERE v.id IN :video_ids
        ORDER BY COALESCE(v.uploaded_at, v.created_at) DESC NULLS LAST, v.created_at DESC
        """
    ).bindparams(bindparam("video_ids", expanding=True))
    rows = db.execute(sql, {"video_ids": [str(video_id) for video_id in video_ids]}).mappings().all()
    return _video_info_rows_to_models(rows)


def _archive_video_filter_sql() -> str:
    return """
        EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id)
        OR EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id)
    """


@_retry_on_transient_error
def get_archive_summary(db, recent_limit: int = 6, popular_limit: int = 8):
    from app.schemas import ArchivePopularSearch, ArchiveSummary

    archive_filter = _archive_video_filter_sql()

    stats = db.execute(
        text(
            f"""
            SELECT
                COUNT(*) AS video_count,
                COALESCE(SUM(COALESCE(v.duration_seconds, 0)), 0) AS total_duration_seconds,
                MAX(COALESCE(v.updated_at, v.created_at)) AS updated_at
            FROM videos v
            WHERE {archive_filter}
            """
        )
    ).mappings().first()

    word_stats = db.execute(
        text(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN btrim(s.text) = '' THEN 0 ELSE cardinality(regexp_split_to_array(btrim(s.text), '\\s+')) END), 0) AS native_words
            FROM segments s
            JOIN videos v ON v.id = s.video_id
            WHERE {archive_filter}
            """
        )
    ).scalar_one()

    yt_word_stats = db.execute(
        text(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN btrim(ys.text) = '' THEN 0 ELSE cardinality(regexp_split_to_array(btrim(ys.text), '\\s+')) END), 0) AS youtube_words
            FROM youtube_segments ys
            JOIN youtube_transcripts yt ON yt.id = ys.youtube_transcript_id
            JOIN videos v ON v.id = yt.video_id
            WHERE {archive_filter}
            """
        )
    ).scalar_one()

    recent_videos = [
        video
        for video in _video_info_rows_to_models(
            db.execute(
                text(
                    f"""
                    SELECT
                        v.id, v.youtube_id, v.title, v.duration_seconds, v.state,
                        v.caption_ingest_state, v.diarization_state, v.uploaded_at,
                        v.created_at, v.updated_at, v.channel_name, v.language, v.category,
                        EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id) AS has_whisper_transcript,
                        EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id) AS has_youtube_transcript
                    FROM videos v
                    WHERE v.state = 'completed'
                      AND ({archive_filter})
                    ORDER BY COALESCE(v.uploaded_at, v.created_at) DESC NULLS LAST, v.created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": recent_limit},
            ).mappings().all()
        )
        if video.has_whisper_transcript or video.has_youtube_transcript
    ]

    try:
        popular_rows = (
            db.execute(
                text(
                    """
                    SELECT term, frequency
                    FROM search_suggestions
                    ORDER BY frequency DESC, last_used DESC
                    LIMIT :limit
                    """
                ),
                {"limit": popular_limit},
            )
            .mappings()
            .all()
        )
    except (OperationalError, ProgrammingError):
        db.rollback()
        popular_rows = []

    return ArchiveSummary(
        video_count=int(stats["video_count"] or 0),
        total_duration_seconds=int(stats["total_duration_seconds"] or 0),
        transcript_word_count=int((word_stats or 0) + (yt_word_stats or 0)),
        updated_at=stats["updated_at"],
        recent_videos=recent_videos,
        popular_searches=[ArchivePopularSearch(term=row["term"], frequency=row["frequency"]) for row in popular_rows],
    )


@_retry_on_transient_error
def get_archive_timeline(db, limit: int = 100, granularity: str = "month"):
    from app.schemas import ArchiveTimelineResponse, TimelineBucket

    archive_filter = _archive_video_filter_sql()
    bucket_trunc = "year" if granularity == "year" else "month"

    rows = (
        db.execute(
            text(
                f"""
                SELECT
                    v.id, v.youtube_id, v.title, v.duration_seconds, v.state,
                    v.caption_ingest_state, v.diarization_state, v.uploaded_at,
                    v.created_at, v.updated_at, v.channel_name, v.language, v.category,
                    EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id) AS has_whisper_transcript,
                    EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id) AS has_youtube_transcript,
                    date_trunc('{bucket_trunc}', COALESCE(v.uploaded_at, v.created_at)) AS bucket_start
                FROM videos v
                WHERE ({archive_filter})
                  AND COALESCE(v.uploaded_at, v.created_at) IS NOT NULL
                ORDER BY bucket_start DESC NULLS LAST, COALESCE(v.uploaded_at, v.created_at) DESC NULLS LAST, v.created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        .mappings()
        .all()
    )

    buckets: dict[str, TimelineBucket] = {}
    for row in rows:
        video = _video_info_rows_to_models([row])[0]
        bucket_start = row["bucket_start"]
        if bucket_start is None:
            continue
        if bucket_trunc == "year":
            period = bucket_start.strftime("%Y")
            label = bucket_start.strftime("%Y")
        else:
            period = bucket_start.strftime("%Y-%m")
            label = bucket_start.strftime("%B %Y")

        bucket = buckets.get(period)
        if not bucket:
            bucket = TimelineBucket(period=period, label=label, video_count=0, total_duration_seconds=0, videos=[])
            buckets[period] = bucket
        bucket.video_count += 1
        bucket.total_duration_seconds += int(video.duration_seconds or 0)
        bucket.videos.append(video)

    return ArchiveTimelineResponse(buckets=list(buckets.values()))


def _search_rows_for_grouping(db, q, source, video_id, limit, offset, sort_by, filters):
    if source == "best":
        return search_best_segments_advanced(
            db,
            q=q,
            video_id=video_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            filters=filters,
        )
    if source == "native":
        return search_segments_advanced(
            db,
            q=q,
            video_id=video_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            filters=filters,
        )
    return search_youtube_segments_advanced(
        db,
        q=q,
        video_id=video_id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        filters=filters,
    )


@_retry_on_transient_error
def get_grouped_search(db, q: str, source: str = "best", video_id: str | None = None, limit: int = 50, offset: int = 0, sort_by: str = "relevance", filters: dict | None = None):
    from app.schemas import EpisodeSearchGroup, GroupedSearchResponse, SearchMoment

    filters = filters or {}
    start_time = time.time()
    rows = _search_rows_for_grouping(db, q, source, video_id, limit, offset, sort_by, filters)
    video_ids = []
    for row in rows:
        row_vid = str(row["video_id"])
        if row_vid not in video_ids:
            video_ids.append(row_vid)
    video_map = {str(video.id): video for video in get_videos_by_ids(db, video_ids)}

    groups: dict[str, EpisodeSearchGroup] = {}
    for row in rows:
        vid = str(row["video_id"])
        video = video_map.get(vid)
        if video is None:
            continue
        group = groups.get(vid)
        if group is None:
            group = EpisodeSearchGroup(video=video, moments=[])
            groups[vid] = group
        group.moments.append(
            SearchMoment(
                id=int(row["id"]),
                video_id=video.id,
                start_ms=int(row["start_ms"]),
                end_ms=int(row["end_ms"]),
                snippet=row["snippet"] or "",
                source=row["source"] if "source" in row else ("whisper" if source == "native" else source),
                video_title=video.title,
                channel_name=video.channel_name,
                uploaded_at=video.uploaded_at,
                duration_seconds=video.duration_seconds,
            )
        )

    return GroupedSearchResponse(
        total_moments=len(rows),
        total_videos=len(groups),
        groups=list(groups.values()),
        query_time_ms=int((time.time() - start_time) * 1000),
    )


@_retry_on_transient_error
def get_mention_map(db, q: str, source: str = "best", video_id: str | None = None, limit: int = 50, offset: int = 0, sort_by: str = "relevance", filters: dict | None = None, top_limit: int = 5):
    from app.schemas import MentionMap
    from datetime import datetime, timedelta, timezone
    import re

    grouped = get_grouped_search(db, q=q, source=source, video_id=video_id, limit=limit, offset=offset, sort_by=sort_by, filters=filters)
    moments = [moment for group in grouped.groups for moment in group.moments]

    baseline = datetime.min.replace(tzinfo=timezone.utc)

    def sort_key(moment):
        return (
            moment.uploaded_at or baseline,
            moment.start_ms,
            str(moment.video_id),
        )

    ordered_moments = sorted(moments, key=sort_key)
    first_mention = ordered_moments[0] if ordered_moments else None
    latest_mention = ordered_moments[-1] if ordered_moments else None

    dated_moments = [(moment, moment.uploaded_at) for moment in moments if moment.uploaded_at is not None]
    first_mentioned_year = None
    if first_mention and first_mention.uploaded_at is not None:
        first_mentioned_year = first_mention.uploaded_at.year

    period_counts: dict[str, int] = {}
    for _moment, uploaded_at in dated_moments:
        period = str(uploaded_at.year)
        period_counts[period] = period_counts.get(period, 0) + 1
    most_discussed_period, most_discussed_count = (None, 0)
    if period_counts:
        most_discussed_period, most_discussed_count = sorted(period_counts.items(), key=lambda item: (-item[1], item[0]))[0]

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=90)
    recent_mentions_90d = sum(1 for _moment, uploaded_at in dated_moments if uploaded_at >= cutoff)

    stopwords = {
        "about", "after", "again", "also", "because", "being", "between", "could", "every", "first", "from", "have", "into", "just", "like", "more", "most", "much", "only", "other", "over", "really", "right", "some", "than", "that", "their", "them", "then", "there", "these", "they", "thing", "this", "those", "through", "time", "very", "what", "when", "where", "which", "with", "would", "your"
    }
    query_terms = {term.lower() for term in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", q)}
    term_counts: dict[str, int] = {}
    for moment in moments:
        text_value = re.sub(r"<[^>]+>", " ", moment.snippet or "")
        seen: set[str] = set()
        for raw_term in re.findall(r"[A-Za-z][A-Za-z0-9'-]{3,}", text_value):
            term = raw_term.strip("'-").lower()
            if term in stopwords or term in query_terms or len(term) < 4:
                continue
            seen.add(term)
        for term in seen:
            term_counts[term] = term_counts.get(term, 0) + 1
    related_topics = [term for term, _count in sorted(term_counts.items(), key=lambda item: (-item[1], item[0]))[:5]]

    top_episodes = sorted(
        grouped.groups,
        key=lambda group: (-len(group.moments), group.video.uploaded_at or group.video.created_at or group.video.updated_at or baseline, str(group.video.id)),
    )[:top_limit]

    return MentionMap(
        query=q,
        total_moments=grouped.total_moments,
        total_videos=grouped.total_videos,
        first_mentioned_year=first_mentioned_year,
        most_discussed_period=most_discussed_period,
        most_discussed_count=most_discussed_count,
        recent_mentions_90d=recent_mentions_90d,
        related_topics=related_topics,
        top_episodes_count=len(top_episodes),
        first_mention=first_mention,
        latest_mention=latest_mention,
        top_episodes=top_episodes,
        query_time_ms=grouped.query_time_ms,
    )


@_retry_on_transient_error
def list_saved_searches(db, user_id):
    from app.schemas import SavedSearch, SavedSearchesResponse

    rows = (
        db.execute(
            text(
                """
                SELECT id, query, filters, created_at
                FROM saved_searches
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                """
            ),
            {"user_id": str(user_id)},
        )
        .mappings()
        .all()
    )
    return SavedSearchesResponse(
        items=[SavedSearch(id=row["id"], query=row["query"], filters=row["filters"] or {}, created_at=row["created_at"]) for row in rows]
    )


@_retry_on_transient_error
def create_saved_search(db, user_id, query: str, filters: dict | None = None):
    from app.schemas import SavedSearch

    payload = filters or {}
    row = (
        db.execute(
            text(
                """
                INSERT INTO saved_searches (id, user_id, query, filters)
                VALUES (:id, :user_id, :query, :filters)
                ON CONFLICT (user_id, query)
                DO UPDATE SET filters = EXCLUDED.filters,
                              created_at = now()
                RETURNING id, query, filters, created_at
                """
            ),
            {"id": str(uuid.uuid4()), "user_id": str(user_id), "query": query.strip(), "filters": json.dumps(payload)},
        )
        .mappings()
        .first()
    )
    db.commit()
    return SavedSearch(id=row["id"], query=row["query"], filters=row["filters"] or {}, created_at=row["created_at"])


@_retry_on_transient_error
def delete_saved_search(db, user_id, saved_search_id):
    result = db.execute(
        text("DELETE FROM saved_searches WHERE id = :id AND user_id = :user_id"),
        {"id": str(saved_search_id), "user_id": str(user_id)},
    )
    db.commit()
    return result.rowcount > 0


@_retry_on_transient_error
def list_completed_videos(db, limit: int = 12, offset: int = 0):
    return (
        db.execute(
            text(
                """
            SELECT v.id, v.youtube_id, v.title, v.duration_seconds
            FROM videos v
            WHERE v.state = 'completed'
              AND EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id)
            ORDER BY v.updated_at DESC, v.created_at DESC
            LIMIT :limit OFFSET :offset
        """
            ),
            {"limit": limit, "offset": offset},
        )
        .mappings()
        .all()
    )


@_retry_on_transient_error
def get_youtube_transcript(db, video_id):
    return (
        db.execute(
            text("SELECT id, language, kind, full_text FROM youtube_transcripts WHERE video_id=:v"),
            {"v": str(video_id)},
        )
        .mappings()
        .first()
    )


@_retry_on_transient_error
def list_youtube_segments(db, youtube_transcript_id):
    return db.execute(
        text("SELECT start_ms,end_ms,text FROM youtube_segments WHERE youtube_transcript_id=:t ORDER BY start_ms"),
        {"t": str(youtube_transcript_id)},
    ).all()


@_retry_on_transient_error
def replace_transcript_blocks(conn, video_id, blocks):
    conn.execute(text("DELETE FROM transcript_blocks WHERE video_id = :v"), {"v": str(video_id)})
    for block in blocks:
        conn.execute(
            text(
                """
                INSERT INTO transcript_blocks (
                    video_id, block_index, start_ms, end_ms, speaker_label,
                    text, segment_ids, kind, formatter_version
                )
                VALUES (
                    :video_id, :block_index, :start_ms, :end_ms, :speaker_label,
                    :text, :segment_ids, :kind, :formatter_version
                )
                """
            ),
            {
                "video_id": str(video_id),
                "block_index": block.block_index,
                "start_ms": block.start_ms,
                "end_ms": block.end_ms,
                "speaker_label": block.speaker_label,
                "text": block.text,
                "segment_ids": json.dumps(block.segment_ids),
                "kind": block.kind,
                "formatter_version": block.formatter_version,
            },
        )


@_retry_on_transient_error
def list_transcript_blocks(db, video_id):
    try:
        return (
            db.execute(
                text(
                    """
                    SELECT block_index, start_ms, end_ms, speaker_label, text,
                           segment_ids, kind, formatter_version
                    FROM transcript_blocks
                    WHERE video_id = :v
                    ORDER BY block_index
                    """
                ),
                {"v": str(video_id)},
            )
            .mappings()
            .all()
        )
    except (OperationalError, ProgrammingError) as exc:
        if "transcript_blocks" in str(exc).lower():
            logger.warning(
                "transcript_blocks table is unavailable; falling back to derived formatted blocks",
                extra={"video_id": str(video_id), "error": str(exc)},
            )
            db.rollback()
            return []
        raise


@_retry_on_transient_error
def search_segments(db, q: str, video_id: str | None = None, limit: int = 50, offset: int = 0):
    from app.metrics import search_queries_total

    sql = """
        SELECT id, video_id, start_ms, end_ms,
               ts_headline('english', text, websearch_to_tsquery('english', :q)) AS snippet,
               ts_rank_cd(text_tsv, websearch_to_tsquery('english', :q)) AS rank
        FROM segments
        WHERE text_tsv @@ websearch_to_tsquery('english', :q)
        {video_filter}
        ORDER BY rank DESC, start_ms ASC
        LIMIT :limit OFFSET :offset
    """
    video_filter = ""
    params = {"q": q, "limit": limit, "offset": offset}
    if video_id:
        video_filter = "AND video_id = :vid"
        params["vid"] = str(video_id)
    rows = db.execute(text(sql.format(video_filter=video_filter)), params).mappings().all()

    # Track search query metric
    search_queries_total.labels(backend="postgres").inc()

    return rows


@_retry_on_transient_error
def search_youtube_segments(db, q: str, video_id: str | None = None, limit: int = 50, offset: int = 0):
    sql = """
        SELECT ys.id, yt.video_id, ys.start_ms, ys.end_ms,
               ts_headline('english', ys.text, websearch_to_tsquery('english', :q)) AS snippet,
               ts_rank_cd(ys.text_tsv, websearch_to_tsquery('english', :q)) AS rank
        FROM youtube_segments ys
        JOIN youtube_transcripts yt ON yt.id = ys.youtube_transcript_id
        WHERE ys.text_tsv @@ websearch_to_tsquery('english', :q)
        {video_filter}
        ORDER BY rank DESC, ys.start_ms ASC
        LIMIT :limit OFFSET :offset
    """
    video_filter = ""
    params = {"q": q, "limit": limit, "offset": offset}
    if video_id:
        video_filter = "AND yt.video_id = :vid"
        params["vid"] = str(video_id)
    rows = db.execute(text(sql.format(video_filter=video_filter)), params).mappings().all()
    return rows


@_retry_on_transient_error
def search_segments_advanced(
    db,
    q: str,
    video_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "relevance",
    filters: dict | None = None,
):
    """Search segments with advanced filters and sorting."""
    from app.metrics import search_queries_total

    filters = filters or {}

    # Build WHERE clause with filters. Search transcript text and video title so
    # users can find newly processed videos by title from the main search box.
    where_clauses = ["(s.text_tsv @@ websearch_to_tsquery('english', :q) OR v.title ILIKE :title_q)"]
    params = {"q": q, "limit": limit, "offset": offset}
    params["title_q"] = f"%{q.strip()}%"

    if video_id:
        where_clauses.append("s.video_id = :vid")
        params["vid"] = str(video_id)

    # Join with videos table for title search, sorting, and filter support.
    needs_video_join = True

    if needs_video_join:
        if filters.get("date_from"):
            where_clauses.append("v.uploaded_at >= :date_from")
            params["date_from"] = filters["date_from"]
        if filters.get("date_to"):
            where_clauses.append("v.uploaded_at <= :date_to")
            params["date_to"] = filters["date_to"]
        if filters.get("min_duration") is not None:
            where_clauses.append("v.duration_seconds >= :min_duration")
            params["min_duration"] = filters["min_duration"]
        if filters.get("max_duration") is not None:
            where_clauses.append("v.duration_seconds <= :max_duration")
            params["max_duration"] = filters["max_duration"]
        if filters.get("category"):
            where_clauses.append("v.category ILIKE :category")
            params["category"] = filters["category"]
        if filters.get("channel"):
            where_clauses.append("v.channel_name ILIKE :channel")
            params["channel"] = f"%{filters['channel']}%"
        if filters.get("language"):
            where_clauses.append("v.language = :language")
            params["language"] = filters["language"]

    # Speaker labels filter
    if filters.get("has_speaker_labels") is not None:
        if filters["has_speaker_labels"]:
            where_clauses.append("s.speaker_label IS NOT NULL")
        else:
            where_clauses.append("s.speaker_label IS NULL")

    # Build ORDER BY clause
    if sort_by == "date_desc":
        order_by = "v.uploaded_at DESC NULLS LAST, s.start_ms ASC"
    elif sort_by == "date_asc":
        order_by = "v.uploaded_at ASC NULLS LAST, s.start_ms ASC"
    elif sort_by == "duration_desc":
        order_by = "v.duration_seconds DESC NULLS LAST, s.start_ms ASC"
    elif sort_by == "duration_asc":
        order_by = "v.duration_seconds ASC NULLS LAST, s.start_ms ASC"
    else:  # relevance (default)
        order_by = "rank DESC, title_match DESC, s.start_ms ASC"

    # Build query
    from_clause = "segments s"
    select_fields = (
        "s.id, s.video_id, s.start_ms, s.end_ms, "
        "CASE WHEN s.text_tsv @@ websearch_to_tsquery('english', :q) "
        "THEN ts_headline('english', s.text, websearch_to_tsquery('english', :q)) "
        "ELSE coalesce(v.title, s.text) END AS snippet, "
        "ts_rank_cd(s.text_tsv, websearch_to_tsquery('english', :q)) AS rank, "
        "CASE WHEN v.title ILIKE :title_q THEN 1 ELSE 0 END AS title_match"
    )

    if needs_video_join:
        from_clause = "segments s JOIN videos v ON s.video_id = v.id"

    sql = f"""
        SELECT {select_fields}
        FROM {from_clause}
        WHERE {' AND '.join(where_clauses)}
        ORDER BY {order_by}
        LIMIT :limit OFFSET :offset
    """

    rows = db.execute(text(sql), params).mappings().all()

    # Track search query metric
    search_queries_total.labels(backend="postgres").inc()

    return rows


@_retry_on_transient_error
def search_youtube_segments_advanced(
    db,
    q: str,
    video_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "relevance",
    filters: dict | None = None,
):
    """Search YouTube segments with advanced filters and sorting."""
    filters = filters or {}

    # Keep transcript text search separate from title/youtube_id metadata search.
    # Applying a title match directly to every youtube_segments row makes title
    # searches scan/return every caption segment for matching videos.
    text_where = ["ys.text_tsv @@ websearch_to_tsquery('english', :q)"]
    title_where = ["(v.title ILIKE :title_q OR v.youtube_id ILIKE :title_q)"]
    params = {"q": q, "limit": limit, "offset": offset, "title_q": f"%{q.strip()}%"}

    if video_id:
        text_where.append("yt.video_id = :vid")
        title_where.append("yt.video_id = :vid")
        params["vid"] = str(video_id)

    # Join with videos table for filter support
    needs_video_join = True

    if needs_video_join:
        if filters.get("date_from"):
            text_where.append("v.uploaded_at >= :date_from")
            title_where.append("v.uploaded_at >= :date_from")
            params["date_from"] = filters["date_from"]
        if filters.get("date_to"):
            text_where.append("v.uploaded_at <= :date_to")
            title_where.append("v.uploaded_at <= :date_to")
            params["date_to"] = filters["date_to"]
        if filters.get("min_duration") is not None:
            text_where.append("v.duration_seconds >= :min_duration")
            title_where.append("v.duration_seconds >= :min_duration")
            params["min_duration"] = filters["min_duration"]
        if filters.get("max_duration") is not None:
            text_where.append("v.duration_seconds <= :max_duration")
            title_where.append("v.duration_seconds <= :max_duration")
            params["max_duration"] = filters["max_duration"]
        if filters.get("category"):
            text_where.append("v.category ILIKE :category")
            title_where.append("v.category ILIKE :category")
            params["category"] = filters["category"]
        if filters.get("channel"):
            text_where.append("v.channel_name ILIKE :channel")
            title_where.append("v.channel_name ILIKE :channel")
            params["channel"] = f"%{filters['channel']}%"
        if filters.get("language"):
            text_where.append("v.language = :language")
            title_where.append("v.language = :language")
            params["language"] = filters["language"]

    # Build ORDER BY clause
    if sort_by == "date_desc":
        order_by = "uploaded_at DESC NULLS LAST, start_ms ASC"
    elif sort_by == "date_asc":
        order_by = "uploaded_at ASC NULLS LAST, start_ms ASC"
    elif sort_by == "duration_desc":
        order_by = "duration_seconds DESC NULLS LAST, start_ms ASC"
    elif sort_by == "duration_asc":
        order_by = "duration_seconds ASC NULLS LAST, start_ms ASC"
    else:  # relevance (default)
        order_by = "title_match DESC, rank DESC, start_ms ASC"

    sql = f"""
        WITH text_hits AS (
            SELECT
                ys.id,
                yt.video_id,
                ys.start_ms,
                ys.end_ms,
                ts_headline('english', ys.text, websearch_to_tsquery('english', :q)) AS snippet,
                ts_rank_cd(ys.text_tsv, websearch_to_tsquery('english', :q)) AS rank,
                0 AS title_match,
                v.uploaded_at,
                v.duration_seconds
            FROM youtube_segments ys
            JOIN youtube_transcripts yt ON yt.id = ys.youtube_transcript_id
            JOIN videos v ON yt.video_id = v.id
            WHERE {' AND '.join(text_where)}
        ), title_hits AS (
            SELECT DISTINCT ON (yt.video_id)
                ys.id,
                yt.video_id,
                ys.start_ms,
                ys.end_ms,
                coalesce(v.title, ys.text) AS snippet,
                0.0 AS rank,
                1 AS title_match,
                v.uploaded_at,
                v.duration_seconds
            FROM youtube_transcripts yt
            JOIN videos v ON yt.video_id = v.id
            JOIN youtube_segments ys ON ys.youtube_transcript_id = yt.id
            WHERE {' AND '.join(title_where)}
            ORDER BY yt.video_id, ys.start_ms ASC
        )
        SELECT id, video_id, start_ms, end_ms, snippet, rank, title_match
        FROM (
            SELECT * FROM text_hits
            UNION ALL
            SELECT * FROM title_hits
        ) youtube_hits
        ORDER BY {order_by}
        LIMIT :limit OFFSET :offset
    """

    rows = db.execute(text(sql), params).mappings().all()
    return rows


@_retry_on_transient_error
def search_best_segments_advanced(
    db,
    q: str,
    video_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "relevance",
    filters: dict | None = None,
):
    """Search the best available transcript source per video.

    Policy: use Whisper/native segments when a video has them; otherwise use
    YouTube caption segments. This lets caption-only videos appear in default
    search without duplicating videos that already have Whisper transcripts.
    """
    from app.metrics import search_queries_total

    filters = filters or {}
    params = {"q": q, "limit": limit, "offset": offset, "title_q": f"%{q.strip()}%"}
    native_where = ["(s.text_tsv @@ websearch_to_tsquery('english', :q) OR v.title ILIKE :title_q)"]
    youtube_where = ["ys.text_tsv @@ websearch_to_tsquery('english', :q)"]
    youtube_title_where = ["(v.title ILIKE :title_q OR v.youtube_id ILIKE :title_q)"]

    if video_id:
        native_where.append("s.video_id = :vid")
        youtube_where.append("yt.video_id = :vid")
        youtube_title_where.append("yt.video_id = :vid")
        params["vid"] = str(video_id)

    if filters.get("date_from"):
        native_where.append("v.uploaded_at >= :date_from")
        youtube_where.append("v.uploaded_at >= :date_from")
        youtube_title_where.append("v.uploaded_at >= :date_from")
        params["date_from"] = filters["date_from"]
    if filters.get("date_to"):
        native_where.append("v.uploaded_at <= :date_to")
        youtube_where.append("v.uploaded_at <= :date_to")
        youtube_title_where.append("v.uploaded_at <= :date_to")
        params["date_to"] = filters["date_to"]
    if filters.get("min_duration") is not None:
        native_where.append("v.duration_seconds >= :min_duration")
        youtube_where.append("v.duration_seconds >= :min_duration")
        youtube_title_where.append("v.duration_seconds >= :min_duration")
        params["min_duration"] = filters["min_duration"]
    if filters.get("max_duration") is not None:
        native_where.append("v.duration_seconds <= :max_duration")
        youtube_where.append("v.duration_seconds <= :max_duration")
        youtube_title_where.append("v.duration_seconds <= :max_duration")
        params["max_duration"] = filters["max_duration"]
    if filters.get("channel"):
        native_where.append("v.channel_name ILIKE :channel")
        youtube_where.append("v.channel_name ILIKE :channel")
        youtube_title_where.append("v.channel_name ILIKE :channel")
        params["channel"] = f"%{filters['channel']}%"
    if filters.get("category"):
        native_where.append("v.category ILIKE :category")
        youtube_where.append("v.category ILIKE :category")
        youtube_title_where.append("v.category ILIKE :category")
        params["category"] = filters["category"]
    if filters.get("language"):
        native_where.append("v.language = :language")
        youtube_where.append("v.language = :language")
        youtube_title_where.append("v.language = :language")
        params["language"] = filters["language"]
    if filters.get("has_speaker_labels") is not None:
        if filters["has_speaker_labels"]:
            native_where.append("s.speaker_label IS NOT NULL")
            youtube_where.append("FALSE")
        else:
            native_where.append("s.speaker_label IS NULL")

    youtube_where.append("NOT EXISTS (SELECT 1 FROM segments native_s WHERE native_s.video_id = yt.video_id)")
    youtube_title_where.append("NOT EXISTS (SELECT 1 FROM segments native_s WHERE native_s.video_id = yt.video_id)")

    if sort_by == "date_desc":
        order_by = "uploaded_at DESC NULLS LAST, start_ms ASC"
    elif sort_by == "date_asc":
        order_by = "uploaded_at ASC NULLS LAST, start_ms ASC"
    elif sort_by == "duration_desc":
        order_by = "duration_seconds DESC NULLS LAST, start_ms ASC"
    elif sort_by == "duration_asc":
        order_by = "duration_seconds ASC NULLS LAST, start_ms ASC"
    else:
        order_by = "rank DESC, title_match DESC, start_ms ASC"

    sql = f"""
        SELECT id, video_id, start_ms, end_ms, snippet, source, rank, title_match,
               uploaded_at, duration_seconds
        FROM (
            SELECT
                s.id,
                s.video_id,
                s.start_ms,
                s.end_ms,
                CASE WHEN s.text_tsv @@ websearch_to_tsquery('english', :q)
                    THEN ts_headline('english', s.text, websearch_to_tsquery('english', :q))
                    ELSE coalesce(v.title, s.text)
                END AS snippet,
                'whisper' AS source,
                ts_rank_cd(s.text_tsv, websearch_to_tsquery('english', :q)) AS rank,
                CASE WHEN v.title ILIKE :title_q THEN 1 ELSE 0 END AS title_match,
                v.uploaded_at,
                v.duration_seconds
            FROM segments s
            JOIN videos v ON s.video_id = v.id
            WHERE {' AND '.join(native_where)}

            UNION ALL

            SELECT
                ys.id,
                yt.video_id,
                ys.start_ms,
                ys.end_ms,
                CASE WHEN ys.text_tsv @@ websearch_to_tsquery('english', :q)
                    THEN ts_headline('english', ys.text, websearch_to_tsquery('english', :q))
                    ELSE coalesce(v.title, ys.text)
                END AS snippet,
                'youtube' AS source,
                ts_rank_cd(ys.text_tsv, websearch_to_tsquery('english', :q)) AS rank,
                CASE WHEN v.title ILIKE :title_q OR v.youtube_id ILIKE :title_q THEN 1 ELSE 0 END AS title_match,
                v.uploaded_at,
                v.duration_seconds
            FROM youtube_segments ys
            JOIN youtube_transcripts yt ON yt.id = ys.youtube_transcript_id
            JOIN videos v ON yt.video_id = v.id
            WHERE {' AND '.join(youtube_where)}

            UNION ALL

            SELECT DISTINCT ON (yt.video_id)
                ys.id,
                yt.video_id,
                ys.start_ms,
                ys.end_ms,
                coalesce(v.title, ys.text) AS snippet,
                'youtube' AS source,
                0.0 AS rank,
                1 AS title_match,
                v.uploaded_at,
                v.duration_seconds
            FROM youtube_transcripts yt
            JOIN videos v ON yt.video_id = v.id
            JOIN youtube_segments ys ON ys.youtube_transcript_id = yt.id
            WHERE {' AND '.join(youtube_title_where)}
            ORDER BY video_id, start_ms ASC
        ) best_hits
        ORDER BY {order_by}
        LIMIT :limit OFFSET :offset
    """
    rows = db.execute(text(sql), params).mappings().all()
    search_queries_total.labels(backend="postgres").inc()
    return rows
