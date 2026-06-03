from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.settings import settings
from worker.repositories import VideoRepository
from worker.youtube.service import YouTubeCaptionResult, YouTubeService
from worker.youtube_captions import YouTubeCaptionFetchError, YouTubeCaptionRateLimitError, fetch_youtube_auto_captions
from worker.youtube_resilience import ErrorClass, YouTubeRateLimitError, classify_error

logger = get_logger(__name__)


@dataclass(frozen=True)
class CaptionIngestionResult:
    attempted: int
    completed: int
    unavailable: int
    failed: int
    rate_limited: bool
    cooldown_seconds: int | None


def _ingest_available_captions_impl(
    db: Session,
    *,
    batch_id: str | None = None,
    limit: int = 1,
    staged_only: bool = True,
    active_only: bool = True,
    terminal_failures: bool = True,
    fetch_caption_func: Callable[[str], Any] | None = None,
    youtube_service: YouTubeService | None = None,
) -> CaptionIngestionResult:
    clauses = [
        "NOT EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id)",
        "(:active_only IS FALSE OR v.caption_ingest_state = 'pending')",
        "(:active_only IS FALSE OR v.state IN ('pending','downloading','transcoding','transcribing'))",
        "(:active_only IS FALSE OR j.state NOT IN ('failed','completed'))",
        "(:staged_only IS FALSE OR j.meta->>'staged' = 'true')",
    ]
    params: dict[str, Any] = {"lim": limit, "staged_only": staged_only, "active_only": active_only}
    if batch_id is not None:
        clauses.append("COALESCE(j.meta->>'batch_id', j.id::text) = :batch_id")
        params["batch_id"] = batch_id

    rows = db.execute(
        text(
            f"""
        SELECT v.id, v.youtube_id
        FROM videos v
        JOIN jobs j ON j.id = v.job_id
        WHERE {' AND '.join(clauses)}
        ORDER BY v.idx ASC NULLS LAST, v.created_at DESC
        FOR UPDATE SKIP LOCKED
        LIMIT :lim
        """
        ),
        params,
    ).all()

    video_repo = VideoRepository(db)
    attempted = completed = unavailable = failed = 0

    if fetch_caption_func is None:
        if youtube_service is not None:
            fetch_caption_func = youtube_service.fetch_auto_captions
        else:
            fetch_caption_func = fetch_youtube_auto_captions

    def normalize_caption_result(result: Any) -> tuple[Any, list[Any]] | None:
        if result is None:
            return None
        if isinstance(result, YouTubeCaptionResult):
            return result.track, result.segments
        return result

    for vid, yid in rows:
        attempted += 1
        try:
            video_repo.mark_caption_running(str(vid))
            logger.info("Fetching YouTube captions for video %s (yid=%s)", vid, yid)
            res = normalize_caption_result(fetch_caption_func(yid))
            if not res:
                logger.info("No auto captions for %s", yid)
                video_repo.mark_caption_unavailable(str(vid))
                unavailable += 1
                continue

            track, segs = res
            yt_full_text = " ".join(s.text for s in segs)

            db.execute(
                text(
                    """
                    DELETE FROM youtube_segments
                    WHERE youtube_transcript_id IN (
                        SELECT id FROM youtube_transcripts WHERE video_id=:v
                    )
                    """
                ),
                {"v": str(vid)},
            )
            db.execute(text("DELETE FROM youtube_transcripts WHERE video_id=:v"), {"v": str(vid)})
            row = db.execute(
                text(
                    """
                INSERT INTO youtube_transcripts (video_id, language, kind, source_url, full_text)
                VALUES (:v,:lang,:kind,:url,:full)
                RETURNING id
            """
                ),
                {"v": str(vid), "lang": track.language, "kind": track.kind, "url": track.url, "full": yt_full_text},
            ).first()
            yt_tr_id = row[0]
            for s in segs:
                db.execute(
                    text(
                        """
                    INSERT INTO youtube_segments (youtube_transcript_id, start_ms, end_ms, text)
                    VALUES (:t, :s, :e, :txt)
                """
                    ),
                    {"t": yt_tr_id, "s": int(s.start * 1000), "e": int(s.end * 1000), "txt": s.text},
                )
            logger.info("Persisted %d YouTube caption segments for %s", len(segs), yid)
            video_repo.mark_caption_completed(str(vid))
            completed += 1
        except (YouTubeCaptionRateLimitError, YouTubeRateLimitError) as e:
            logger.warning("YouTube rate limit hit during caption ingest; leaving video pending and pausing batch")
            video_repo.mark_caption_pending_with_error(str(vid), str(e))
            return CaptionIngestionResult(
                attempted=attempted,
                completed=completed,
                unavailable=unavailable,
                failed=failed,
                rate_limited=True,
                cooldown_seconds=settings.YTDLP_RATE_LIMIT_COOLDOWN_SECONDS,
            )
        except YouTubeCaptionFetchError as e:
            logger.warning("YouTube captions fetch/parse failed for %s: %s", yid, e)
            if terminal_failures:
                video_repo.mark_caption_failed(str(vid), str(e))
                failed += 1
            else:
                video_repo.mark_caption_pending_with_error(str(vid), str(e))
        except Exception as e:
            error_class = classify_error(getattr(e, "returncode", 0), getattr(e, "stderr", "") or str(e), e)
            if error_class == ErrorClass.THROTTLE:
                logger.warning("YouTube rate limit hit during caption ingest; leaving video pending and pausing batch")
                video_repo.mark_caption_pending_with_error(str(vid), str(e))
                return CaptionIngestionResult(
                    attempted=attempted,
                    completed=completed,
                    unavailable=unavailable,
                    failed=failed,
                    rate_limited=True,
                    cooldown_seconds=settings.YTDLP_RATE_LIMIT_COOLDOWN_SECONDS,
                )
            logger.warning("YouTube captions fetch failed for %s: %s", yid, e)
            if terminal_failures:
                video_repo.mark_caption_failed(str(vid), str(e))
                failed += 1
            else:
                video_repo.mark_caption_pending_with_error(str(vid), str(e))

    return CaptionIngestionResult(
        attempted=attempted,
        completed=completed,
        unavailable=unavailable,
        failed=failed,
        rate_limited=False,
        cooldown_seconds=None,
    )


def ingest_available_captions(
    db: Session,
    *,
    batch_id: str | None = None,
    limit: int = 1,
    youtube_service: YouTubeService | None = None,
) -> CaptionIngestionResult:
    return _ingest_available_captions_impl(
        db,
        batch_id=batch_id,
        limit=limit,
        staged_only=True,
        active_only=True,
        terminal_failures=True,
        youtube_service=youtube_service,
    )


def ingest_captions_for_unprocessed_videos(
    db: Session,
    *,
    batch_id: str | None = None,
    limit: int = 1,
    staged_only: bool = True,
    active_only: bool = True,
    terminal_failures: bool = True,
    fetch_caption_func: Callable[[str], Any] | None = None,
    youtube_service: YouTubeService | None = None,
) -> CaptionIngestionResult:
    """Compatibility-oriented caption ingest Interface for existing callers.

    `ingest_available_captions` is the narrow rolling-mode Interface used by the
    worker loop. This wider Interface preserves legacy knobs while keeping the
    implementation local to this Module.
    """
    return _ingest_available_captions_impl(
        db,
        batch_id=batch_id,
        limit=limit,
        staged_only=staged_only,
        active_only=active_only,
        terminal_failures=terminal_failures,
        fetch_caption_func=fetch_caption_func,
        youtube_service=youtube_service,
    )
