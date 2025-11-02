import functools
import time
import uuid

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.cache import cache
from app.logging_config import get_logger
from app.settings import settings

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
def create_job(db, kind: str, url: str, meta: dict = None):
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
        db.execute(text("SELECT id, youtube_id, title, duration_seconds FROM videos WHERE id=:v"), {"v": str(video_id)})
        .mappings()
        .first()
    )


@_retry_on_transient_error
def list_videos(db, limit: int = 50, offset: int = 0):
    return (
        db.execute(
            text(
                """
            SELECT id, youtube_id, title, duration_seconds
            FROM videos
            ORDER BY created_at DESC
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

    # Build WHERE clause with filters
    where_clauses = ["text_tsv @@ websearch_to_tsquery('english', :q)"]
    params = {"q": q, "limit": limit, "offset": offset}

    if video_id:
        where_clauses.append("s.video_id = :vid")
        params["vid"] = str(video_id)

    # Join with videos table for filter support
    needs_video_join = any(
        k in filters for k in ["date_from", "date_to", "min_duration", "max_duration", "channel", "language"]
    )

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
        order_by = "rank DESC, s.start_ms ASC"

    # Build query
    from_clause = "segments s"
    select_fields = (
        "s.id, s.video_id, s.start_ms, s.end_ms, "
        "ts_headline('english', s.text, websearch_to_tsquery('english', :q)) AS snippet, "
        "ts_rank_cd(s.text_tsv, websearch_to_tsquery('english', :q)) AS rank"
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

    # Build WHERE clause with filters
    where_clauses = ["ys.text_tsv @@ websearch_to_tsquery('english', :q)"]
    params = {"q": q, "limit": limit, "offset": offset}

    if video_id:
        where_clauses.append("yt.video_id = :vid")
        params["vid"] = str(video_id)

    # Join with videos table for filter support
    needs_video_join = any(
        k in filters for k in ["date_from", "date_to", "min_duration", "max_duration", "channel", "language"]
    )

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
        if filters.get("channel"):
            where_clauses.append("v.channel_name ILIKE :channel")
            params["channel"] = f"%{filters['channel']}%"
        if filters.get("language"):
            where_clauses.append("v.language = :language")
            params["language"] = filters["language"]

    # Build ORDER BY clause
    if sort_by == "date_desc":
        order_by = "v.uploaded_at DESC NULLS LAST, ys.start_ms ASC"
    elif sort_by == "date_asc":
        order_by = "v.uploaded_at ASC NULLS LAST, ys.start_ms ASC"
    elif sort_by == "duration_desc":
        order_by = "v.duration_seconds DESC NULLS LAST, ys.start_ms ASC"
    elif sort_by == "duration_asc":
        order_by = "v.duration_seconds ASC NULLS LAST, ys.start_ms ASC"
    else:  # relevance (default)
        order_by = "rank DESC, ys.start_ms ASC"

    # Build query
    from_clause = "youtube_segments ys JOIN youtube_transcripts yt ON yt.id = ys.youtube_transcript_id"
    select_fields = (
        "ys.id, yt.video_id, ys.start_ms, ys.end_ms, "
        "ts_headline('english', ys.text, websearch_to_tsquery('english', :q)) AS snippet, "
        "ts_rank_cd(ys.text_tsv, websearch_to_tsquery('english', :q)) AS rank"
    )

    if needs_video_join:
        from_clause += " JOIN videos v ON yt.video_id = v.id"

    sql = f"""
        SELECT {select_fields}
        FROM {from_clause}
        WHERE {' AND '.join(where_clauses)}
        ORDER BY {order_by}
        LIMIT :limit OFFSET :offset
    """

    rows = db.execute(text(sql), params).mappings().all()
    return rows
