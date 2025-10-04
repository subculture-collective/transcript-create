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

## Long Video Chunking

Configured via `CHUNK_SECONDS` (default 900). Each chunk transcribed; timestamps offset and merged. Diarization runs once on full WAV for coherent speakers.

## Notes / Next Steps

-   Add retry/backoff logic per stage (currently single attempt)
-   Add SRT/VTT export endpoints
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

## License

TBD
