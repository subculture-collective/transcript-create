import time

from sqlalchemy import create_engine, text

from app.logging_config import configure_logging, get_logger, job_id_ctx, video_id_ctx
from app.settings import settings
from worker.pipeline import capture_youtube_captions_for_unprocessed, expand_channel_if_needed, process_video

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
POLL_INTERVAL = 3

# Configure structured logging for worker service
configure_logging(
    service="worker",
    level=settings.LOG_LEVEL,
    json_format=(settings.LOG_FORMAT == "json"),
)
logger = get_logger(__name__)


def run():
    logger.info("Worker service started")
    while True:
        logger.debug("Polling for work: expand jobs and pick a video")
        with engine.begin() as conn:
            # Expand pending jobs into videos
            from worker.pipeline import expand_single_if_needed

            try:
                expand_single_if_needed(conn)
                expand_channel_if_needed(conn)
            except Exception as e:
                logger.exception("Error expanding jobs", extra={"error": str(e)})

            # Opportunistically capture YouTube captions early for videos without captions yet
            try:
                capture_youtube_captions_for_unprocessed(conn, limit=5)
            except Exception as e:
                logger.warning("YouTube captions capture step failed", extra={"error": str(e)})

            # Rescue stuck videos: if a video has been in a non-terminal state for too long, mark it pending again
            try:
                rescue_seconds = int(getattr(settings, "RESCUE_STUCK_AFTER_SECONDS", 0) or 0)
                if rescue_seconds > 0:
                    logger.debug("Rescue check: requeue videos stuck", extra={"threshold_seconds": rescue_seconds})
                    conn.execute(
                        text(
                            """
                        UPDATE videos
                        SET state = 'pending', updated_at = now()
                        WHERE state IN ('downloading','transcoding','transcribing')
                          AND now() - updated_at > make_interval(secs => :secs)
                        RETURNING id
                        """
                        ),
                        {"secs": rescue_seconds},
                    )
            except Exception as e:
                logger.warning("Rescue check failed", extra={"error": str(e)})

            # Model upgrade requeue: reprocess completed videos if current model is larger/better
            try:
                current_model = settings.WHISPER_MODEL
                model_hierarchy = {
                    "tiny": 1,
                    "base": 2,
                    "small": 3,
                    "medium": 4,
                    "large": 5,
                    "large-v2": 6,
                    "large-v3": 7,
                }
                current_rank = model_hierarchy.get(current_model, 0)
                if current_rank > 0:
                    requeue_result = conn.execute(
                        text(
                            """
                        UPDATE videos v
                        SET state = 'pending', updated_at = now()
                        FROM transcripts t
                        WHERE v.id = t.video_id
                          AND v.state = 'completed'
                          AND t.model IS NOT NULL
                          AND (
                            -- Requeue if transcript model rank is lower than current
                            CASE
                              WHEN t.model = 'tiny' THEN 1
                              WHEN t.model = 'base' THEN 2
                              WHEN t.model = 'small' THEN 3
                              WHEN t.model = 'medium' THEN 4
                              WHEN t.model = 'large' THEN 5
                              WHEN t.model = 'large-v2' THEN 6
                              WHEN t.model = 'large-v3' THEN 7
                              ELSE 0
                            END
                          ) < :current_rank
                        RETURNING v.id, t.model
                    """
                        ),
                        {"current_rank": current_rank},
                    )
                    requeued = requeue_result.fetchall()
                    if requeued:
                        logger.info(
                            "Model upgrade requeue",
                            extra={
                                "count": len(requeued),
                                "from_models": ", ".join(set(r[1] for r in requeued)),
                                "to_model": current_model,
                            },
                        )
            except Exception as e:
                logger.warning("Model upgrade requeue failed", extra={"error": str(e)})

            # Model upgrade requeue: reprocess completed videos if current model is larger/better
            try:
                current_model = settings.WHISPER_MODEL
                model_hierarchy = {
                    "tiny": 1,
                    "base": 2,
                    "small": 3,
                    "medium": 4,
                    "large": 5,
                    "large-v2": 6,
                    "large-v3": 7,
                }
                current_rank = model_hierarchy.get(current_model, 0)
                if current_rank > 0:
                    requeue_result = conn.execute(
                        text(
                            """
                        UPDATE videos v
                        SET state = 'pending', updated_at = now()
                        FROM transcripts t
                        WHERE v.id = t.video_id
                          AND v.state = 'completed'
                          AND t.model IS NOT NULL
                          AND (
                            -- Requeue if transcript model rank is lower than current
                            CASE
                              WHEN t.model = 'tiny' THEN 1
                              WHEN t.model = 'base' THEN 2
                              WHEN t.model = 'small' THEN 3
                              WHEN t.model = 'medium' THEN 4
                              WHEN t.model = 'large' THEN 5
                              WHEN t.model = 'large-v2' THEN 6
                              WHEN t.model = 'large-v3' THEN 7
                              ELSE 0
                            END
                          ) < :current_rank
                        RETURNING v.id, t.model
                    """
                        ),
                        {"current_rank": current_rank},
                    )
                    requeued = requeue_result.fetchall()
                    if requeued:
                        logger.info(
                            "Model upgrade requeue",
                            extra={
                                "count": len(requeued),
                                "from_models": ", ".join(set(r[1] for r in requeued)),
                                "to_model": current_model,
                            },
                        )
            except Exception as e:
                logger.warning("Model upgrade requeue failed", extra={"error": str(e)})
            row = conn.execute(
                text(
                    """
                SELECT v.id
                FROM videos v
                WHERE v.state = 'pending'
                ORDER BY v.created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            """
                )
            ).first()
            if not row:
                logger.debug("No pending videos found. Sleeping", extra={"sleep_seconds": POLL_INTERVAL})
                time.sleep(POLL_INTERVAL)
                continue
            video_id = row[0]
            
            # Set video context for logging
            video_id_ctx.set(str(video_id))
            
            logger.info("Picked video for processing")
            conn.execute(text("UPDATE videos SET state='downloading', updated_at=now() WHERE id=:i"), {"i": video_id})
        try:
            logger.info("Starting video processing")
            process_video(engine, video_id)
            logger.info("Video processing completed successfully")
        except Exception as e:
            logger.exception("Video processing failed", extra={"error": str(e)})
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE videos SET state='failed', error=:e, updated_at=now() WHERE id=:i"),
                    {"i": video_id, "e": str(e)[:5000]},
                )
        finally:
            # Clear video context
            video_id_ctx.set(None)


def main():
    run()


if __name__ == "__main__":
    main()
