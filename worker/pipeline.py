from __future__ import annotations

import json
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.logging_config import get_logger
from app.settings import settings
from worker.audio import chunk_audio, download_audio, ensure_wav_16k
from worker.diarize import diarize_and_align
from worker.state_model import ACTIVE_VIDEO_STATES, OPEN_CAPTION_INGEST_STATES, TERMINAL_VIDEO_STATES, sql_string_list
from worker.whisper_runner import transcribe_chunk
from worker.repositories import VideoRepository
from worker.youtube_captions import (
    YouTubeCaptionFetchError,
    YouTubeCaptionRateLimitError,
    fetch_youtube_auto_captions,
)

WORKDIR = Path("/data")  # mount volume externally

logger = get_logger(__name__)

ACTIVE_VIDEO_STATES_SQL = sql_string_list(ACTIVE_VIDEO_STATES)
OPEN_CAPTION_INGEST_STATES_SQL = sql_string_list(OPEN_CAPTION_INGEST_STATES)
TERMINAL_VIDEO_STATES_SQL = sql_string_list(TERMINAL_VIDEO_STATES)


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


def _yt_dlp_metadata_commands(url: str, *, flat_playlist: bool = False) -> list[tuple[str, list[str]]]:
    """Build simple yt-dlp metadata commands using the configured client fallback order."""
    from worker.ytdlp_client_utils import get_client_extractor_args

    clients = [c.strip() for c in settings.YTDLP_CLIENT_ORDER.split(",") if c.strip()]
    disabled = {c.strip() for c in settings.YTDLP_CLIENTS_DISABLED.split(",") if c.strip()}
    commands: list[tuple[str, list[str]]] = []

    for client in clients:
        if client in disabled:
            continue
        extractor_args = get_client_extractor_args(client)
        if extractor_args is None:
            logger.warning("Unknown YTDLP client in metadata strategy; skipping", extra={"client": client})
            continue
        cmd = ["yt-dlp"]
        if flat_playlist:
            cmd.append("--flat-playlist")
        cmd.append("-J")
        cmd.extend(extractor_args)
        if settings.YTDLP_COOKIES_PATH and Path(settings.YTDLP_COOKIES_PATH).exists():
            cmd.extend(["--cookies", settings.YTDLP_COOKIES_PATH])
        if settings.YTDLP_EXTRA_ARGS:
            cmd.extend(shlex.split(settings.YTDLP_EXTRA_ARGS))
        cmd.append(url)
        commands.append((client, cmd))

    if not commands:
        cmd = ["yt-dlp"]
        if flat_playlist:
            cmd.append("--flat-playlist")
        cmd.extend(["-J", url])
        commands.append(("default", cmd))

    return commands


def _fetch_ytdlp_metadata(url: str, *, flat_playlist: bool = False) -> dict[str, Any]:
    """Fetch yt-dlp JSON metadata using configured client fallback commands."""
    last_error: subprocess.CalledProcessError | None = None
    for client, cmd in _yt_dlp_metadata_commands(url, flat_playlist=flat_playlist):
        try:
            logger.info("Fetching yt-dlp metadata", extra={"client": client, "flat_playlist": flat_playlist})
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=settings.YTDLP_REQUEST_TIMEOUT,
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            last_error = e
            logger.warning(
                "yt-dlp metadata strategy failed",
                extra={"client": client, "stderr_snippet": (e.stderr or "")[:200]},
            )

    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to fetch yt-dlp metadata")


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
        SELECT j.id, j.input_url
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

            # Extract channel ID for logging (None if not available)
            channel_id = data.get("channel_id") or data.get("uploader_id")

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
                conn.execute(
                    text(
                        """
                    INSERT INTO videos (job_id, youtube_id, idx, title, duration_seconds)
                    VALUES (:j,:y,:idx,:title,:dur)
                    ON CONFLICT (job_id, youtube_id) DO NOTHING
                """
                    ),
                    {"j": job["id"], "y": yid, "idx": idx, "title": title, "dur": duration},
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
            logger.info(
                "Video metadata extracted",
                extra={
                    "title": title[:50] + ("..." if len(title) > 50 else ""),
                    "duration_seconds": duration,
                },
            )
            conn.execute(
                text(
                    """
                INSERT INTO videos (job_id, youtube_id, idx, title, duration_seconds)
                VALUES (:j,:y,:idx,:title,:dur)
                ON CONFLICT (job_id, youtube_id) DO NOTHING
            """
                ),
                {"j": job["id"], "y": vid, "idx": 0, "title": title, "dur": duration},
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
    from worker.metrics import (
        chunk_count,
        diarization_duration_seconds,
        download_duration_seconds,
        transcode_duration_seconds,
        transcription_duration_seconds,
        whisper_chunk_transcription_seconds,
    )

    t0 = time.time()
    logger.info("Video processing started")
    with engine.begin() as conn:
        v = (
            conn.execute(
                text("SELECT v.*, j.id AS job_id FROM videos v JOIN jobs j ON j.id=v.job_id WHERE v.id=:i"),
                {"i": video_id},
            )
            .mappings()
            .first()
        )
    youtube_id = v["youtube_id"]
    dest_dir = WORKDIR / str(video_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading audio", extra={"youtube_id": youtube_id, "stage": "downloading"})
    download_start = time.time()
    raw_path = download_audio(f"https://www.youtube.com/watch?v={youtube_id}", dest_dir)
    download_duration = time.time() - download_start
    download_duration_seconds.observe(download_duration)
    logger.info("Download completed", extra={"duration_seconds": round(download_duration, 2)})

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE videos SET raw_path=:p, state='transcoding', updated_at=now() WHERE id=:i"),
            {"p": str(raw_path), "i": video_id},
        )

    logger.info("Converting to wav 16k", extra={"stage": "transcoding"})
    transcode_start = time.time()
    wav_path = ensure_wav_16k(raw_path)
    transcode_duration = time.time() - transcode_start
    transcode_duration_seconds.observe(transcode_duration)
    logger.info("Transcode completed", extra={"duration_seconds": round(transcode_duration, 2)})

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE videos SET wav_path=:p, state='transcribing', updated_at=now() WHERE id=:i"),
            {"p": str(wav_path), "i": video_id},
        )

    logger.info("Chunking audio", extra={"max_chunk_seconds": settings.CHUNK_SECONDS, "stage": "transcribing"})
    chunks = chunk_audio(wav_path, settings.CHUNK_SECONDS)
    logger.info("Audio chunks created", extra={"chunk_count": len(chunks)})
    chunk_count.observe(len(chunks))

    # Extract quality settings from job metadata if available
    with engine.begin() as conn:
        job_meta = conn.execute(
            text("SELECT meta FROM jobs WHERE id=:j"),
            {"j": v["job_id"]},
        ).scalar()

    if job_meta and isinstance(job_meta, str):
        job_meta = json.loads(job_meta)
    quality_settings = job_meta.get("quality", {}) if job_meta else {}
    language = quality_settings.get("language") or getattr(settings, "WHISPER_LANGUAGE", None) or None
    beam_size = quality_settings.get("beam_size") or getattr(settings, "WHISPER_BEAM_SIZE", 5)
    temp_from_settings = getattr(settings, "WHISPER_TEMPERATURE", 0.0)
    temperature = (
        quality_settings.get("temperature") if quality_settings.get("temperature") is not None else temp_from_settings
    )
    word_timestamps = quality_settings.get("word_timestamps", getattr(settings, "WHISPER_WORD_TIMESTAMPS", True))
    vad_filter = quality_settings.get("vad_filter", getattr(settings, "WHISPER_VAD_FILTER", False))

    all_segments = []
    detected_language = None
    language_probability = None
    transcription_start = time.time()

    for c in chunks:
        ct0 = time.time()
        logger.info("Transcribing chunk", extra={"chunk_file": c.path.name, "offset_seconds": c.offset})
        segs, lang_info = transcribe_chunk(
            c.path,
            language=language,
            beam_size=beam_size,
            temperature=temperature,
            word_timestamps=word_timestamps,
            vad_filter=vad_filter,
        )

        # Capture language info from first chunk
        if detected_language is None and lang_info:
            detected_language = lang_info.get("language")
            language_probability = lang_info.get("language_probability")
            logger.info(
                "Language detected",
                extra={
                    "language": detected_language,
                    "probability": language_probability,
                },
            )

        for s in segs:
            s["start"] += c.offset
            s["end"] += c.offset
            # Adjust word timestamps if present
            if "words" in s:
                for w in s["words"]:
                    w["start"] += c.offset
                    w["end"] += c.offset
        all_segments.extend(segs)
        chunk_duration = time.time() - ct0
        whisper_chunk_transcription_seconds.labels(model=settings.WHISPER_MODEL).observe(chunk_duration)
        logger.info(
            "Chunk transcription complete",
            extra={
                "chunk_file": c.path.name,
                "segment_count": len(segs),
                "duration_seconds": round(chunk_duration, 2),
            },
        )

    total_transcription_duration = time.time() - transcription_start
    transcription_duration_seconds.labels(model=settings.WHISPER_MODEL).observe(total_transcription_duration)
    logger.info("All chunks transcribed", extra={"duration_seconds": round(total_transcription_duration, 2)})

    diar_segments = all_segments
    if settings.ENABLE_DIARIZATION and settings.DIARIZATION_INLINE:
        logger.info("Inline diarization phase starting", extra={"segment_count": len(all_segments)})
        diarization_start = time.time()
        diar_segments = diarize_and_align(wav_path, all_segments)
        diarization_duration = time.time() - diarization_start
        if diarization_duration > 1.0:
            diarization_duration_seconds.observe(diarization_duration)
            logger.info("Inline diarization completed", extra={"duration_seconds": round(diarization_duration, 2)})
    elif settings.ENABLE_DIARIZATION:
        logger.info("Diarization queued for separate worker", extra={"segment_count": len(all_segments)})

    # Apply custom vocabulary corrections if enabled
    if getattr(settings, "ENABLE_CUSTOM_VOCABULARY", True):
        try:
            from worker.vocabulary import apply_vocabulary_corrections

            with engine.begin() as conn:
                # Ensure job_meta is a dict before accessing .get()
                if job_meta and isinstance(job_meta, str):
                    try:
                        job_meta = json.loads(job_meta)
                    except Exception as e:
                        logger.warning("Failed to parse job_meta as JSON", extra={"error": str(e)})
                        job_meta = None
                user_id = job_meta.get("user_id") if job_meta else None
                diar_segments = apply_vocabulary_corrections(conn, diar_segments, user_id)
                logger.info("Applied custom vocabulary corrections")
        except Exception as e:
            logger.warning("Failed to apply vocabulary corrections", extra={"error": str(e)})

    with engine.begin() as conn:
        full_text = " ".join(s["text"] for s in diar_segments)
        logger.info("Inserting transcript", extra={"text_length": len(full_text)})
        # Clean existing transcript/segments for idempotent reprocessing
        try:
            conn.execute(text("DELETE FROM segments WHERE video_id = :v"), {"v": video_id})
            conn.execute(text("DELETE FROM transcripts WHERE video_id = :v"), {"v": video_id})
            logger.info("Cleared existing transcript/segments for reprocessing")
        except Exception as e:
            logger.warning("Failed to clear existing rows (continuing)", extra={"error": str(e)})
        conn.execute(
            text(
                """
            INSERT INTO transcripts (video_id, full_text, language, model, detected_language, language_probability)
            VALUES (:v,:t,:lang,:m,:dlang,:lprob)
        """
            ),
            {
                "v": video_id,
                "t": full_text,
                "lang": detected_language or "en",
                "m": settings.WHISPER_MODEL,
                "dlang": detected_language,
                "lprob": language_probability,
            },
        )
        logger.info("Inserting segments", extra={"segment_count": len(diar_segments)})
        for s in diar_segments:
            # Serialize word timestamps if present
            word_ts_json = None
            if "words" in s and s["words"]:
                word_ts_json = json.dumps(s["words"])

            conn.execute(
                text(
                    """
                INSERT INTO segments (
                    video_id,start_ms,end_ms,text,speaker_label,confidence,
                    avg_logprob,temperature,token_count,word_timestamps
                )
                VALUES (:v,:s,:e,:txt,:spk,:conf,:lp,:temp,:tc,:wts)
            """
                ),
                {
                    "v": video_id,
                    "s": int(s["start"] * 1000),
                    "e": int(s["end"] * 1000),
                    "txt": s["text"],
                    "spk": s.get("speaker"),
                    "conf": s.get("confidence"),
                    "lp": s.get("avg_logprob"),
                    "temp": s.get("temperature"),
                    "tc": s.get("token_count"),
                    "wts": word_ts_json,
                },
            )
        logger.info("Marking video as completed")
        diarization_state = "completed" if settings.ENABLE_DIARIZATION and settings.DIARIZATION_INLINE else (
            "pending" if settings.ENABLE_DIARIZATION else "skipped"
        )
        conn.execute(
            text(
                """
                UPDATE videos
                SET state='completed', error=NULL, diarization_state=:ds, updated_at=now()
                WHERE id=:i
                """
            ),
            {"i": video_id, "ds": diarization_state},
        )
        refresh_job_state(conn, v["job_id"])

    # Cleanup large intermediates if configured
    if settings.CLEANUP_AFTER_PROCESS:
        try:
            removed = []
            preserve_wav_for_diarization = (
                settings.ENABLE_DIARIZATION
                and not settings.DIARIZATION_INLINE
                and diarization_state == "pending"
            )
            # Delete chunk files
            if settings.CLEANUP_DELETE_CHUNKS:
                for p in dest_dir.glob("chunk_*.wav"):
                    p.unlink(missing_ok=True)
                    removed.append(p.name)
            # Delete wav
            if settings.CLEANUP_DELETE_WAV and not preserve_wav_for_diarization and wav_path.exists():
                wav_path.unlink(missing_ok=True)
                removed.append(Path(wav_path).name)
            # Delete raw
            if settings.CLEANUP_DELETE_RAW and raw_path.exists():
                raw_path.unlink(missing_ok=True)
                removed.append(Path(raw_path).name)
            # Remove dir if empty
            if settings.CLEANUP_DELETE_DIR_IF_EMPTY:
                try:
                    next(dest_dir.iterdir())
                except StopIteration:
                    dest_dir.rmdir()
                    removed.append(f"dir:{dest_dir.name}")
            logger.info("Cleanup completed", extra={"removed_files": ", ".join(removed) if removed else "none"})
        except Exception as e:
            logger.warning("Cleanup encountered an error", extra={"error": str(e)})

    processing_time = time.time() - t0
    logger.info(
        "Video processing completed successfully",
        extra={"total_duration_seconds": round(processing_time, 2)},
    )
    return len(diar_segments)


def capture_youtube_captions_for_unprocessed(
    conn,
    limit: int = 5,
    *,
    staged_only: bool = False,
    active_only: bool = False,
    terminal_failures: bool = False,
) -> int:
    """Select a few videos lacking youtube_transcripts and attempt to fetch/persist captions.

    Run inside the worker loop before audio processing to make captions available early.
    """
    rows = conn.execute(
        text(
            """
        SELECT v.id, v.youtube_id
        FROM videos v
        JOIN jobs j ON j.id = v.job_id
        WHERE NOT EXISTS (
            SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id
        )
          AND (:active_only IS FALSE OR v.caption_ingest_state = 'pending')
          AND (:active_only IS FALSE OR v.state IN ('pending','downloading','transcoding','transcribing'))
          AND (:active_only IS FALSE OR j.state NOT IN ('failed','completed'))
          AND (:staged_only IS FALSE OR j.meta->>'staged' = 'true')
        ORDER BY v.idx ASC NULLS LAST, v.created_at DESC
        FOR UPDATE SKIP LOCKED
        LIMIT :lim
        """
        ),
        {"lim": limit, "staged_only": staged_only, "active_only": active_only},
    ).all()
    from worker.youtube_resilience import ErrorClass, YouTubeRateLimitError, classify_error

    video_repo = VideoRepository(conn)
    processed = 0
    for vid, yid in rows:
        try:
            video_repo.mark_caption_running(str(vid))
            logger.info("Fetching YouTube captions for video %s (yid=%s)", vid, yid)
            res = fetch_youtube_auto_captions(yid)
            if not res:
                logger.info("No auto captions for %s", yid)
                video_repo.mark_caption_unavailable(str(vid))
                continue
            track, segs = res
            yt_full_text = " ".join(s.text for s in segs)
            # delete + insert for idempotency
            conn.execute(
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
            conn.execute(text("DELETE FROM youtube_transcripts WHERE video_id=:v"), {"v": str(vid)})
            row = conn.execute(
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
                conn.execute(
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
            processed += 1
        except YouTubeCaptionRateLimitError as e:
            logger.warning("YouTube rate limit hit during caption download; leaving video pending and pausing batch")
            video_repo.mark_caption_pending_with_error(str(vid), str(e))
            raise YouTubeRateLimitError(str(e)) from e
        except YouTubeCaptionFetchError as e:
            logger.warning("YouTube captions fetch/parse failed for %s: %s", yid, e)
            if terminal_failures:
                video_repo.mark_caption_failed(str(vid), str(e))
            else:
                video_repo.mark_caption_pending_with_error(str(vid), str(e))
        except Exception as e:
            error_class = classify_error(getattr(e, "returncode", 0), getattr(e, "stderr", "") or str(e), e)
            if error_class == ErrorClass.THROTTLE:
                logger.warning("YouTube rate limit hit during caption ingest; leaving video pending and pausing batch")
                video_repo.mark_caption_pending_with_error(str(vid), str(e))
                raise YouTubeRateLimitError(str(e)) from e
            logger.warning("YouTube captions fetch failed for %s: %s", yid, e)
            if terminal_failures:
                video_repo.mark_caption_failed(str(vid), str(e))
            else:
                video_repo.mark_caption_pending_with_error(str(vid), str(e))
    return processed


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
