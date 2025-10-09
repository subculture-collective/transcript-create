# Admin: Set user plan
# Transcript Create

End-to-end pipeline for:

1. Accepting YouTube URL (single video or entire channel)
2. Downloading and converting audio to 16 kHz mono WAV
3. Chunking long audio
4. Transcribing with Whisper (ROCm GPU) via `faster-whisper`
5. Speaker diarization with `pyannote.audio`
6. Aligning speakers to Whisper segments
7. Persisting full transcript and segments into PostgreSQL
8. Querying status and transcript via FastAPI

## Architecture

-   **API**: FastAPI (`/jobs`, `/jobs/{id}`, `/videos/{video_id}/transcript`)
-   **Queue**: PostgreSQL tables (`jobs`, `videos`) using `SELECT ... FOR UPDATE SKIP LOCKED` for job locking.
-   **Worker**: Polls pending videos, processes pipeline stages, updates states.
-   **Storage**: PostgreSQL for metadata, transcripts, segments. (Audio files stored on a mounted volume at `/data` inside container.)
-   **Models**: `faster-whisper` large-v3, `pyannote/speaker-diarization`.

## Database Schema

See `sql/schema.sql`.

Apply schema locally:

```bash
psql $DATABASE_URL -f sql/schema.sql
```

## Environment

Create `.env` from example:

```bash
cp .env.example .env
# Edit HF_TOKEN for pyannote access
```

### Environment variables overview

Backend (.env):

- Core/worker
  - DATABASE_URL: Postgres URL (with psycopg driver)
  - HF_TOKEN: Optional, enables diarization models
  - WHISPER_MODEL: Model name (e.g., large-v3)
  - WHISPER_BACKEND: faster-whisper (default) or whisper
  - CHUNK_SECONDS: Chunk size for long audio (seconds)
  - MAX_PARALLEL_JOBS: Concurrency in worker
  - ROCM: true to enable ROCm-specific behavior in Docker image
  - CLEANUP_*: Cleanup toggles for media artifacts
- Search
  - SEARCH_BACKEND: postgres or opensearch
  - OPENSEARCH_URL, OPENSEARCH_INDEX_NATIVE, OPENSEARCH_INDEX_YOUTUBE
  - OPENSEARCH_USER, OPENSEARCH_PASSWORD (if security enabled)
- API/Frontend integration
  - FRONTEND_ORIGIN: e.g., http://localhost:5173 for dev CORS
  - SESSION_SECRET: Random string for session cookie signing
  - ADMIN_EMAILS: Comma-separated admin emails for /admin
- OAuth (Google)
  - OAUTH_GOOGLE_CLIENT_ID, OAUTH_GOOGLE_CLIENT_SECRET
  - OAUTH_GOOGLE_REDIRECT_URI: e.g., http://localhost:8000/auth/callback/google
 - OAuth (Twitch)
  - OAUTH_TWITCH_CLIENT_ID, OAUTH_TWITCH_CLIENT_SECRET
  - OAUTH_TWITCH_REDIRECT_URI: e.g., http://localhost:8000/auth/callback/twitch

Frontend (frontend/.env):

- VITE_API_BASE: Override API base URL for the web app (optional; defaults to http://localhost:8000 in dev)

## Running Locally (Host Python)

Install dependencies (recommend venv):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run API:

```bash
uvicorn app.main:app --reload --port 8000
```

Run worker:

```bash
python -m worker.loop
```

## Docker (ROCm)

Build image:

```bash
docker build -t transcript-create:latest .
```

Run API container (mount data + pass devices):

```bash
docker run --rm -it \
  --device /dev/kfd --device /dev/dri --group-add video \
  --env-file .env \
  -v $(pwd)/data:/data \
  -p 8000:8000 \
  transcript-create:latest
```

Start worker (second container sharing volume & env):

```bash
docker run --rm -it \
  --device /dev/kfd --device /dev/dri --group-add video \
  --env-file .env \
  -v $(pwd)/data:/data \
  transcript-create:latest \
  python -m worker.loop
```

### Docker Compose (recommended)

Start the full stack (PostgreSQL, API, worker) with ROCm device passthrough:

```bash
docker compose build
docker compose up -d
```

The API will be at <http://localhost:8000> and the database at db:5432 inside the network. Volume `./data` is mounted at `/data` inside the containers. The schema is applied automatically on first DB startup.

If your host ROCm version isn’t 6.0, set the build arg when building:

```bash
docker compose build --build-arg ROCM_WHEEL_INDEX=https://download.pytorch.org/whl/rocm6.1
docker compose up -d
```

Check logs:

```bash
docker compose logs -f api worker db
```

## API Usage
# Admin: Set user plan

Admins can set a user's plan to free or pro:

POST /admin/users/{user_id}/plan

Body:

{ "plan": "pro" }  # or "free"

## Billing (Stripe)

- POST `/billing/checkout-session` → returns Checkout URL
- GET `/billing/portal` → returns Customer Portal URL
- POST `/stripe/webhook` → handles subscription lifecycle

Events:
- checkout.session.completed, customer.subscription.created/updated: plan set to Pro when status is active or trialing.
- customer.subscription.deleted: plan set to Free.

Configure `.env` with STRIPE_API_KEY, STRIPE_WEBHOOK_SECRET, and price IDs. Success/cancel URLs default to the Pricing page unless overridden.


Create single video job:

```bash
curl -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=VIDEOID","kind":"single"}'
```

Check job:

```bash
curl http://localhost:8000/jobs/JOB_UUID
```

Transcript:

```bash
curl http://localhost:8000/videos/VIDEO_UUID/transcript
```

YouTube auto-captions (if available):

```bash
# JSON (merged segments with speaker if diarized)
curl http://localhost:8000/videos/VIDEO_UUID/youtube-transcript

# SRT and VTT exports
curl http://localhost:8000/videos/VIDEO_UUID/youtube-transcript.srt
curl http://localhost:8000/videos/VIDEO_UUID/youtube-transcript.vtt
```

## Long Video Chunking

Configured via `CHUNK_SECONDS` (default 900). Each chunk transcribed; timestamps offset and merged. Diarization runs once on full WAV for coherent speakers.

## Notes / Next Steps

-   Add retry/backoff logic per stage (currently single attempt)
-   Add language auto-detection (we assume English now)
-   Cache pyannote model across processes (presently per-process load)
-   Observability: add logging + metrics
-   Security: validate input URLs and limit channel expansion size
-   Consider using migrations tool (Alembic) instead of raw SQL for evolutions

### Force GPU mode for faster-whisper

If you want to guarantee the model runs on GPU (CUDA or ROCm HIP) and never fall back to CPU, set:

```env
FORCE_GPU=true
# Optionally tune the order we try backends and compute types:
GPU_DEVICE_PREFERENCE=cuda,hip
GPU_COMPUTE_TYPES=float16,int8_float16,bfloat16,float32
# And allow model size fallbacks to reduce VRAM pressure:
GPU_MODEL_FALLBACKS=large-v3,medium,small,base,tiny
```

Behavior:

-   The worker will try each combination of backend and compute type in order for the primary `WHISPER_MODEL`.
-   If loading fails (e.g., out of memory), it tries the next model in `GPU_MODEL_FALLBACKS`.
-   If none of the GPU combinations succeed, the job fails fast instead of silently using CPU.

## YouTube Auto Captions Ingestion

This project automatically fetches YouTube auto-captions (when available) as an early pre-processing step. Captions are stored separately from native Whisper transcripts so you can compare or search either source.

- Tables: `youtube_transcripts` (one per video, with `full_text`) and `youtube_segments` (one per caption segment).
- Worker fetches JSON3 captions first, falling back to VTT; both are normalized into segments with `start_ms`, `end_ms`, and `text`.
- Endpoints: see the API Usage section above for JSON/SRT/VTT routes.

Backfill captions for existing videos:

```bash
python scripts/backfill_youtube_captions.py --batch 200
```

Idempotent: it only inserts when missing (or replaces cleanly per video).

## Search Backends (Postgres FTS or OpenSearch)

You can search across native Whisper segments or YouTube auto-captions via a single endpoint:

```bash
GET /search?q=your+query&source=native|youtube
```

Two interchangeable backends are supported and selected via `.env`:

- `SEARCH_BACKEND=postgres` uses PostgreSQL FTS with `tsvector` columns, triggers, and GIN indexes.
- `SEARCH_BACKEND=opensearch` uses OpenSearch with rich analyzers (English stem/stop, synonyms, n-grams, edge n-grams, shingles) and highlighting.

### Postgres FTS setup

FTS schema is defined in `sql/schema.sql` and applied automatically on first compose up. If applying manually, run:

```bash
psql $DATABASE_URL -f sql/schema.sql
```

Backfill `tsvector` for existing rows:

```bash
python scripts/backfill_fts.py --batch 500 --until-empty
```

### OpenSearch (local, CPU-only)

Docker Compose includes OpenSearch and Dashboards for local development with security disabled. Start as part of the stack:

```bash
docker compose up -d
```

Relevant `.env` settings (defaults exist):

```env
SEARCH_BACKEND=opensearch
OPENSEARCH_URL=http://localhost:9200
OPENSEARCH_INDEX_NATIVE=segments
OPENSEARCH_INDEX_YOUTUBE=youtube_segments
```

Synonyms are managed in `config/opensearch/analysis/synonyms.txt` and mounted into the container; indices reference this file via `synonyms_path`.

Index or reindex data from Postgres into OpenSearch:

```bash
python scripts/opensearch_indexer.py \
  --recreate \
  --batch 5000 \
  --bulk-docs 1000 \
  --refresh-off
```

Notes:

- `--recreate` drops and recreates indices with the latest analyzers/mappings.
- `--bulk-docs` controls the size of each bulk request; tune to avoid 429 throttling.
- `--refresh-off` speeds up bulk loads by disabling refresh and making translog asynchronous during indexing; the tool restores defaults afterwards.

With OpenSearch selected, `/search` automatically runs boosted multi-field queries (including phrase and prefix variants) and returns highlighted matches.

## License

TBD
