import json
import subprocess
import time
from pathlib import Path

from sqlalchemy import text

from app.logging_config import get_logger
from app.settings import settings
from worker.audio import chunk_audio, download_audio, ensure_wav_16k
from worker.diarize import diarize_and_align
from worker.whisper_runner import transcribe_chunk
from worker.youtube_captions import fetch_youtube_auto_captions

WORKDIR = Path("/data")  # mount volume externally

logger = get_logger(__name__)


def expand_channel_if_needed(conn):
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
    for job in jobs:
        url = job["input_url"]
        logger.info("Expanding channel job", extra={"job_id": str(job["id"]), "url": url})
        cmd = ["yt-dlp", "--flat-playlist", "-J", url]
        meta = subprocess.check_output(cmd)
        data = json.loads(meta)
        entries = data.get("entries", [])
        logger.info("Channel expansion found entries", extra={"count": len(entries)})
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
        logger.info("Marking job as downloading after expansion", extra={"job_id": str(job["id"])})
        conn.execute(text("UPDATE jobs SET state='downloading', updated_at=now() WHERE id=:i"), {"i": job["id"]})


def expand_single_if_needed(conn):
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
    for job in jobs:
        url = job["input_url"]
        logger.info("Expanding single job", extra={"job_id": str(job["id"]), "url": url})
        # Use yt-dlp to robustly extract the video id for any YouTube URL form
        meta = subprocess.check_output(["yt-dlp", "-J", url])
        data = json.loads(meta)
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
        quality_settings.get("temperature")
        if quality_settings.get("temperature") is not None
        else temp_from_settings
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
            vad_filter=vad_filter
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
                }
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

    logger.info("Diarization phase starting", extra={"segment_count": len(all_segments)})
    diarization_start = time.time()
    diar_segments = diarize_and_align(wav_path, all_segments)
    diarization_duration = time.time() - diarization_start
    if diarization_duration > 1.0:  # Only track if diarization actually ran
        diarization_duration_seconds.observe(diarization_duration)
        logger.info("Diarization completed", extra={"duration_seconds": round(diarization_duration, 2)})

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
                INSERT INTO segments (video_id,start_ms,end_ms,text,speaker_label,confidence,avg_logprob,temperature,token_count,word_timestamps)
                VALUES (:v,:s,:e,:txt,:spk,:conf,:lp,:temp,:tc,:wts)
            """  # noqa: E501
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
        conn.execute(text("UPDATE videos SET state='completed', updated_at=now() WHERE id=:i"), {"i": video_id})

    # Cleanup large intermediates if configured
    if settings.CLEANUP_AFTER_PROCESS:
        try:
            removed = []
            # Delete chunk files
            if settings.CLEANUP_DELETE_CHUNKS:
                for p in dest_dir.glob("chunk_*.wav"):
                    p.unlink(missing_ok=True)
                    removed.append(p.name)
            # Delete wav
            if settings.CLEANUP_DELETE_WAV and wav_path.exists():
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

    # YouTube captions are handled by a pre-processing loop step; see capture_youtube_captions_for_unprocessed


def capture_youtube_captions_for_unprocessed(conn, limit: int = 5) -> int:
    """Select a few videos lacking youtube_transcripts and attempt to fetch/persist captions.

    Run inside the worker loop before audio processing to make captions available early.
    """
    rows = conn.execute(
        text(
            """
        SELECT v.id, v.youtube_id
        FROM videos v
        WHERE NOT EXISTS (
            SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id
        )
        ORDER BY v.created_at
        FOR UPDATE SKIP LOCKED
        LIMIT :lim
        """
        ),
        {"lim": limit},
    ).all()
    processed = 0
    for vid, yid in rows:
        try:
            logger.info("Fetching YouTube captions for video %s (yid=%s)", vid, yid)
            res = fetch_youtube_auto_captions(yid)
            if not res:
                logger.info("No auto captions for %s", yid)
                continue
            track, segs = res
            yt_full_text = " ".join(s.text for s in segs)
            # delete + insert for idempotency
            conn.execute(
                text(
                    "DELETE FROM youtube_segments WHERE youtube_transcript_id IN (SELECT id FROM youtube_transcripts WHERE video_id=:v)"  # noqa: E501
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
            processed += 1
        except Exception as e:
            logger.warning("YouTube captions fetch failed for %s: %s", yid, e)
    return processed
