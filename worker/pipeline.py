from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app import crud
from app.logging_config import get_logger
from app.settings import settings
from app.transcripts.blocks import build_transcript_blocks
from app.transcripts.types import TranscriptSegment
from worker.audio import chunk_audio, download_audio, ensure_wav_16k
from worker.caption_ingest import ingest_captions_for_unprocessed_videos
from worker.diarize import diarize_and_align
from worker.native_pipeline import NativePipelineDependencies, process_video as process_native_video
from worker.state_model import ACTIVE_VIDEO_STATES, OPEN_CAPTION_INGEST_STATES, TERMINAL_VIDEO_STATES, sql_string_list
from worker.whisper_runner import transcribe_chunk
from worker.youtube.service import get_youtube_service

WORKDIR = Path("/data")  # mount volume externally

logger = get_logger(__name__)

ACTIVE_VIDEO_STATES_SQL = sql_string_list(ACTIVE_VIDEO_STATES)
OPEN_CAPTION_INGEST_STATES_SQL = sql_string_list(OPEN_CAPTION_INGEST_STATES)
TERMINAL_VIDEO_STATES_SQL = sql_string_list(TERMINAL_VIDEO_STATES)


def _parse_youtube_upload_date(value: Any) -> datetime | None:
    """Parse yt-dlp's source upload date into an aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    raw = str(value).strip()
    if not raw:
        return None

    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _clean_channel_title(value: Any) -> str | None:
    if not value:
        return None
    title = str(value).strip()
    if title.endswith(" - Videos"):
        title = title[: -len(" - Videos")].strip()
    return title or None


def _metadata_channel_name(metadata: dict[str, Any], fallback: str | None = None) -> str | None:
    return _clean_channel_title(
        metadata.get("uploader")
        or metadata.get("channel")
        or metadata.get("channel_name")
        or metadata.get("uploader_id")
        or fallback
    )


def _metadata_uploaded_at(metadata: dict[str, Any]) -> datetime | None:
    upload_date = _parse_youtube_upload_date(metadata.get("upload_date"))
    if upload_date:
        return upload_date
    timestamp = metadata.get("timestamp") or metadata.get("release_timestamp")
    if timestamp is not None:
        try:
            return datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
    return _parse_youtube_upload_date(metadata.get("release_date"))


def refresh_job_state(conn, job_id, *, error: str | None = None) -> None:
    """Update a parent job based on child video terminal states."""
    counts = conn.execute(
        text(
            f"""
            SELECT
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE state = 'completed') AS completed,
              COUNT(*) FILTER (WHERE state = 'failed') AS failed,
              COUNT(*) FILTER (WHERE state IN ({ACTIVE_VIDEO_STATES_SQL})) AS active
            FROM videos
            WHERE job_id = :j
            """
        ),
        {"j": job_id},
    ).mappings().first()

    if not counts or int(counts["total"] or 0) == 0:
        return

    total = int(counts["total"] or 0)
    completed = int(counts["completed"] or 0)
    failed = int(counts["failed"] or 0)
    active = int(counts["active"] or 0)

    if total == completed:
        logger.info("Marking job completed", extra={"job_id": str(job_id), "videos_completed": completed})
        conn.execute(text("UPDATE jobs SET state='completed', error=NULL, updated_at=now() WHERE id=:j"), {"j": job_id})
    elif active == 0 and failed > 0:
        msg = error or f"{failed} of {total} videos failed"
        logger.warning(
            "Marking job failed",
            extra={"job_id": str(job_id), "videos_completed": completed, "videos_failed": failed},
        )
        conn.execute(
            text("UPDATE jobs SET state='failed', error=:e, updated_at=now() WHERE id=:j"),
            {"j": job_id, "e": msg[:5000]},
        )


def reconcile_terminal_jobs(conn) -> None:
    """Repair parent jobs whose child videos have already reached terminal states."""
    completed = conn.execute(
        text(
            f"""
            UPDATE jobs j
            SET state='completed', error=NULL, updated_at=now()
            WHERE j.state NOT IN ({TERMINAL_VIDEO_STATES_SQL})
              AND EXISTS (SELECT 1 FROM videos v WHERE v.job_id = j.id)
              AND NOT EXISTS (
                SELECT 1 FROM videos v
                WHERE v.job_id = j.id AND v.state <> 'completed'
              )
            RETURNING j.id
            """
        ),
    ).fetchall()
    if completed:
        logger.info("Reconciled completed jobs", extra={"count": len(completed)})

    failed = conn.execute(
        text(
            f"""
            UPDATE jobs j
            SET state='failed',
                error=COALESCE(j.error, 'One or more videos failed'),
                updated_at=now()
            WHERE j.state NOT IN ({TERMINAL_VIDEO_STATES_SQL})
              AND EXISTS (SELECT 1 FROM videos v WHERE v.job_id = j.id AND v.state = 'failed')
              AND NOT EXISTS (
                SELECT 1 FROM videos v
                WHERE v.job_id = j.id AND v.state IN ({ACTIVE_VIDEO_STATES_SQL})
              )
            RETURNING j.id
            """
        ),
    ).fetchall()
    if failed:
        logger.info("Reconciled failed jobs", extra={"count": len(failed)})


def _fetch_ytdlp_metadata(url: str, *, flat_playlist: bool = False) -> dict[str, Any]:
    """Compatibility wrapper around the YouTube Adapter metadata seam."""
    return get_youtube_service().fetch_metadata(url, flat_playlist=flat_playlist)


def normalize_channel_url(url: str) -> str:
    """
    Normalize a YouTube channel URL to ensure it includes /videos suffix.

    This ensures we get all videos from the channel rather than a truncated list.
    Works with channel IDs and handles (@username).

    Args:
        url: Input YouTube channel URL

    Returns:
        Normalized URL with /videos suffix

    Examples:
        https://youtube.com/channel/UCtest -> https://youtube.com/channel/UCtest/videos
        https://youtube.com/@user -> https://youtube.com/@user/videos
        https://youtube.com/channel/UCtest/videos -> https://youtube.com/channel/UCtest/videos (unchanged)
    """
    url = url.rstrip("/")

    # Check if already has /videos suffix
    if url.endswith("/videos"):
        return url

    # Append /videos to channel URLs and handle (@username) URLs
    # Match patterns like youtube.com/channel/UCxxx or youtube.com/@username
    # Using simple string matching is sufficient for YouTube URLs
    if "youtube.com/channel/" in url or "youtube.com/@" in url:
        return f"{url}/videos"

    return url


def expand_channel_if_needed(conn):
    from worker.metrics import youtube_requests_total
    from worker.youtube_resilience import classify_error, get_circuit_breaker, retry_with_backoff

    logger.debug("Checking for pending channel jobs to expand")
    jobs = (
        conn.execute(
            text(
                """
        SELECT j.id, j.input_url, j.meta
        FROM jobs j
        WHERE j.kind='channel'
          AND j.state IN ('pending','downloading')
          AND NOT EXISTS (
              SELECT 1 FROM videos v WHERE v.job_id = j.id
          )
        FOR UPDATE SKIP LOCKED
        LIMIT 5
    """
            )
        )
        .mappings()
        .all()
    )

    # Get circuit breaker for metadata operations
    circuit_breaker = None
    if settings.YTDLP_CIRCUIT_BREAKER_ENABLED:
        circuit_breaker = get_circuit_breaker("youtube_metadata")

    for job in jobs:
        url = job["input_url"]
        # Normalize channel URL to ensure /videos suffix for complete enumeration
        normalized_url = normalize_channel_url(url)

        logger.info(
            "Expanding channel job",
            extra={
                "job_id": str(job["id"]),
                "original_url": url,
                "normalized_url": normalized_url,
                "url_modified": url != normalized_url,
            }
        )

        # Use factory function to capture loop variable correctly for retry closure
        def make_fetch_channel_metadata(channel_url: str):
            """Create channel metadata fetch function with explicit parameter binding."""
            def fetch_channel_metadata():
                """Fetch channel metadata with timeout."""
                return _fetch_ytdlp_metadata(channel_url, flat_playlist=True)
            return fetch_channel_metadata  # noqa: B023 (false positive - function returned immediately)

        fetch_channel_metadata = make_fetch_channel_metadata(normalized_url)

        def classify_channel_error(e: Exception):
            """Classify channel expansion error."""
            stderr = getattr(e, "stderr", b"")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="ignore")
            returncode = getattr(e, "returncode", 0)
            return classify_error(returncode, stderr or str(e), e)

        try:
            # Use retry with backoff for channel expansion
            data = retry_with_backoff(
                fetch_channel_metadata,
                max_attempts=settings.YTDLP_MAX_RETRY_ATTEMPTS,
                base_delay=settings.YTDLP_BACKOFF_BASE_DELAY,
                max_delay=settings.YTDLP_BACKOFF_MAX_DELAY,
                circuit_breaker=circuit_breaker,
                classify_func=classify_channel_error,
            )

            entries = data.get("entries", [])
            entry_count = len(entries)
            raw_meta = job.get("meta") or {}
            try:
                job_meta = raw_meta if isinstance(raw_meta, dict) else json.loads(raw_meta)
            except (TypeError, ValueError):
                logger.warning("Unable to parse job metadata for channel cap", extra={"job_id": str(job["id"])})
                job_meta = {}
            max_channel_videos = int(job_meta.get("max_channel_videos") or settings.JOB_CREATE_MAX_CHANNEL_VIDEOS or 0)

            if max_channel_videos > 0 and entry_count > max_channel_videos:
                error_message = (
                    f"Channel expansion found {entry_count} videos, exceeding configured cap "
                    f"of {max_channel_videos}."
                )
                logger.warning(
                    "Channel expansion exceeds configured cap",
                    extra={
                        "job_id": str(job["id"]),
                        "entry_count": entry_count,
                        "max_channel_videos": max_channel_videos,
                    },
                )
                conn.execute(
                    text("UPDATE jobs SET state='failed', error=:e, updated_at=now() WHERE id=:i"),
                    {"i": job["id"], "e": error_message[:5000]},
                )
                youtube_requests_total.labels(operation="channel_expansion", result="failure").inc()
                continue

            # Extract channel ID for logging (None if not available)
            channel_id = data.get("channel_id") or data.get("uploader_id")
            channel_name = _metadata_channel_name(data, data.get("title"))

            logger.info(
                "Channel expansion found entries",
                extra={
                    "job_id": str(job["id"]),
                    "channel_id": channel_id,
                    "entry_count": entry_count,
                    "url": normalized_url,
                }
            )

            for idx, e in enumerate(entries):
                yid = e["id"]
                # Extract metadata for each channel video
                title = e.get("title", "")
                duration = e.get("duration")  # duration in seconds
                video_channel_name = _metadata_channel_name(e, channel_name)
                uploaded_at = _metadata_uploaded_at(e)
                conn.execute(
                    text(
                        """
                    INSERT INTO videos (job_id, youtube_id, idx, title, duration_seconds, uploaded_at, channel_name)
                    VALUES (:j,:y,:idx,:title,:dur,:uploaded_at,:channel_name)
                    ON CONFLICT (job_id, youtube_id) DO NOTHING
                """
                    ),
                    {
                        "j": job["id"],
                        "y": yid,
                        "idx": idx,
                        "title": title,
                        "dur": duration,
                        "uploaded_at": uploaded_at,
                        "channel_name": video_channel_name,
                    },
                )

            logger.info(
                "Channel expansion complete",
                extra={
                    "job_id": str(job["id"]),
                    "channel_id": channel_id,
                    "videos_inserted": entry_count,
                }
            )
            conn.execute(text("UPDATE jobs SET state='downloading', updated_at=now() WHERE id=:i"), {"i": job["id"]})
            youtube_requests_total.labels(operation="channel_expansion", result="success").inc()

        except Exception as e:
            logger.error(
                "Channel expansion failed after retries",
                extra={"job_id": str(job["id"]), "error": str(e)[:200]}
            )
            youtube_requests_total.labels(operation="channel_expansion", result="failure").inc()
            conn.execute(
                text("UPDATE jobs SET state='failed', error=:e, updated_at=now() WHERE id=:i"),
                {"i": job["id"], "e": str(e)[:5000]},
            )


def expand_single_if_needed(conn):
    from worker.metrics import youtube_requests_total
    from worker.youtube_resilience import classify_error, get_circuit_breaker, retry_with_backoff

    logger.debug("Checking for pending single jobs to expand")
    jobs = (
        conn.execute(
            text(
                """
        SELECT j.id, j.input_url
        FROM jobs j
        WHERE j.kind='single'
          AND j.state IN ('pending','downloading')
          AND NOT EXISTS (
              SELECT 1 FROM videos v WHERE v.job_id = j.id
          )
        FOR UPDATE SKIP LOCKED
        LIMIT 5
    """
            )
        )
        .mappings()
        .all()
    )

    # Get circuit breaker for metadata operations
    circuit_breaker = None
    if settings.YTDLP_CIRCUIT_BREAKER_ENABLED:
        circuit_breaker = get_circuit_breaker("youtube_metadata")

    for job in jobs:
        url = job["input_url"]
        logger.info("Expanding single job", extra={"job_id": str(job["id"]), "url": url})

        # Use factory function to capture loop variable correctly for retry closure
        def make_fetch_video_metadata(video_url: str):
            """Create video metadata fetch function with explicit parameter binding."""
            def fetch_video_metadata():
                """Fetch video metadata with timeout."""
                # Use yt-dlp to robustly extract the video id for any YouTube URL form
                return _fetch_ytdlp_metadata(video_url)
            return fetch_video_metadata  # noqa: B023 (false positive - function returned immediately)

        fetch_video_metadata = make_fetch_video_metadata(url)

        def classify_video_error(e: Exception):
            """Classify video expansion error."""
            stderr = getattr(e, "stderr", b"")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="ignore")
            returncode = getattr(e, "returncode", 0)
            return classify_error(returncode, stderr or str(e), e)

        try:
            # Use retry with backoff for single video expansion
            data = retry_with_backoff(
                fetch_video_metadata,
                max_attempts=settings.YTDLP_MAX_RETRY_ATTEMPTS,
                base_delay=settings.YTDLP_BACKOFF_BASE_DELAY,
                max_delay=settings.YTDLP_BACKOFF_MAX_DELAY,
                circuit_breaker=circuit_breaker,
                classify_func=classify_video_error,
            )

            vid = data.get("id")
            if not vid:
                # Some structures may nest under 'entries' when URL points to a playlist link
                entries = data.get("entries") or []
                if entries:
                    vid = entries[0].get("id")
            if not vid:
                raise RuntimeError(f"Unable to determine YouTube ID for URL: {url}")

            logger.info("Job resolved video id", extra={"job_id": str(job["id"]), "youtube_id": vid})
            # Extract title and duration from metadata
            title = data.get("title", "")
            duration = data.get("duration")  # duration in seconds
            uploaded_at = _metadata_uploaded_at(data)
            channel_name = _metadata_channel_name(data)
            logger.info(
                "Video metadata extracted",
                extra={
                    "title": title[:50] + ("..." if len(title) > 50 else ""),
                    "duration_seconds": duration,
                    "uploaded_at": uploaded_at.isoformat() if uploaded_at else None,
                    "channel_name": channel_name,
                },
            )
            conn.execute(
                text(
                    """
                INSERT INTO videos (job_id, youtube_id, idx, title, duration_seconds, uploaded_at, channel_name)
                VALUES (:j,:y,:idx,:title,:dur,:uploaded_at,:channel_name)
                ON CONFLICT (job_id, youtube_id) DO NOTHING
            """
                ),
                {
                    "j": job["id"],
                    "y": vid,
                    "idx": 0,
                    "title": title,
                    "dur": duration,
                    "uploaded_at": uploaded_at,
                    "channel_name": channel_name,
                },
            )
            logger.info("Marking job as downloading after single expansion", extra={"job_id": str(job["id"])})
            conn.execute(text("UPDATE jobs SET state='downloading', updated_at=now() WHERE id=:i"), {"i": job["id"]})
            youtube_requests_total.labels(operation="video_expansion", result="success").inc()

        except Exception as e:
            logger.error(
                "Single video expansion failed after retries",
                extra={"job_id": str(job["id"]), "error": str(e)[:200]}
            )
            youtube_requests_total.labels(operation="video_expansion", result="failure").inc()
            conn.execute(
                text("UPDATE jobs SET state='failed', error=:e, updated_at=now() WHERE id=:i"),
                {"i": job["id"], "e": str(e)[:5000]},
            )


def process_video(engine, video_id):
    deps = NativePipelineDependencies(
        settings=settings,
        logger=logger,
        download_audio=download_audio,
        ensure_wav_16k=ensure_wav_16k,
        chunk_audio=chunk_audio,
        transcribe_chunk=transcribe_chunk,
        diarize_and_align=diarize_and_align,
        replace_transcript_blocks=crud.replace_transcript_blocks,
        refresh_job_state=refresh_job_state,
    )
    return process_native_video(engine, video_id, workdir=WORKDIR, deps=deps)


def capture_youtube_captions_for_unprocessed(
    conn,
    limit: int = 5,
    *,
    staged_only: bool = False,
    active_only: bool = False,
    terminal_failures: bool = False,
) -> int:
    result = ingest_captions_for_unprocessed_videos(
        conn,
        limit=limit,
        staged_only=staged_only,
        active_only=active_only,
        terminal_failures=terminal_failures,
        youtube_service=get_youtube_service(),
    )
    if result.rate_limited:
        from worker.youtube_resilience import YouTubeRateLimitError

        raise YouTubeRateLimitError("YouTube rate-limited caption ingest; pause caption ingest before retrying.")
    return result.completed


def promote_staged_batches_if_ready(conn) -> int:
    """Log staged batches whose caption phase is complete.

    Native transcription locking is enforced in worker.loop's queue SELECT so we
    do not need a custom video state that would conflict with the existing DB
    enum. This helper is intentionally observational.
    """
    rows = conn.execute(
        text(
            f"""
            SELECT COALESCE(j.meta->>'batch_id', j.id::text) AS batch_id
            FROM jobs j
            JOIN videos v ON v.job_id = j.id
            WHERE j.meta->>'staged' = 'true'
              AND j.state NOT IN ('failed','completed')
            GROUP BY COALESCE(j.meta->>'batch_id', j.id::text)
            HAVING COUNT(DISTINCT j.id) >= COALESCE(MAX((j.meta->>'batch_expected_jobs')::int), 1)
               AND COUNT(*) FILTER (WHERE v.caption_ingest_state IN ({OPEN_CAPTION_INGEST_STATES_SQL})) = 0
            """
        )
    ).fetchall()

    ready = 0
    for (batch_id,) in rows:
        ready += 1
        logger.info("Staged caption batch ready for native transcription", extra={"batch_id": batch_id})
    return ready
