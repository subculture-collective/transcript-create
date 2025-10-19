import json
import logging
import subprocess
import time
from pathlib import Path

from sqlalchemy import text

from app.settings import settings
from worker.audio import chunk_audio, download_audio, ensure_wav_16k
from worker.diarize import diarize_and_align
from worker.whisper_runner import transcribe_chunk
from worker.youtube_captions import fetch_youtube_auto_captions

WORKDIR = Path("/data")  # mount volume externally


def expand_channel_if_needed(conn):
    logging.debug("Checking for pending channel jobs to expand")
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
        logging.info("Expanding channel job %s from %s", job["id"], url)
        cmd = ["yt-dlp", "--flat-playlist", "-J", url]
        meta = subprocess.check_output(cmd)
        data = json.loads(meta)
        entries = data.get("entries", [])
        logging.info("Channel expansion found %d entries", len(entries))
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
        logging.info("Marking job %s as downloading after expansion", job["id"])
        conn.execute(text("UPDATE jobs SET state='downloading', updated_at=now() WHERE id=:i"), {"i": job["id"]})


def expand_single_if_needed(conn):
    logging.debug("Checking for pending single jobs to expand")
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
        logging.info("Expanding single job %s from %s", job["id"], url)
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
        logging.info("Job %s resolved video id %s", job["id"], vid)
        # Extract title and duration from metadata
        title = data.get("title", "")
        duration = data.get("duration")  # duration in seconds
        logging.info(
            "Video metadata: title='%s', duration=%ss", title[:50] + ("..." if len(title) > 50 else ""), duration
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
        logging.info("Marking job %s as downloading after single expansion", job["id"])
        conn.execute(text("UPDATE jobs SET state='downloading', updated_at=now() WHERE id=:i"), {"i": job["id"]})


def process_video(engine, video_id):
    t0 = time.time()
    logging.info("process_video start %s", video_id)
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

    logging.info("Downloading audio for %s", youtube_id)
    raw_path = download_audio(f"https://www.youtube.com/watch?v={youtube_id}", dest_dir)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE videos SET raw_path=:p, state='transcoding', updated_at=now() WHERE id=:i"),
            {"p": str(raw_path), "i": video_id},
        )

    logging.info("Converting to wav 16k for %s", video_id)
    wav_path = ensure_wav_16k(raw_path)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE videos SET wav_path=:p, state='transcribing', updated_at=now() WHERE id=:i"),
            {"p": str(wav_path), "i": video_id},
        )

    logging.info("Chunking audio (max %ss)", settings.CHUNK_SECONDS)
    chunks = chunk_audio(wav_path, settings.CHUNK_SECONDS)
    logging.info("Created %d chunk(s)", len(chunks))
    all_segments = []
    for c in chunks:
        ct0 = time.time()
        logging.info("Transcribing chunk %s (offset %.2fs)", c.path.name, c.offset)
        segs = transcribe_chunk(c.path)
        for s in segs:
            s["start"] += c.offset
            s["end"] += c.offset
        all_segments.extend(segs)
        logging.info("Chunk %s produced %d segments in %.2fs", c.path.name, len(segs), time.time() - ct0)

    logging.info("Diarization phase starting (%d segments)", len(all_segments))
    diar_segments = diarize_and_align(wav_path, all_segments)

    with engine.begin() as conn:
        full_text = " ".join(s["text"] for s in diar_segments)
        logging.info("Inserting transcript len=%d chars", len(full_text))
        # Clean existing transcript/segments for idempotent reprocessing
        try:
            conn.execute(text("DELETE FROM segments WHERE video_id = :v"), {"v": video_id})
            conn.execute(text("DELETE FROM transcripts WHERE video_id = :v"), {"v": video_id})
            logging.info("Cleared existing transcript/segments for video %s", video_id)
        except Exception as e:
            logging.warning("Failed to clear existing rows (continuing): %s", e)
        conn.execute(
            text(
                """
            INSERT INTO transcripts (video_id, full_text, language, model)
            VALUES (:v,:t,:lang,:m)
        """
            ),
            {"v": video_id, "t": full_text, "lang": "en", "m": settings.WHISPER_MODEL},
        )
        logging.info("Inserting %d segment rows", len(diar_segments))
        for s in diar_segments:
            conn.execute(
                text(
                    """
                INSERT INTO segments (video_id,start_ms,end_ms,text,speaker_label,confidence,avg_logprob,temperature,token_count)
                VALUES (:v,:s,:e,:txt,:spk,:conf,:lp,:temp,:tc)
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
                },
            )
        logging.info("Marking video %s completed", video_id)
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
            logging.info("Cleanup removed: %s", ", ".join(removed) if removed else "nothing")
        except Exception as e:
            logging.warning("Cleanup encountered an error: %s", e)
    logging.info("process_video end %s (%.2fs)", video_id, time.time() - t0)

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
            logging.info("Fetching YouTube captions for video %s (yid=%s)", vid, yid)
            res = fetch_youtube_auto_captions(yid)
            if not res:
                logging.info("No auto captions for %s", yid)
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
            logging.info("Persisted %d YouTube caption segments for %s", len(segs), yid)
            processed += 1
        except Exception as e:
            logging.warning("YouTube captions fetch failed for %s: %s", yid, e)
    return processed
