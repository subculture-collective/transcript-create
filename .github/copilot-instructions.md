# Copilot instructions for transcript-create

This repository provides an end-to-end pipeline to create transcripts from YouTube videos or channels using FastAPI + PostgreSQL + a background worker that runs Whisper (ROCm GPU) and optional pyannote diarization.

## Architecture overview
- API (FastAPI): `app/main.py` exposes:
  - POST `/jobs` to enqueue a job (single or channel). Uses `app/crud.py` and `sqlalchemy`.
  - GET `/jobs/{id}` to check status.
  - GET `/videos/{video_id}/transcript` to fetch merged, diarized segments.
- Database: PostgreSQL with schema in `sql/schema.sql`. Core tables: `jobs`, `videos`, `transcripts`, `segments`. States are managed via a `job_state` enum.
- Worker: `worker/loop.py` repeatedly:
  - Expands jobs into `videos` (single or channel) using yt-dlp JSON metadata.
  - Picks one pending video with `FOR UPDATE SKIP LOCKED` and runs `worker/pipeline.process_video`.
- Processing pipeline (`worker/pipeline.py`):
  1) Download audio with yt-dlp (`worker/audio.download_audio`).
  2) Convert to mono 16 kHz WAV via ffmpeg (`ensure_wav_16k`).
  3) Chunk long audio (`chunk_audio`) using `CHUNK_SECONDS` setting.
  4) Transcribe each chunk using Whisper (`worker/whisper_runner.transcribe_chunk`).
  5) Optional speaker diarization + alignment (`worker/diarize.diarize_and_align`) if `HF_TOKEN` set.
  6) Persist: insert one row in `transcripts` and many rows in `segments`; mark video `completed`.

Why this structure: Database-backed job/queue with SKIP LOCKED enables simple horizontal scaling of workers without extra infra. Chunking controls memory/runtime; diarization post-process keeps speaker labels coherent across the whole audio.

## Key settings and conventions
- Settings live in `app/settings.py` and are read from `.env` via `pydantic-settings`.
  - `WHISPER_BACKEND` = `faster-whisper` (CT2) or `whisper` (PyTorch). Default is CT2.
  - ROCm-friendly GPU control: `FORCE_GPU`, `GPU_DEVICE_PREFERENCE`, `GPU_COMPUTE_TYPES`, `GPU_MODEL_FALLBACKS`.
  - Chunking: `CHUNK_SECONDS` (default 900).
  - Cleanup toggles remove large media after success.
  - `RESCUE_STUCK_AFTER_SECONDS` requeues non-terminal videos that stall.
- Worker selects one pending video at a time; status transitions: `downloading` → `transcoding` → `transcribing` → `completed` (or `failed`). Jobs are "expanded" into `videos` first.
- Diarization: if `HF_TOKEN` missing or `pyannote.audio` unavailable, we return Whisper segments unchanged and still complete successfully.
- Reprocessing: Worker auto-requeues completed videos when `settings.WHISPER_MODEL` ranks higher than prior `transcripts.model`.

## Build and run workflows
- Local (host):
  - API: `uvicorn app.main:app --reload --port 8000`
  - Worker: `python -m worker.loop`
- Docker (ROCm): build from `Dockerfile`; compose stack with `docker-compose.yml`.
  - Full stack: `docker compose build && docker compose up -d`
  - Recreate GPU worker: VS Code task "Recreate worker (whisper ROCm)" or `docker compose up -d --force-recreate worker`.
  - Logs: `docker compose logs -f api worker db`
- DB schema: auto-applied on first Postgres start via compose; or apply manually with `psql $DATABASE_URL -f sql/schema.sql`.

## Coding patterns to follow
- DB access uses SQLAlchemy Core with parameterized `text()` and manual transactions (`engine.begin()` or `SessionLocal`). See `app/crud.py`, `worker/pipeline.py`.
- Job/video locking: always use `FOR UPDATE SKIP LOCKED` when selecting work to avoid contention.
- File I/O: all media lives under `/data/<video_uuid>` (volume-mounted). Use `worker/pipeline.WORKDIR` and `pathlib.Path`.
- Transcription API shapes:
  - Whisper CT2: iterate `(segments, info)`; map to dict with `start`, `end`, `text`, `avg_logprob`, `temperature`, `token_count`, `confidence`.
  - PyTorch whisper: `model.transcribe(...)["segments"]` with similar mapping; on ROCm fault signatures, code falls back to CT2 automatically.
- Diarization assigns human-friendly labels like "Speaker 1" ordered by first appearance; both `speaker` and `speaker_label` are set on segment dicts.

## Integration specifics
- YouTube metadata extraction uses `yt-dlp -J` (single) or `--flat-playlist -J` (channel). Insert `videos(job_id, youtube_id, idx, title, duration_seconds)` once per entry.
- State updates must update `updated_at=now()` consistently.
- API responses:
  - `JobStatus` schema in `app/schemas.py` maps DB row fields directly.
  - `TranscriptResponse` returns `segments` sorted by `start_ms`.

## Useful file references
- API: `app/main.py`, `app/crud.py`, `app/db.py`, `app/schemas.py`, `app/settings.py`
- Worker: `worker/loop.py`, `worker/pipeline.py`, `worker/audio.py`, `worker/whisper_runner.py`, `worker/diarize.py`
- Infra: `docker-compose.yml`, `Dockerfile`, `sql/schema.sql`, `scripts/run_worker.sh`

## Make agents effective
- Prefer updating `app/settings.py` for new env flags or behavior toggles.
- When adding new pipeline stages, ensure idempotency and clear state progression; clean existing transcript/segments before reinserting on reprocess.
- Keep long-running calls (yt-dlp, ffmpeg, model loads) logged at INFO with concise command echoes.
- If adding new endpoints, stick to Pydantic response models and use `crud` helpers for DB access where possible.
