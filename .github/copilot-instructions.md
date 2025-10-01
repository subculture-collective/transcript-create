# Copilot Instructions for transcript-create

## Goal

Local pipeline to transcribe long YouTube livestreams. TypeScript orchestrates; WhisperX runs in Docker. Outputs: `artifacts/<videoId>/transcript.json` and `snippets.jsonl` for downstream indexing.

## Architecture & Data Flow

Sequential pipeline: **ingest → chunk → transcribe → export**

-   **Ingest** (`src/pipeline/ingest.ts`): Extract `videoId` via `src/pipeline/ids.ts`, create `artifacts/<videoId>/`, write `source.json`. Expects `audio.wav` file. Use `npm run ingest -- --video <id|url> --dry-run`.
-   **Chunk** (`src/pipeline/chunk.ts`): Split audio into overlapping chunks, produce `manifest.json` with `ChunkManifest`. Use `npm run chunk -- --video <id> [--audio path] --dry-run`.
-   **Transcribe** (`src/pipeline/transcribe.ts`): Process chunks via WhisperX Docker containers, merge to unified `TranscriptJson`. Entry: `python/whisperx_runner.py`. Use `npm run transcribe -- --video <id|url> --dry-run` (runs full pipeline).
-   **Export** (`src/pipeline/export.ts`): Generate sliding-window `snippets.jsonl` from transcript. Use `npm run export -- --transcript <path> --out <dir>`.

## Critical Data Contracts (`src/pipeline/types.ts`)

-   **TranscriptJson**: `{ videoId, source, processing, segments[], words[], snippets[] }` - all times in seconds (float)
-   **ChunkManifest**: `{ videoId, audioPath, chunkSec, overlapSec, chunks[{chunkIndex,path,globalStart,globalEnd}] }`
-   **Snippet IDs**: Format `<videoId>-00012-<ms>` for indexing

## Key Architecture Patterns

-   **File-based orchestration**: TS writes JSON configs/manifests; Python reads them via Docker volume mounts
-   **Deterministic paths**: `artifacts/<videoId>/` structure enables idempotency and resume capability
-   **Type-safe boundaries**: All cross-language contracts defined in `src/pipeline/types.ts`

## Development Workflow

```bash
# Setup (first time)
npm install
docker compose -f docker/compose.yaml up -d db
npm run build && npm run migrate

# Development (use ts-node for faster iteration)
npm run transcribe -- --video <id|url> --dry-run  # Full pipeline test
npm run migrate:dev  # Apply new migrations without build step
```

## Environment Configuration (`src/pipeline/env.ts`)

All settings have defaults; override via `.env` file or CLI flags:

-   **DATABASE_URL**: `postgres://postgres:postgres@localhost:5432/transcripts`
-   **ARTIFACTS_ROOT**: `artifacts` (filesystem base path)
-   **CHUNK_SEC/OVERLAP_SEC**: `1800`/`8` (chunk size in seconds)
-   **WHISPERX_IMAGE**: Docker image name; if empty, uses local `python/whisperx_runner.py`
-   **DOCKER_ADDITIONAL_ARGS**: Space-separated args for GPU pass-through (`--device /dev/kfd --device /dev/dri --group-add video`)

## Database Schema (`db/migrations/0001_init.sql`)

-   **videos**: Core metadata (id, url, title, duration)
-   **runs**: Processing attempts (video_id → engine, status, config)
-   **artifacts**: Filesystem tracking (video_id → path, kind)
-   **\_migrations**: Auto-managed by `src/db/migrate.ts`

## Docker & GPU Integration

-   **ROCm preferred**: `docker/whisperx.rocm.Dockerfile` (AMD ROCm 6.0)
-   **CPU fallback**: `docker/whisperx.cpu.Dockerfile` for debugging
-   **Volume strategy**: Mount `ARTIFACTS_ROOT` at same absolute path in container
-   **GPU access**: Use `DOCKER_ADDITIONAL_ARGS` for device mapping and user groups

## Critical Patterns

-   **Idempotency**: Skip existing artifacts unless `--force`; enables safe pipeline restarts
-   **Language boundaries**: TS writes JSON configs → Python reads via volume mounts → TS processes results
-   **Pure functions**: Keep side-effects (FS/DB writes) at pipeline edges; core logic should be testable
-   **Absolute paths**: All artifact paths written as absolute to simplify container orchestration

## Implementation Status & TODOs

-   **Working**: Full dry-run pipeline, database migrations, type-safe contracts
-   **In progress**: Docker orchestration for WhisperX containers, per-chunk JSON merging
-   **Pending**: ffmpeg normalization, production chunk/overlap tuning, Docker image pinning, speaker diarization`

## Environment Configuration (`src/pipeline/env.ts`)

All settings have defaults; override via `.env` file or CLI flags:

-   **DATABASE_URL**: `postgres://postgres:postgres@localhost:5432/transcripts`
-   **ARTIFACTS_ROOT**: `artifacts` (filesystem base path)
-   **CHUNK_SEC/OVERLAP_SEC**: `1800`/`8` (chunk size in seconds)
-   **WHISPERX_IMAGE**: Docker image name; if empty, uses local `python/whisperx_runner.py`
-   **DOCKER_ADDITIONAL_ARGS**: Space-separated args for GPU pass-through (`--device /dev/kfd --device /dev/dri --group-add video`)

## Database Schema (`db/migrations/0001_init.sql`)

-   **videos**: Core metadata (id, url, title, duration)
-   **runs**: Processing attempts (video_id → engine, status, config)
-   **artifacts**: Filesystem tracking (video_id → path, kind)
-   **\_migrations**: Auto-managed by `src/db/migrate.ts`

## Docker & GPU Integration

-   **ROCm preferred**: `docker/whisperx.rocm.Dockerfile` (AMD ROCm 6.0)
-   **CPU fallback**: `docker/whisperx.cpu.Dockerfile` for debugging
-   **Volume strategy**: Mount `ARTIFACTS_ROOT` at same absolute path in container
-   **GPU access**: Use `DOCKER_ADDITIONAL_ARGS` for device mapping and user groups

## Critical Patterns

-   **Idempotency**: Skip existing artifacts unless `--force`; enables safe pipeline restarts
-   **Language boundaries**: TS writes JSON configs → Python reads via volume mounts → TS processes results
-   **Pure functions**: Keep side-effects (FS/DB writes) at pipeline edges; core logic should be testable
-   **Absolute paths**: All artifact paths written as absolute to simplify container orchestrationscript-create

## Goal

Local pipeline to transcribe long YouTube livestreams. TypeScript orchestrates; WhisperX runs in Docker. Outputs: `artifacts/<videoId>/transcript.json` and `snippets.jsonl` for downstream indexing.

## Architecture & Data Flow

Sequential pipeline: **ingest → chunk → transcribe → export**

-   **Ingest** (`src/pipeline/ingest.ts`): Extract `videoId` via `src/pipeline/ids.ts`, create `artifacts/<videoId>/`, write `source.json`. Expects `audio.wav` file. Use `npm run ingest -- --video <id|url> --dry-run`.
-   **Chunk** (`src/pipeline/chunk.ts`): Split audio into overlapping chunks, produce `manifest.json` with `ChunkManifest`. Use `npm run chunk -- --video <id> [--audio path] --dry-run`.
-   **Transcribe** (`src/pipeline/transcribe.ts`): Process chunks via WhisperX Docker containers, merge to unified `TranscriptJson`. Entry: `python/whisperx_runner.py`. Use `npm run transcribe -- --video <id|url> --dry-run` (runs full pipeline).
-   **Export** (`src/pipeline/export.ts`): Generate sliding-window `snippets.jsonl` from transcript. Use `npm run export -- --transcript <path> --out <dir>`.

## Critical Data Contracts (`src/pipeline/types.ts`)

-   **TranscriptJson**: `{ videoId, source, processing, segments[], words[], snippets[] }` - all times in seconds (float)
-   **ChunkManifest**: `{ videoId, audioPath, chunkSec, overlapSec, chunks[{chunkIndex,path,globalStart,globalEnd}] }`
-   **Snippet IDs**: Format `<videoId>-00012-<ms>` for indexing

## Key Architecture Patterns

-   **File-based orchestration**: TS writes JSON configs/manifests; Python reads them via Docker volume mounts
-   **Deterministic paths**: `artifacts/<videoId>/` structure enables idempotency and resume capability
-   **Type-safe boundaries**: All cross-language contracts defined in `src/pipeline/types.ts`

Environment & configuration (`src/pipeline/env.ts`, `.env.example`)

-   DATABASE_URL (default `postgres://postgres:postgres@localhost:5432/transcripts`), ARTIFACTS_ROOT (`artifacts`), CHUNK_SEC (`1800`), OVERLAP_SEC (`8`), FORCE (`false`). CLI flags can override (e.g., `--dry-run`, `--force`).
-   Optional: WHISPERX_IMAGE to run per-chunk via Docker; if unset, falls back to local `python/whisperx_runner.py`. DOCKER_BIN can override the docker binary.

Database workflow

-   Start DB: `docker compose -f docker/compose.yaml up -d db`.
-   Apply migrations: `npm run build && npm run migrate` (or `npm run migrate:dev` for ts-node).
-   Tables: `videos`, `runs`, `artifacts`; `_migrations` tracks applied files.

Conventions & patterns

-   Deterministic paths under `artifacts/<videoId>/` enable resume/idempotency. Skip existing unless `--force`.
-   TS orchestrates; Python stays inside the container. Exchange via files/JSON on shared volumes.
-   Keep side-effects at FS/DB edges; merge/export logic should be pure and typed.

Docker & GPUs

-   Preferred: AMD ROCm (6.0). CPU image available for debugging. Orchestration will `docker run` per chunk with volume mounts to `artifacts/` and device pass-through as needed (see comments in Dockerfiles and `compose.yaml`).
    -   Paths: chunk files are written with absolute paths to simplify container volume mapping; mount the `ARTIFACTS_ROOT` at the same absolute path into the container.

Safety & boundaries

-   Local-only (no SaaS uploads). Don’t overwrite artifacts; fail or require `--force`. Diarization planned later.

Open items (from codebase TODOs)

-   ffmpeg normalization profile; finalize chunk size/overlap and snippet window; implement Docker orchestration and merging of per-chunk WhisperX JSON; pin image versions.
