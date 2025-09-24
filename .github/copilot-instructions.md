# Copilot Instructions for transcript-create

Purpose

- Local, GPU-accelerated pipeline to transcribe long YouTube livestreams (8–10h). Output: canonical transcript JSON + snippet JSONL for a separate indexing repo.

Architecture (big picture)

- Ingest: Fetch YouTube metadata and download audio (yt-dlp) → normalization via ffmpeg (TBD based on ASR engine).
- Segment: Split into deterministic chunks (e.g., 30min) with small overlap; keep a manifest with global offsets.
- Transcribe: WhisperX (self-hosted, GPU) per chunk for word-level timestamps; merge preserving global times.
- Export: Emit `artifacts/<videoId>/transcript.json` + `snippets.jsonl` for downstream indexer.
- Persist: Store video + run metadata in PostgreSQL; large artifacts on filesystem.
- Diarization: v1.1 (speaker labels later).

Runtime & environment

- GPU priority: AMD (ROCm) on Linux via Docker is preferred; default target ROCm 6.0 (bump if host drivers require). NVIDIA (CUDA) optional; CPU fallback allowed for dev.
- Container-first: maintain images for ROCm and CUDA. Orchestrate from TypeScript (child_process → `docker run`).
- Python stays inside the container; TypeScript orchestrates on host. Avoid per-dev Python setup.
- macOS development is fine for orchestration; heavy ASR runs execute in the GPU container host.

Key files/directories (expected)

- `src/cli/` – small Node CLI entry points (`ingest`, `chunk`, `transcribe`, `export`).
- `src/pipeline/` – pure TS orchestration logic with typed inputs/outputs.
- `python/` – WhisperX runner invoked by TS (JSON in/out via stdout/files).
- `artifacts/<videoId>/` – audio, chunks, transcript.json, snippets.jsonl, manifest.json.
- `db/` – migrations (PostgreSQL) and minimal SQL queries.
- `docker/` – ROCm/CUDA Dockerfiles; `compose.yaml` for Postgres + runner.
- `.env` – configuration (DB URL, paths); include `.env.example` and do not commit secrets.

Canonical output (shape summary)

- `transcript.json` contains: source metadata, processing config, segments[{startSec,endSec,text}], words[{startSec,endSec,text}], snippets[{snippetId,startSec,endSec,text}]. Times in seconds (float, UTC reference).

Agent workflow (small, idempotent steps)

1. Scaffold TS project + minimal CLI; add `.env`, logging, strict types.
2. Ingest: given `videoId|url`, write DB record and download audio to `artifacts/<videoId>/audio.wav`.
3. Chunking: deterministic splits + `manifest.json` with [globalStart, globalEnd]; WAV/FLAC chunks.
4. Transcription: TS → Docker WhisperX per chunk; collect JSON with word timestamps.
5. Merge & Export: compose final `transcript.json` and `snippets.jsonl` windows.
6. DB: migrations for `videos`, `runs`, `artifacts`; record each run.
7. Reliability: retries, caching, resume (skip existing files unless `--force`).

Conventions & patterns

- TS orchestrates; Python does ASR. Exchange via deterministic file paths and JSON.
- Deterministic paths enable resume/idempotency. Avoid randomness in filenames.
- Pure functions for merge/export; side effects isolated at FS/DB edges.
- All media times in seconds (float). Use UTC timestamps for metadata.

Dev flow (expected)

- Setup: install `ffmpeg` + `yt-dlp`. Build GPU Docker image (ROCm or CUDA). Start Postgres via `docker compose`.
- Run end-to-end: `node ./dist/cli/transcribe --video <id|url>` (CLI calls into dockerized ASR).
- Iterate per-step using individual CLIs: `ingest`, `chunk`, `transcribe`, `export`.

Safety & boundaries

- No SaaS uploads for MVP (local processing only). Keep PII local.
- Do not overwrite artifacts; append or version on re-runs. Fail if outputs exist unless `--force`.

Open items (track as TODOs, don’t guess)

- Normalization profile (ffmpeg) depends on chosen ASR/aligner; decide during ASR image build.
- Finalize chunk size/overlap and snippet window defaults after first long-run test.
- WhisperX image targets: ROCm (AMD) and CUDA (NVIDIA); pin versions for reproducibility. Postgres schema fields.
