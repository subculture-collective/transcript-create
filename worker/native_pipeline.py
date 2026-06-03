from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import text

from app import crud
from app.logging_config import get_logger
from app.settings import settings
from app.transcripts.blocks import build_transcript_blocks
from app.transcripts.types import TranscriptSegment
from worker.audio import Chunk, chunk_audio, download_audio, ensure_wav_16k
from worker.diarize import diarize_and_align
from worker.whisper_runner import transcribe_chunk
from worker.youtube.service import get_youtube_service


WORKDIR = Path("/data")

logger = get_logger(__name__)


@dataclass(frozen=True)
class NativePipelineDependencies:
    settings: Any = settings
    logger: Any = logger
    download_audio: Callable[[str, Path], Path] = download_audio
    ensure_wav_16k: Callable[[Path], Path] = ensure_wav_16k
    chunk_audio: Callable[[Path, int], list[Chunk]] = chunk_audio
    transcribe_chunk: Callable[..., tuple[list[dict[str, Any]], dict[str, Any] | None]] = transcribe_chunk
    diarize_and_align: Callable[[Path, list[dict[str, Any]]], list[dict[str, Any]]] = diarize_and_align
    replace_transcript_blocks: Callable[[Any, Any, list[Any]], Any] = crud.replace_transcript_blocks
    refresh_job_state: Callable[[Any, Any], None] | None = None


@dataclass
class VideoPipelineContext:
    engine: Any
    video: dict[str, Any]
    work_dir: Path
    raw_path: Path | None = None
    wav_path: Path | None = None
    chunks: list[Chunk] = field(default_factory=list)
    job_meta: dict[str, Any] | str | None = None
    quality_settings: dict[str, Any] = field(default_factory=dict)
    all_segments: list[dict[str, Any]] = field(default_factory=list)
    diar_segments: list[dict[str, Any]] = field(default_factory=list)
    detected_language: str | None = None
    language_probability: float | None = None
    diarization_state: str = "skipped"

    @property
    def video_id(self) -> Any:
        return self.video["id"]

    @property
    def job_id(self) -> Any:
        return self.video["job_id"]

    @property
    def youtube_id(self) -> str:
        return self.video["youtube_id"]


def _parse_job_meta(job_meta: Any) -> dict[str, Any] | None:
    if not job_meta:
        return None
    if isinstance(job_meta, dict):
        return job_meta
    if isinstance(job_meta, str):
        try:
            parsed = json.loads(job_meta)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _load_video_context(engine, video_id: Any, *, workdir: Path, deps: NativePipelineDependencies) -> VideoPipelineContext:
    with engine.begin() as conn:
        video = (
            conn.execute(
                text("SELECT v.*, j.id AS job_id FROM videos v JOIN jobs j ON j.id=v.job_id WHERE v.id=:i"),
                {"i": video_id},
            )
            .mappings()
            .first()
        )

    if not video:
        raise RuntimeError(f"Video not found: {video_id}")

    work_dir = workdir / str(video_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    return VideoPipelineContext(engine=engine, video=dict(video), work_dir=work_dir)


def _enrich_source_metadata(ctx: VideoPipelineContext, deps: NativePipelineDependencies) -> None:
    if ("uploaded_at" in ctx.video and ctx.video.get("uploaded_at") is None) or (
        "channel_name" in ctx.video and not ctx.video.get("channel_name")
    ):
        try:
            metadata = get_youtube_service().fetch_metadata(f"https://www.youtube.com/watch?v={ctx.youtube_id}")
            uploaded_at = _metadata_uploaded_at(metadata)
            channel_name = _metadata_channel_name(metadata)
            title = metadata.get("title") or ctx.video.get("title")
            duration = metadata.get("duration") or ctx.video.get("duration_seconds")
            with ctx.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE videos
                        SET uploaded_at = COALESCE(uploaded_at, :uploaded_at),
                            channel_name = COALESCE(NULLIF(channel_name, ''), :channel_name),
                            title = COALESCE(NULLIF(title, ''), :title),
                            duration_seconds = COALESCE(duration_seconds, :duration),
                            updated_at = now()
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": ctx.video_id,
                        "uploaded_at": uploaded_at,
                        "channel_name": channel_name,
                        "title": title,
                        "duration": duration,
                    },
                )
            deps.logger.info(
                "Video source metadata enriched",
                extra={
                    "video_id": str(ctx.video_id),
                    "youtube_id": ctx.youtube_id,
                    "uploaded_at": uploaded_at.isoformat() if uploaded_at else None,
                    "channel_name": channel_name,
                },
            )
        except Exception as e:
            deps.logger.warning(
                "Unable to enrich video source metadata before processing",
                extra={"video_id": str(ctx.video_id), "youtube_id": ctx.youtube_id, "error": str(e)[:200]},
            )


def _load_job_meta_and_quality_settings(ctx: VideoPipelineContext, deps: NativePipelineDependencies) -> None:
    with ctx.engine.begin() as conn:
        job_meta = conn.execute(text("SELECT meta FROM jobs WHERE id=:j"), {"j": ctx.job_id}).scalar()

    parsed_job_meta = _parse_job_meta(job_meta)
    if isinstance(job_meta, str) and job_meta and parsed_job_meta is None:
        deps.logger.warning("Failed to parse job_meta as JSON", extra={"job_id": str(ctx.job_id)})
    ctx.job_meta = parsed_job_meta if parsed_job_meta is not None else job_meta
    ctx.quality_settings = parsed_job_meta.get("quality", {}) if parsed_job_meta else {}


def _download_and_transcode(ctx: VideoPipelineContext, deps: NativePipelineDependencies) -> None:
    from worker.metrics import download_duration_seconds, transcode_duration_seconds

    deps.logger.info("Downloading audio", extra={"youtube_id": ctx.youtube_id, "stage": "downloading"})
    download_start = time.time()
    raw_path = deps.download_audio(f"https://www.youtube.com/watch?v={ctx.youtube_id}", ctx.work_dir)
    ctx.raw_path = raw_path
    download_duration = time.time() - download_start
    download_duration_seconds.observe(download_duration)
    deps.logger.info("Download completed", extra={"duration_seconds": round(download_duration, 2)})

    with ctx.engine.begin() as conn:
        conn.execute(
            text("UPDATE videos SET raw_path=:p, state='transcoding', updated_at=now() WHERE id=:i"),
            {"p": str(raw_path), "i": ctx.video_id},
        )

    deps.logger.info("Converting to wav 16k", extra={"stage": "transcoding"})
    transcode_start = time.time()
    wav_path = deps.ensure_wav_16k(raw_path)
    ctx.wav_path = wav_path
    transcode_duration = time.time() - transcode_start
    transcode_duration_seconds.observe(transcode_duration)
    deps.logger.info("Transcode completed", extra={"duration_seconds": round(transcode_duration, 2)})

    with ctx.engine.begin() as conn:
        conn.execute(
            text("UPDATE videos SET wav_path=:p, state='transcribing', updated_at=now() WHERE id=:i"),
            {"p": str(wav_path), "i": ctx.video_id},
        )


def _quality_setting(ctx: VideoPipelineContext, key: str, default: Any) -> Any:
    value = ctx.quality_settings.get(key)
    return default if value is None else value


def _transcribe_chunks(ctx: VideoPipelineContext, deps: NativePipelineDependencies) -> None:
    if ctx.wav_path is None:
        raise RuntimeError("Audio has not been transcoded yet")

    deps.logger.info(
        "Chunking audio",
        extra={"max_chunk_seconds": deps.settings.CHUNK_SECONDS, "stage": "transcribing"},
    )
    ctx.chunks = deps.chunk_audio(ctx.wav_path, deps.settings.CHUNK_SECONDS)
    deps.logger.info("Audio chunks created", extra={"chunk_count": len(ctx.chunks)})

    from worker.metrics import (
        chunk_count,
        transcription_duration_seconds,
        whisper_chunk_transcription_seconds,
    )

    chunk_count.observe(len(ctx.chunks))

    language = _quality_setting(ctx, "language", getattr(deps.settings, "WHISPER_LANGUAGE", None) or None)
    beam_size = _quality_setting(ctx, "beam_size", getattr(deps.settings, "WHISPER_BEAM_SIZE", 5))
    temperature = _quality_setting(ctx, "temperature", getattr(deps.settings, "WHISPER_TEMPERATURE", 0.0))
    word_timestamps = _quality_setting(ctx, "word_timestamps", getattr(deps.settings, "WHISPER_WORD_TIMESTAMPS", True))
    vad_filter = _quality_setting(ctx, "vad_filter", getattr(deps.settings, "WHISPER_VAD_FILTER", False))

    transcription_start = time.time()
    ctx.all_segments = []

    for c in ctx.chunks:
        ct0 = time.time()
        deps.logger.info("Transcribing chunk", extra={"chunk_file": c.path.name, "offset_seconds": c.offset})
        segs, lang_info = deps.transcribe_chunk(
            c.path,
            language=language,
            beam_size=beam_size,
            temperature=temperature,
            word_timestamps=word_timestamps,
            vad_filter=vad_filter,
        )

        if ctx.detected_language is None and lang_info:
            ctx.detected_language = lang_info.get("language")
            ctx.language_probability = lang_info.get("language_probability")
            deps.logger.info(
                "Language detected",
                extra={"language": ctx.detected_language, "probability": ctx.language_probability},
            )

        for s in segs:
            s["start"] += c.offset
            s["end"] += c.offset
            if "words" in s:
                for w in s["words"]:
                    w["start"] += c.offset
                    w["end"] += c.offset
        ctx.all_segments.extend(segs)
        chunk_duration = time.time() - ct0
        whisper_chunk_transcription_seconds.labels(model=deps.settings.WHISPER_MODEL).observe(chunk_duration)
        deps.logger.info(
            "Chunk transcription complete",
            extra={
                "chunk_file": c.path.name,
                "segment_count": len(segs),
                "duration_seconds": round(chunk_duration, 2),
            },
        )

    total_transcription_duration = time.time() - transcription_start
    transcription_duration_seconds.labels(model=deps.settings.WHISPER_MODEL).observe(total_transcription_duration)
    deps.logger.info("All chunks transcribed", extra={"duration_seconds": round(total_transcription_duration, 2)})


def _apply_diarization(ctx: VideoPipelineContext, deps: NativePipelineDependencies) -> None:
    ctx.diar_segments = ctx.all_segments
    if deps.settings.ENABLE_DIARIZATION and deps.settings.DIARIZATION_INLINE:
        deps.logger.info("Inline diarization phase starting", extra={"segment_count": len(ctx.all_segments)})
        diarization_start = time.time()
        ctx.diar_segments = deps.diarize_and_align(ctx.wav_path, ctx.all_segments)  # type: ignore[arg-type]
        diarization_duration = time.time() - diarization_start
        if diarization_duration > 1.0:
            from worker.metrics import diarization_duration_seconds

            diarization_duration_seconds.observe(diarization_duration)
            deps.logger.info(
                "Inline diarization completed",
                extra={"duration_seconds": round(diarization_duration, 2)},
            )
        ctx.diarization_state = "completed"
    elif deps.settings.ENABLE_DIARIZATION:
        deps.logger.info("Diarization queued for separate worker", extra={"segment_count": len(ctx.all_segments)})
        ctx.diarization_state = "pending"
    else:
        ctx.diarization_state = "skipped"


def _apply_custom_vocabulary(ctx: VideoPipelineContext, deps: NativePipelineDependencies) -> None:
    if not getattr(deps.settings, "ENABLE_CUSTOM_VOCABULARY", True):
        return

    try:
        from worker.vocabulary import apply_vocabulary_corrections

        user_id = ctx.job_meta.get("user_id") if isinstance(ctx.job_meta, dict) else None
        with ctx.engine.begin() as conn:
            ctx.diar_segments = apply_vocabulary_corrections(conn, ctx.diar_segments, user_id)
            deps.logger.info("Applied custom vocabulary corrections")
    except Exception as e:
        deps.logger.warning("Failed to apply vocabulary corrections", extra={"error": str(e)})


def _refresh_job_state(conn, job_id, *, error: str | None = None) -> None:
    from worker.pipeline import ACTIVE_VIDEO_STATES_SQL

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


def _persist_transcript(ctx: VideoPipelineContext, deps: NativePipelineDependencies) -> None:
    refresh_job_state = deps.refresh_job_state or _refresh_job_state

    with ctx.engine.begin() as conn:
        full_text = " ".join(s["text"] for s in ctx.diar_segments)
        deps.logger.info("Inserting transcript", extra={"text_length": len(full_text)})
        try:
            conn.execute(text("DELETE FROM segments WHERE video_id = :v"), {"v": ctx.video_id})
            conn.execute(text("DELETE FROM transcripts WHERE video_id = :v"), {"v": ctx.video_id})
            deps.logger.info("Cleared existing transcript/segments for reprocessing")
        except Exception as e:
            deps.logger.warning("Failed to clear existing rows (continuing)", extra={"error": str(e)})

        conn.execute(
            text(
                """
            INSERT INTO transcripts (video_id, full_text, language, model, detected_language, language_probability)
            VALUES (:v,:t,:lang,:m,:dlang,:lprob)
        """
            ),
            {
                "v": ctx.video_id,
                "t": full_text,
                "lang": ctx.detected_language or "en",
                "m": deps.settings.WHISPER_MODEL,
                "dlang": ctx.detected_language,
                "lprob": ctx.language_probability,
            },
        )

        deps.logger.info("Inserting segments", extra={"segment_count": len(ctx.diar_segments)})
        for s in ctx.diar_segments:
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
                    "v": ctx.video_id,
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

        blocks = build_transcript_blocks(
            [
                TranscriptSegment(
                    start_ms=int(s["start"] * 1000),
                    end_ms=int(s["end"] * 1000),
                    text=s["text"],
                    speaker_label=s.get("speaker"),
                )
                for s in ctx.diar_segments
            ]
        )
        deps.replace_transcript_blocks(conn, ctx.video_id, blocks)
        deps.logger.info("Marking video as completed")
        conn.execute(
            text(
                """
                UPDATE videos
                SET state='completed', error=NULL, diarization_state=:ds, updated_at=now()
                WHERE id=:i
                """
            ),
            {"i": ctx.video_id, "ds": ctx.diarization_state},
        )
        refresh_job_state(conn, ctx.job_id)


def _cleanup(ctx: VideoPipelineContext, deps: NativePipelineDependencies) -> None:
    if not getattr(deps.settings, "CLEANUP_AFTER_PROCESS", False):
        return

    try:
        removed: list[str] = []
        preserve_wav_for_diarization = (
            deps.settings.ENABLE_DIARIZATION and not deps.settings.DIARIZATION_INLINE and ctx.diarization_state == "pending"
        )
        if getattr(deps.settings, "CLEANUP_DELETE_CHUNKS", False):
            for p in ctx.work_dir.glob("chunk_*.wav"):
                p.unlink(missing_ok=True)
                removed.append(p.name)
        if getattr(deps.settings, "CLEANUP_DELETE_WAV", False) and not preserve_wav_for_diarization and ctx.wav_path and ctx.wav_path.exists():
            ctx.wav_path.unlink(missing_ok=True)
            removed.append(Path(ctx.wav_path).name)
        if getattr(deps.settings, "CLEANUP_DELETE_RAW", False) and ctx.raw_path and ctx.raw_path.exists():
            ctx.raw_path.unlink(missing_ok=True)
            removed.append(Path(ctx.raw_path).name)
        if getattr(deps.settings, "CLEANUP_DELETE_DIR_IF_EMPTY", False):
            try:
                next(ctx.work_dir.iterdir())
            except StopIteration:
                ctx.work_dir.rmdir()
                removed.append(f"dir:{ctx.work_dir.name}")
        deps.logger.info("Cleanup completed", extra={"removed_files": ", ".join(removed) if removed else "none"})
    except Exception as e:
        deps.logger.warning("Cleanup encountered an error", extra={"error": str(e)})


def process_video(engine, video_id, *, workdir: Path = WORKDIR, deps: NativePipelineDependencies | None = None) -> int:
    deps = deps or NativePipelineDependencies()
    t0 = time.time()
    deps.logger.info("Video processing started")

    ctx = _load_video_context(engine, video_id, workdir=workdir, deps=deps)
    _enrich_source_metadata(ctx, deps)
    _download_and_transcode(ctx, deps)
    _load_job_meta_and_quality_settings(ctx, deps)
    _transcribe_chunks(ctx, deps)
    _apply_diarization(ctx, deps)
    _apply_custom_vocabulary(ctx, deps)
    _persist_transcript(ctx, deps)
    _cleanup(ctx, deps)

    deps.logger.info(
        "Video processing completed successfully",
        extra={"total_duration_seconds": round(time.time() - t0, 2)},
    )
    return len(ctx.diar_segments)


def _parse_iso_date(value: Any) -> Any:
    from datetime import datetime, timezone

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


def _metadata_channel_name(metadata: dict[str, Any], fallback: str | None = None) -> str | None:
    value = metadata.get("uploader") or metadata.get("channel") or metadata.get("channel_name") or metadata.get("uploader_id") or fallback
    if not value:
        return None
    title = str(value).strip()
    if title.endswith(" - Videos"):
        title = title[: -len(" - Videos")].strip()
    return title or None


def _metadata_uploaded_at(metadata: dict[str, Any]):
    upload_date = _parse_iso_date(metadata.get("upload_date"))
    if upload_date:
        return upload_date
    timestamp = metadata.get("timestamp") or metadata.get("release_timestamp")
    if timestamp is not None:
        try:
            from datetime import datetime, timezone

            return datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
    return _parse_iso_date(metadata.get("release_date"))
