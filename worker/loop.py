import os
import socket
import time
from threading import Thread

from prometheus_client import start_http_server
from sqlalchemy import create_engine, text

from app.logging_config import configure_logging, get_logger, video_id_ctx
from app.settings import settings
from app.ytdlp_validation import validate_js_runtime_or_exit
from worker.metrics import setup_worker_info, try_collect_gpu_metrics
from worker.pipeline import capture_youtube_captions_for_unprocessed, expand_channel_if_needed, process_video

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
POLL_INTERVAL = 3
HEARTBEAT_INTERVAL = 60  # seconds

# Configure structured logging for worker service
configure_logging(
    service="worker",
    level=settings.LOG_LEVEL,
    json_format=(settings.LOG_FORMAT == "json"),
)
logger = get_logger(__name__)

# Generate a unique worker ID based on hostname and PID
WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"


def update_heartbeat():
    """Update worker heartbeat in database."""
    try:
        with engine.begin() as conn:
            # Upsert heartbeat record
            conn.execute(
                text(
                    """
                    INSERT INTO worker_heartbeat (worker_id, hostname, pid, last_seen, metrics)
                    VALUES (:worker_id, :hostname, :pid, now(), :metrics)
                    ON CONFLICT (worker_id)
                    DO UPDATE SET
                        last_seen = now(),
                        hostname = EXCLUDED.hostname,
                        pid = EXCLUDED.pid,
                        metrics = EXCLUDED.metrics
                """
                ),
                {
                    "worker_id": WORKER_ID,
                    "hostname": socket.gethostname(),
                    "pid": os.getpid(),
                    "metrics": "{}",  # Can be extended with additional metrics
                },
            )
            logger.debug("Worker heartbeat updated", extra={"worker_id": WORKER_ID})
    except Exception as e:
        logger.warning("Failed to update worker heartbeat", extra={"error": str(e)})


def update_queue_metrics():
    """Update queue metrics from database."""
    from worker.metrics import videos_in_progress, videos_pending

    try:
        with engine.begin() as conn:
            # Count pending videos
            pending_count = conn.execute(text("SELECT COUNT(*) FROM videos WHERE state = 'pending'")).scalar_one()
            videos_pending.set(pending_count)

            # Count in-progress videos by state
            states = conn.execute(
                text(
                    """
                    SELECT state, COUNT(*)
                    FROM videos
                    WHERE state IN ('downloading', 'transcoding', 'transcribing')
                    GROUP BY state
                """
                )
            ).all()

            # Reset all in-progress gauges first
            for state in ["downloading", "transcoding", "transcribing"]:
                videos_in_progress.labels(state=state).set(0)

            # Set current counts
            for state, count in states:
                videos_in_progress.labels(state=state).set(count)
    except Exception as e:
        logger.warning("Failed to update queue metrics", extra={"error": str(e)})


def gpu_metrics_collector():
    """Background thread to periodically collect GPU metrics."""
    while True:
        try:
            try_collect_gpu_metrics()
        except Exception as e:
            logger.debug("GPU metrics collection failed", extra={"error": str(e)})
        time.sleep(30)  # Update every 30 seconds


def heartbeat_updater():
    """Background thread to periodically update worker heartbeat."""
    while True:
        try:
            update_heartbeat()
        except Exception as e:
            logger.debug("Heartbeat update failed", extra={"error": str(e)})
        time.sleep(HEARTBEAT_INTERVAL)


def run():
    # Validate JavaScript runtime for yt-dlp before starting worker
    validate_js_runtime_or_exit()

    logger.info("Worker service started", extra={"worker_id": WORKER_ID})

    # Initialize worker info metrics
    setup_worker_info(
        whisper_model=settings.WHISPER_MODEL,
        whisper_backend=settings.WHISPER_BACKEND,
        force_gpu=settings.FORCE_GPU,
    )

    # Start Prometheus metrics HTTP server on port 8001
    try:
        start_http_server(8001)
        logger.info("Prometheus metrics server started", extra={"port": 8001})
    except Exception as e:
        logger.warning("Failed to start metrics server", extra={"error": str(e)})

    # Start GPU metrics collector thread
    gpu_thread = Thread(target=gpu_metrics_collector, daemon=True)
    gpu_thread.start()

    # Start heartbeat updater thread
    heartbeat_thread = Thread(target=heartbeat_updater, daemon=True)
    heartbeat_thread.start()
    logger.info("Worker heartbeat thread started")

    # Initial heartbeat
    update_heartbeat()

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

            # Update queue metrics
            update_queue_metrics()

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

            # Track successful video processing
            from worker.metrics import videos_processed_total

            videos_processed_total.labels(result="completed").inc()
        except Exception as e:
            logger.exception("Video processing failed", extra={"error": str(e)})

            # Track failed video processing
            from worker.metrics import videos_processed_total

            videos_processed_total.labels(result="failed").inc()

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
