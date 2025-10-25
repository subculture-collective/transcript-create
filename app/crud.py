import functools
import logging
import time
import uuid

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

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
                            "Database transient error on attempt %d/%d: %s. Retrying in %.2fs...",
                            attempt + 1,
                            MAX_RETRIES,
                            str(e),
                            delay,
                        )
                        time.sleep(delay)
                        continue
                # Not a transient error or max retries reached
                logger.error("Database error after %d attempts: %s", attempt + 1, str(e))
                raise
            except Exception:
                # For non-transient errors, raise immediately
                raise
        # Should not reach here, but just in case
        if last_error:
            raise last_error

    return wrapper


@_retry_on_transient_error
def create_job(db, kind: str, url: str):
    job_id = uuid.uuid4()
    db.execute(
        text("INSERT INTO jobs (id, kind, input_url) VALUES (:i,:k,:u)"), {"i": str(job_id), "k": kind, "u": url}
    )
    db.commit()
    return job_id


@_retry_on_transient_error
def fetch_job(db, job_id):
    row = db.execute(text("SELECT * FROM jobs WHERE id=:i"), {"i": str(job_id)}).mappings().first()
    return row


@_retry_on_transient_error
def list_segments(db, video_id):
    rows = db.execute(
        text("SELECT start_ms,end_ms,text,speaker_label FROM segments WHERE video_id=:v ORDER BY start_ms"),
        {"v": str(video_id)},
    ).all()
    return rows


@_retry_on_transient_error
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
