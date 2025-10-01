# transcript-create

Local pipeline to produce canonical transcripts from (very) long YouTube videos / livestreams.

Core pipeline (sequential): ingest -> chunk -> transcribe -> export.

-   TypeScript orchestrates filesystem + DB + docker.
-   WhisperX runs inside a container (ROCm for AMD GPUs, or CPU fallback) to perform ASR + alignment.
-   Artifacts live under `artifacts/<videoId>/` (idempotent, resumable). Database keeps lightweight metadata.

## Quick Start

Prereqs: Docker, Node 18+, ffmpeg, Postgres (docker compose), optional yt-dlp (binary or Python package).

1. Install deps: `npm install`
2. Start DB: `docker compose -f docker/compose.yaml up -d db`
3. Build: `npm run build`
4. Migrate: `npm run migrate`
5. Dry run a single video: `npm run transcribe -- --video <id|url> --dry-run`

Produces (dry run):

```text
artifacts/<videoId>/
  audio.wav (empty placeholder)
  source.json
  manifest.json
  transcript.json (empty arrays)
  snippets.jsonl
```

## Real Transcription (Single Video)

```bash
npm run transcribe -- --video <id|url>
```

Flags:

-   `--dry-run` generate empty artifacts only.
-   `--force` re-download audio and re-run all stages even if outputs exist.

Environment (override via `.env` or process env): see `src/pipeline/env.ts`.

Key vars:

-   `ARTIFACTS_ROOT` (default `artifacts`)
-   `CHUNK_SEC` / `OVERLAP_SEC` (default 1800s / 8s)
-   `WHISPERX_IMAGE` (required for docker execution)
-   `DOCKER_ADDITIONAL_ARGS` (e.g. `--device /dev/kfd --device /dev/dri --group-add video` for AMD)
-   `WHISPERX_FORCE_CPU=1` force CPU path even if GPU devices passed through
-   `YTDLP_BIN` and/or `YTDLP_PYTHON_BIN` for custom yt-dlp resolution

## Channel Transcription

Batch process every video found on a channel (YouTube channel URL or ID). The CLI automatically:

-   Lists videos via layered yt-dlp fallback: configured binary -> `yt-dlp` -> `<python> -m yt_dlp` (custom) -> `python3 -m yt_dlp`.
-   Skips any video whose `artifacts/<id>/transcript.json` already exists unless `--force`.
-   Supports bounded concurrency.
-   Summarizes results (processed / skipped / failed).

Usage:

```bash
npm run channel -- --channel <channelId|url> [--limit N] [--concurrency K] [--force] [--dry-run]
```

Examples:

-   First pass (dry): `npm run channel -- --channel UCXXXX --limit 3 --dry-run`
-   Real run, 2 at a time: `npm run channel -- --channel UCXXXX --concurrency 2`

Behavior:

-   Concurrency default = 1. Higher values increase I/O & CPU pressure (each video downloads + chunks + spawns WhisperX containers per chunk).
-   Skip logic: presence of `transcript.json` is authoritative that the video finished at least once.
-   Failure of one video does not halt others; errors are logged and counted.

## Resumability & Idempotency

Each stage checks for existing outputs unless `--force` is supplied. This makes the pipeline safe to re-run after interruption.

## CPU vs GPU

Set `WHISPERX_FORCE_CPU=1` to remove device flags and request CPU inference even if GPU devices are available. This is useful when GPU drivers / ROCm stack are unstable.

If using AMD ROCm:

-   Provide an image built from `docker/whisperx.rocm.Dockerfile` with ROCm-compatible PyTorch.
-   Supply device mappings in `DOCKER_ADDITIONAL_ARGS`.
-   Verify container health (the pipeline runs a health probe before chunk processing).

CPU-only:

-   Optionally build `docker/whisperx.cpu.Dockerfile` and set `WHISPERX_IMAGE` to that tag, or just keep using the ROCm image with `WHISPERX_FORCE_CPU`.

## yt-dlp Fallback Chain

For both single video ingest and channel listing the following order is tried until success:

1. Configured `YTDLP_BIN`
2. `yt-dlp`
3. Configured `YTDLP_PYTHON_BIN -m yt_dlp`
4. `python3 -m yt_dlp`

This minimizes setup friction; ensure at least one path works (virtualenv or system install).

## Artifacts Layout

```text
artifacts/<videoId>/
  source.json          # metadata (title, duration, etc.)
  audio.wav            # normalized mono 16k
  manifest.json        # chunk boundaries with global offsets
  chunk_0000.json ...  # per-chunk raw WhisperX output (during run)
  transcript.json      # merged + offset-adjusted transcript
  snippets.jsonl       # sliding window textual snippets
```

## Development Notes

-   Pure logic kept small & testable; cross-language handoff via JSON only.
-   All paths written absolute to simplify docker volume mounts.
-   Per-chunk JSON merge tolerates partial failures (continues merging others).

## Roadmap / TODO (high-level)

-   Optional speaker diarization stage
-   Smarter snippet windowing + semantic scoring
-   Configurable language & model selection per run
-   GPU cache volume (HF model cache) for faster cold starts

## Troubleshooting

Missing yt-dlp: ensure one of the fallback methods is installed.

Container health fails: verify `WHISPERX_IMAGE` tag, device mappings, and that the image contains required models (or allow it to download them). Use `docker run --rm <image> --health` manually for debugging.

Chunk outputs missing: inspect ffmpeg install, confirm `audio.wav` is non-empty; rerun with `--force` if needed.

Slow performance: reduce `CHUNK_SEC` or concurrency; on CPU large models can be prohibitively slow.

Model download interruptions: pre-pull models by running the container with a dummy short audio to populate the cache (mount a persistent volume for cache if needed).

Zero-byte or tiny audio after dry-run: a previous `--dry-run` creates an empty placeholder `audio.wav`. The ingest step now auto-detects 0-byte or <1KB files and re-downloads real audio even without `--force`; a log line `[ingest] Detected empty placeholder audio ...` will appear. If you see many failures citing `Input audio is empty (0 bytes)`, remove affected directories or rerun the channel command (it will repair them on the next pass).
