# Architecture Overview

This document describes the system architecture, component responsibilities, and data flow of Transcript Create.

## Table of Contents

- [High-Level Architecture](#high-level-architecture)
- [Component Responsibilities](#component-responsibilities)
- [Data Flow](#data-flow)
- [Database Schema](#database-schema)
- [Technology Stack](#technology-stack)
- [Design Decisions](#design-decisions)

## High-Level Architecture

Transcript Create follows a microservices-inspired architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│                          Frontend (React)                        │
│              Vite + React + Tailwind + TypeScript                │
│                    http://localhost:5173                         │
└─────────────────────┬───────────────────────────────────────────┘
                      │ HTTP/REST
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│                     API Server (FastAPI)                         │
│                   http://localhost:8000                          │
│  ┌──────────────┬─────────────┬───────────┬──────────────┐     │
│  │ Auth Routes  │ Job Routes  │  Video    │   Search     │     │
│  │              │             │  Routes   │   Routes     │     │
│  ├──────────────┼─────────────┼───────────┼──────────────┤     │
│  │ Billing      │ Admin       │ Favorites │   Export     │     │
│  │ Routes       │ Routes      │  Routes   │   Routes     │     │
│  └──────────────┴─────────────┴───────────┴──────────────┘     │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ├─────────────────┐
                      │                 │
          ┌───────────▼──────┐  ┌───────▼──────────┐
          │   PostgreSQL     │  │   OpenSearch     │
          │   (Primary DB)   │  │   (Optional)     │
          │   Queue + Store  │  │   Search Index   │
          └──────────────────┘  └──────────────────┘
                      ▲
                      │
          ┌───────────┴──────────┐
          │   Worker Process     │
          │   (Python)           │
          │                      │
          │  ┌────────────────┐  │
          │  │ Job Processor  │  │
          │  │ Video Pipeline │  │
          │  │ Whisper Model  │  │
          │  │ Diarization    │  │
          │  └────────────────┘  │
          └──────────────────────┘
                      │
          ┌───────────▼──────────┐
          │  File Storage        │
          │  /data/<video_uuid>/ │
          │  (Audio + Metadata)  │
          └──────────────────────┘
```

## Component Responsibilities

### Frontend (React + Vite)

**Location**: `frontend/`

**Purpose**: User interface for interacting with the transcription service

**Key Features**:
- Search interface with filtering and highlighting
- Video transcript viewer with timestamp deep links
- Export menu (SRT, VTT, JSON, PDF)
- Authentication (OAuth login)
- Billing/upgrade flow with Stripe
- Admin dashboard (for authorized users)

**Tech Stack**:
- Vite for fast development and optimized builds
- React 18 with hooks
- TailwindCSS for styling
- React Router for navigation
- Axios for API calls
- TypeScript for type safety

### API Server (FastAPI)

**Location**: `app/`

**Purpose**: RESTful API for managing jobs, videos, transcripts, and user operations

**Responsibilities**:
- Handle HTTP requests from frontend
- Authentication and authorization (OAuth, session management)
- Job creation and status tracking
- Video metadata and transcript retrieval
- Search orchestration (PostgreSQL FTS or OpenSearch)
- Export generation (SRT, VTT, JSON, PDF)
- Billing integration (Stripe webhooks)
- Admin operations and analytics

**Key Modules**:
- `app/routes/`: Modular router definitions
  - `auth.py`: OAuth login (Google, Twitch), session management
  - `jobs.py`: Job creation and status
  - `videos.py`: Video metadata and transcript access
  - `search.py`: Full-text search across transcripts
  - `exports.py`: Export format generation
  - `billing.py`: Stripe Checkout and Customer Portal
  - `admin.py`: Admin-only analytics and user management
  - `favorites.py`: User favorites management
  - `events.py`: Event logging for analytics
- `app/crud.py`: Database operations with SQLAlchemy
- `app/db.py`: Database connection management
- `app/schemas.py`: Pydantic models for request/response validation
- `app/settings.py`: Configuration via environment variables

**API Patterns**:
- RESTful endpoints with standard HTTP methods
- JSON request/response bodies
- Session-based authentication with cookies
- Error handling with structured JSON responses
- Health check endpoints for load balancers

### Worker Process

**Location**: `worker/`

**Purpose**: Background processing of transcription jobs

**Responsibilities**:
- Poll database for pending videos (using `FOR UPDATE SKIP LOCKED`)
- Download audio from YouTube (yt-dlp)
- Transcode to 16 kHz mono WAV (ffmpeg)
- Chunk long audio for memory management
- Run Whisper transcription (GPU-accelerated)
- Optional speaker diarization (pyannote.audio)
- Merge and align segments
- Update database with results
- Clean up temporary files

**Key Modules**:
- `worker/loop.py`: Main worker loop with job polling
- `worker/pipeline.py`: Orchestrates the full processing pipeline
- `worker/audio.py`: Audio download and preprocessing
- `worker/whisper_runner.py`: Whisper model loading and transcription
- `worker/diarize.py`: Speaker diarization and alignment

**State Transitions**:
```
pending → downloading → transcoding → transcribing → completed
                                                   ↘ failed
```

**Processing Pipeline**:
1. **Expand Jobs**: Convert channel URLs to individual video entries
2. **Select Video**: Pick one pending video with row-level locking
3. **Download**: Use yt-dlp to fetch audio and metadata
4. **Transcode**: Convert to 16 kHz mono WAV
5. **Chunk**: Split long audio into manageable segments
6. **Transcribe**: Run Whisper on each chunk
7. **Diarize** (optional): Identify speakers and align with transcript
8. **Persist**: Save transcript and segments to database
9. **Cleanup**: Remove temporary files (if configured)

### Database (PostgreSQL)

**Location**: SQL schema in `sql/schema.sql`, migrations in `alembic/`

**Purpose**: Primary data store and job queue

**Core Tables**:
- `jobs`: Job metadata and status
- `videos`: Video information, processing state, YouTube metadata
- `transcripts`: Transcript metadata (model, language, duration)
- `segments`: Individual transcript segments with timestamps
- `youtube_captions`: YouTube auto-captions for comparison
- `youtube_caption_segments`: Individual YouTube caption segments
- `users`: User accounts (OAuth)
- `sessions`: Session management
- `favorites`: User-favorited videos
- `events`: Analytics event log

**Queue Mechanism**:
- Workers use `SELECT ... FOR UPDATE SKIP LOCKED` for lock-free parallelism
- Multiple workers can process different videos simultaneously
- No external queue service needed (RabbitMQ, Redis, etc.)

**Search Indexes**:
- PostgreSQL Full-Text Search (GIN indexes)
- Triggers for automatic index updates
- Optional OpenSearch for advanced features

### File Storage

**Location**: `/data/<video_uuid>/` (Docker volume or local directory)

**Purpose**: Store downloaded audio and temporary files

**Contents**:
- `audio.opus` or `audio.m4a`: Original downloaded audio
- `audio.wav`: Transcoded 16 kHz mono WAV
- `audio_chunk_*.wav`: Chunked audio segments
- Metadata files from yt-dlp

**Lifecycle**:
- Created during video processing
- Optionally cleaned up after successful transcription (configurable)
- Persistent across container restarts (via Docker volumes)

### OpenSearch (Optional)

**Purpose**: Advanced search capabilities with highlighting and ranking

**Features**:
- Synonym expansion
- N-gram matching for partial words
- Relevance scoring
- Fast highlighting
- Aggregations and faceting

**Integration**:
- Indexer script: `scripts/opensearch_indexer.py`
- Search backend setting: `SEARCH_BACKEND=opensearch`
- Falls back to PostgreSQL FTS if unavailable

## Data Flow

### Job Creation Flow

```
1. User submits YouTube URL via frontend
   └─> POST /jobs { url, kind }

2. API validates URL and creates job record
   └─> INSERT INTO jobs (url, kind, state='pending')
   └─> Returns job_id to frontend

3. Frontend polls job status
   └─> GET /jobs/{job_id}
   └─> Returns job state + video count

4. Worker expands job into videos (for channels)
   └─> Run yt-dlp --flat-playlist
   └─> INSERT INTO videos (job_id, youtube_id, title, ...)
   └─> UPDATE jobs SET state='expanded'
```

### Video Processing Flow

```
1. Worker polls for pending video
   └─> SELECT * FROM videos 
       WHERE state='pending' 
       ORDER BY created_at 
       FOR UPDATE SKIP LOCKED LIMIT 1

2. Download audio
   └─> yt-dlp downloads to /data/{video_uuid}/
   └─> UPDATE videos SET state='downloading'

3. Transcode audio
   └─> ffmpeg converts to 16kHz mono WAV
   └─> UPDATE videos SET state='transcoding'

4. Transcribe audio
   └─> Chunk audio into segments
   └─> Load Whisper model
   └─> Transcribe each chunk
   └─> UPDATE videos SET state='transcribing'

5. Diarize (optional)
   └─> Run pyannote.audio
   └─> Align speakers with transcript segments

6. Save results
   └─> INSERT INTO transcripts (video_id, model, language, ...)
   └─> INSERT INTO segments (transcript_id, start_ms, end_ms, text, ...)
   └─> UPDATE videos SET state='completed'

7. Cleanup
   └─> Remove temporary files (if CLEANUP_* enabled)
```

### Search Flow

```
1. User enters search query in frontend
   └─> GET /search?q=query&source=native

2. API routes to appropriate search backend

3a. PostgreSQL FTS:
    └─> SELECT * FROM segments
        WHERE search_vector @@ plainto_tsquery('query')
        ORDER BY ts_rank(...)

3b. OpenSearch:
    └─> POST /_search
        └─> Multi-field query with highlighting
        └─> Boosting, synonyms, n-grams

4. API groups results by video
   └─> Returns grouped hits with timestamps and highlights

5. Frontend displays results
   └─> Video list with matching segments
   └─> Click segment → deep link to timestamp
```

### Export Flow

```
1. User clicks export button
   └─> GET /videos/{id}/transcript.srt

2. API checks quotas
   └─> Query user plan and daily export count
   └─> Return 402 if quota exceeded

3. Generate export format
   └─> Fetch segments from database
   └─> Format as SRT/VTT/JSON/PDF
   └─> Log export event

4. Return file
   └─> Content-Disposition: attachment
   └─> Frontend triggers download
```

## Database Schema

### Key Relationships

```
jobs (1) ─────< (N) videos
                      │
                      │ (1)
                      ▼
                 transcripts (1) ─────< (N) segments
                      │
                      │ (1)
                      ▼
                   (N) youtube_captions ─────< (N) youtube_caption_segments

users (1) ─────< (N) sessions
      (1) ─────< (N) favorites ────> (1) videos
      (1) ─────< (N) events
```

### State Management

**Job States**:
- `pending`: Newly created, awaiting expansion
- `expanded`: Videos created, ready for processing
- `processing`: One or more videos are being processed
- `completed`: All videos completed
- `failed`: Job failed during expansion

**Video States**:
- `pending`: Awaiting processing
- `downloading`: Downloading audio
- `transcoding`: Converting audio format
- `transcribing`: Running Whisper
- `completed`: Successfully transcribed
- `failed`: Processing failed

## Technology Stack

### Backend
- **Python 3.11+**: Primary language
- **FastAPI**: High-performance async web framework
- **SQLAlchemy**: ORM and query builder
- **Alembic**: Database migrations
- **Pydantic**: Data validation and settings management
- **psycopg**: PostgreSQL adapter (psycopg3)
- **uvicorn**: ASGI server

### Machine Learning
- **OpenAI Whisper**: Speech recognition model
- **faster-whisper**: Optimized Whisper inference (CTranslate2)
- **PyTorch**: Deep learning framework
- **pyannote.audio**: Speaker diarization (optional)
- **ROCm / CUDA**: GPU acceleration

### Data Processing
- **yt-dlp**: YouTube video/audio download
- **ffmpeg**: Audio/video transcoding
- **NumPy**: Numerical operations

### Frontend
- **React 18**: UI library
- **Vite**: Build tool and dev server
- **TypeScript**: Type-safe JavaScript
- **TailwindCSS**: Utility-first CSS framework
- **React Router**: Client-side routing
- **Axios**: HTTP client

### Infrastructure
- **PostgreSQL 15+**: Primary database
- **OpenSearch** (optional): Search engine
- **Docker**: Containerization
- **Docker Compose**: Local orchestration
- **Kubernetes**: Production deployment
- **Prometheus**: Metrics collection
- **Grafana**: Metrics visualization

### Testing
- **pytest**: Python testing framework
- **Playwright**: E2E browser testing
- **Vitest**: Frontend unit testing

### Code Quality
- **ruff**: Fast Python linter
- **black**: Python code formatter
- **isort**: Import sorting
- **mypy**: Static type checking
- **ESLint**: JavaScript/TypeScript linting
- **Prettier**: Frontend code formatting
- **pre-commit**: Git hooks for quality checks

## Design Decisions

### Why FastAPI?

**Pros**:
- Native async/await support for high concurrency
- Automatic OpenAPI documentation
- Built-in data validation with Pydantic
- High performance (on par with Node.js)
- Type hints enable better IDE support

**Cons**:
- Smaller ecosystem than Flask/Django
- Async patterns require understanding

### Why PostgreSQL as a Queue?

**Pros**:
- No additional service to manage (simpler ops)
- ACID transactions ensure reliability
- `FOR UPDATE SKIP LOCKED` enables lock-free concurrency
- Query jobs and queue with same tool
- Backup/restore includes queue state

**Cons**:
- Not designed for high-throughput queues
- Polling overhead (mitigated with reasonable intervals)

**Alternative Considered**: RabbitMQ, Redis, Celery
- Would add operational complexity
- Overkill for moderate job volumes
- Our workload: long-running tasks, not high throughput

### Why Whisper Chunking?

**Problem**: Large Whisper models (large-v3) consume significant VRAM. Long videos (1+ hours) can exceed VRAM limits.

**Solution**: Split audio into chunks (default 15 minutes), transcribe independently, merge with time offsets.

**Trade-offs**:
- Pro: Predictable memory usage, parallel processing potential
- Con: Potential discontinuity at chunk boundaries (mitigated by context overlap in future)

### Why Optional OpenSearch?

**Decision**: Make OpenSearch optional, default to PostgreSQL FTS

**Rationale**:
- PostgreSQL FTS sufficient for basic use cases
- OpenSearch adds operational overhead (JVM, memory, management)
- Users can opt-in for advanced features (highlighting, synonyms, ranking)

**When to use OpenSearch**:
- Large corpus (100K+ documents)
- Advanced search features needed
- Performance requirements exceed PostgreSQL FTS

### Why ROCm Primary, CUDA Secondary?

**Context**: Project initially developed on AMD hardware

**Implementation**:
- Dockerfile uses ROCm base image
- `GPU_DEVICE_PREFERENCE=hip,cuda` tries ROCm first
- Falls back gracefully to CUDA or CPU

**Future**: Maintain both GPU backends equally, select via build variant

### Why Session-Based Auth?

**Decision**: Server-side sessions over JWT

**Rationale**:
- Easier session revocation (logout, security incidents)
- Smaller cookies (just session ID, not full JWT payload)
- OAuth tokens stored server-side (more secure)

**Trade-off**: Requires database lookup per request (mitigated by connection pooling)

## Next Steps

- **Read Code Guidelines**: [code-guidelines.md](code-guidelines.md)
- **Learn Testing Practices**: [testing.md](testing.md)
- **Understand Release Process**: [release-process.md](release-process.md)
- **Explore Codebase**: Start with `app/main.py` and `worker/loop.py`

## Questions?

If you have questions about the architecture:
- Open an issue with the `question` label
- Check existing issues and discussions
- Review inline code comments for implementation details
