import time
from pathlib import Path

from sqlalchemy import create_engine, text

from app.logging_config import configure_logging, get_logger
from app.settings import settings
from worker.diarize import run_diarization

configure_logging(
    service="diarization-worker",
    level=settings.LOG_LEVEL,
    json_format=(settings.LOG_FORMAT == "json"),
)
logger = get_logger(__name__)


def _load_segments(conn, video_id):
    rows = conn.execute(
        text(
            """
            SELECT id, start_ms, end_ms, text, speaker_label, confidence, avg_logprob, temperature, token_count
            FROM segments
            WHERE video_id = :v
            ORDER BY start_ms, id
            """
        ),
        {"v": video_id},
    ).mappings().all()
    return [
        {
            "_segment_id": row["id"],
            "start": float(row["start_ms"] or 0) / 1000.0,
            "end": float(row["end_ms"] or 0) / 1000.0,
            "text": row["text"] or "",
            "speaker": row["speaker_label"],
            "speaker_label": row["speaker_label"],
            "confidence": row["confidence"],
            "avg_logprob": row["avg_logprob"],
            "temperature": row["temperature"],
            "token_count": row["token_count"],
        }
        for row in rows
    ]


def _claim_video(conn):
    row = conn.execute(
        text(
            """
            SELECT v.id, v.wav_path
            FROM videos v
            WHERE v.state = 'completed'
              AND v.wav_path IS NOT NULL
              AND v.diarization_state = 'pending'
              AND EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id)
            ORDER BY v.updated_at, v.created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        )
    ).mappings().first()
    if not row:
        return None
    logger.info("Claiming diarization job", extra={"video_id": str(row["id"]), "wav_path": row["wav_path"]})
    conn.execute(
        text("UPDATE videos SET diarization_state='running', diarization_error=NULL, updated_at=now() WHERE id=:v"),
        {"v": row["id"]},
    )
    return row


def _requeue_stale_running(conn):
    rows = conn.execute(
        text(
            """
            UPDATE videos
            SET diarization_state='pending',
                diarization_error='Requeued stale running diarization job',
                updated_at=now()
            WHERE diarization_state='running'
              AND now() - updated_at > (:timeout_minutes * interval '1 minute')
            RETURNING id
            """
        ),
        {"timeout_minutes": settings.DIARIZATION_RUNNING_TIMEOUT_MINUTES},
    ).fetchall()
    if rows:
        logger.warning(
            "Requeued stale running diarization jobs",
            extra={"count": len(rows), "timeout_minutes": settings.DIARIZATION_RUNNING_TIMEOUT_MINUTES},
        )


def process_one(engine) -> bool:
    with engine.begin() as conn:
        _requeue_stale_running(conn)
        row = _claim_video(conn)
    if not row:
        return False

    video_id = row["id"]
    wav_path = Path(row["wav_path"])
    logger.info("Starting diarization job", extra={"video_id": str(video_id), "wav_path": str(wav_path)})

    try:
        if not wav_path.exists():
            raise FileNotFoundError(f"WAV file missing for diarization: {wav_path}")
        with engine.begin() as conn:
            segments = _load_segments(conn, video_id)
        logger.info(
            "Loaded transcript segments for diarization",
            extra={"video_id": str(video_id), "segments": len(segments)},
        )
        if not segments:
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE videos SET diarization_state='skipped', updated_at=now() WHERE id=:v"),
                    {"v": video_id},
                )
            return True

        logger.info(
            "Calling pyannote diarization",
            extra={"video_id": str(video_id), "device": settings.DIARIZATION_DEVICE},
        )
        diar_list, friendly = run_diarization(wav_path)
        logger.info(
            "pyannote diarization returned",
            extra={"video_id": str(video_id), "speaker_regions": len(diar_list), "speakers": len(friendly)},
        )
        with engine.begin() as conn:
            assigned = 0
            for seg in segments:
                mid = (seg["start"] + seg["end"]) / 2.0
                speaker = None
                for start, end, raw_label in diar_list:
                    if start <= mid <= end:
                        speaker = friendly.get(raw_label, raw_label)
                        break
                if speaker:
                    assigned += 1
                conn.execute(
                    text("UPDATE segments SET speaker_label=:spk WHERE id=:sid"),
                    {"sid": seg["_segment_id"], "spk": speaker},
                )
            if assigned == 0:
                raise RuntimeError("Diarization completed without assigning any speaker labels")
            conn.execute(
                text(
                    """
                    UPDATE videos
                    SET diarization_state='completed', diarization_error=NULL, updated_at=now()
                    WHERE id=:v
                    """
                ),
                {"v": video_id},
            )
        logger.info(
            "Diarization job completed",
            extra={"video_id": str(video_id), "speakers_assigned": assigned},
        )
        return True
    except Exception as e:
        logger.exception("Diarization job failed", extra={"video_id": str(video_id), "error": str(e)})
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE videos
                    SET diarization_state='failed', diarization_error=:e, updated_at=now()
                    WHERE id=:v
                    """
                ),
                {"v": video_id, "e": str(e)[:5000]},
            )
        return True


def run():
    if not settings.ENABLE_DIARIZATION:
        logger.warning("ENABLE_DIARIZATION is false; diarization worker will idle")
    engine = create_engine(settings.DATABASE_URL, future=True, pool_pre_ping=True)
    logger.info(
        "Diarization worker started",
        extra={"device": settings.DIARIZATION_DEVICE, "inline": settings.DIARIZATION_INLINE},
    )
    while True:
        try:
            did_work = process_one(engine) if settings.ENABLE_DIARIZATION else False
        except Exception as e:
            logger.exception("Diarization worker loop failed", extra={"error": str(e)})
            did_work = False
        if not did_work:
            time.sleep(settings.DIARIZATION_POLL_INTERVAL)


def main():
    run()


if __name__ == "__main__":
    main()
