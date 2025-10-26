<img src="public/icon.png" alt="Logo" width="64" height="64" align="right" />

# Transcript Create

[![Backend CI](https://github.com/subculture-collective/transcript-create/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/subculture-collective/transcript-create/actions/workflows/backend-ci.yml)
[![Frontend CI](https://github.com/subculture-collective/transcript-create/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/subculture-collective/transcript-create/actions/workflows/frontend-ci.yml)
[![E2E Tests](https://github.com/subculture-collective/transcript-create/actions/workflows/e2e-tests.yml/badge.svg)](https://github.com/subculture-collective/transcript-create/actions/workflows/e2e-tests.yml)
[![Docker Build](https://github.com/subculture-collective/transcript-create/actions/workflows/docker-build.yml/badge.svg)](https://github.com/subculture-collective/transcript-create/actions/workflows/docker-build.yml)
[![Docker Image Version](https://ghcr-badge.egpl.dev/onnwee/transcript-create/latest_tag?trim=major&label=latest)](https://github.com/onnwee/transcript-create/pkgs/container/transcript-create)

Create searchable, exportable transcripts from YouTube videos or channels. The stack includes a FastAPI backend, PostgreSQL queue/store, a GPU-accelerated Whisper worker (ROCm or CUDA), optional pyannote diarization, and a Vite React frontend with search, deep links, and export tools.

## CI/CD Status

This project has comprehensive CI/CD automation:

-   **Backend CI**: Linting (ruff, black, isort), type checking (mypy), security scanning, tests with PostgreSQL, Docker build validation
-   **Frontend CI**: ESLint, Prettier formatting, TypeScript checking, Vite build with bundle size monitoring
-   **E2E Tests**: Playwright tests across Chromium, Firefox, WebKit, and mobile viewports (255 tests)
-   **Docker Build**: Automated builds on push to main and tags, published to GHCR with ROCm support
-   **Security**: Weekly dependency audits, secret scanning, vulnerability detection

All checks must pass before merging to `main`. Typical PR checks complete in < 3 minutes. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Highlights

-   Ingest a single video or entire channel with yt-dlp
-   Transcribe with Whisper large-v3 (GPU preferred) and optional speaker diarization
-   Long-audio chunking with automatic time-offset merging
-   YouTube auto-captions ingestion to compare vs native transcripts
-   Full-text search across native or YouTube captions (Postgres FTS or OpenSearch)
-   Exports: SRT, VTT, JSON (native and YouTube), plus pretty PDF with headers/footers
-   OAuth login (Google, Twitch), favorites, admin analytics
-   Monetization-ready: free vs pro plans, daily limits, Stripe checkout/portal/webhook
-   Horizontal-safe worker queue using Postgres SKIP LOCKED

## Architecture (at a glance)

-   API (FastAPI): modular routers for auth, billing, jobs, videos, favorites, events, admin, search, exports
-   Database (PostgreSQL): `jobs`, `videos`, `transcripts`, `segments`, plus YouTube captions tables
-   Worker: selects one pending video with `FOR UPDATE SKIP LOCKED`, runs the pipeline, updates status
-   Optional: OpenSearch for richer search and highlighting
-   Frontend (Vite + React + Tailwind): search/group-by-video, timestamp deep links, export menu, pricing/upgrade flow

Why this design: a DB-backed queue keeps infra light while enabling scale-out workers. Chunking manages memory/runtime; diarization runs post-process for coherent speakers across the whole audio.

## Quickstart

1. Copy env and fill basics

```bash
cp .env.example .env
# SECURITY: Generate a secure SESSION_SECRET
openssl rand -hex 32  # Copy this value to SESSION_SECRET in .env
# Required for local dev: DATABASE_URL (set automatically by docker-compose)
# Optional: FRONTEND_ORIGIN (defaults to http://localhost:5173), HF_TOKEN for diarization
# Billing/auth can be added later; see sections below
```

**Security Note**: See [SECURITY.md](SECURITY.md) for detailed security practices and secrets management.

2. Start services with Docker Compose (Postgres + API + Worker; OpenSearch optional)

```bash
docker compose build
docker compose up -d
```

-   API available at <http://localhost:8000>
-   Postgres exposed on host port 5434 (inside network: db:5432)
-   Prometheus metrics at <http://localhost:9090>
-   Grafana dashboards at <http://localhost:3000> (admin/admin)
-   If your host ROCm version ≠ 6.0, use a different build arg, e.g.:

```bash
docker compose build --build-arg ROCM_WHEEL_INDEX=https://download.pytorch.org/whl/rocm6.1
docker compose up -d
```

If ports are already in use on your machine, you can override the host ports without editing the compose file by setting environment variables:

-   `DB_HOST_PORT` (default 5434)
-   `API_HOST_PORT` (default 8000)
-   `OPENSEARCH_HOST_PORT` (default 9200)
-   `DASHBOARDS_HOST_PORT` (default 5601)
-   `PROMETHEUS_HOST_PORT` (default 9090)
-   `GRAFANA_HOST_PORT` (default 3000)

Example (run Grafana on 3300 instead of 3000):

```bash
GRAFANA_HOST_PORT=3300 docker compose up -d
```

3. Start the frontend (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

4. Ingest a video

```bash
curl -s -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=VIDEOID","kind":"single"}'
```

Check status and fetch transcript when complete (see API section below).

## Docker Images

Pre-built Docker images are automatically published to GitHub Container Registry (GHCR) on every release and push to main.

### Pulling Images

```bash
# Pull the latest stable image
docker pull ghcr.io/onnwee/transcript-create:latest

# Pull a specific version
docker pull ghcr.io/onnwee/transcript-create:1.0.0

# Pull a specific ROCm variant
docker pull ghcr.io/onnwee/transcript-create:rocm6.0
docker pull ghcr.io/onnwee/transcript-create:rocm6.1
```

### Available Tags

-   `latest` - Latest stable build from main branch (ROCm 6.0 by default)
-   `v1.2.3`, `1.2.3`, `1.2`, `1` - Semantic version tags from releases
-   `sha-abc123` - Specific commit builds
-   `rocm6.0`, `rocm6.1`, `rocm6.2` - ROCm version variants
-   `buildcache` - Build cache (internal use)

### Using Pre-built Images

Update your `docker-compose.yml` to use the pre-built image:

```yaml
services:
    api:
        image: ghcr.io/onnwee/transcript-create:latest
        # Remove the 'build' section
        env_file: .env
        # ... rest of configuration
```

### Image Details

-   **Base**: ROCm dev-ubuntu-22.04:6.0.2 (AMD GPU support)
-   **Size**: ~2.5-3GB (optimized with layer caching)
-   **Platforms**: linux/amd64
-   **Includes**: PyTorch ROCm, Whisper, ffmpeg, all dependencies

### Build Configuration

Images are built with:

-   Planned: Multi-stage optimization for smaller size
-   Layer caching for faster rebuilds (< 5 min with cache)
-   SBOM (Software Bill of Materials) for security
-   Provenance attestations for supply chain security
-   Configurable ROCm version via `ROCM_WHEEL_INDEX` build arg

## Repository layout

-   Backend: `app/` (routers in `app/routes/`, settings in `app/settings.py`)
-   Worker: `worker/` (pipeline + whisper runner + diarization)
-   Frontend: `frontend/` (Vite + React + Tailwind)
-   SQL schema: `sql/schema.sql` (auto-applied on first compose up)
-   Data storage: `data/VIDEO_UUID/` mounted as `/data` in containers
-   OpenSearch analysis: `config/opensearch/analysis/`

## Pipeline overview

1. Fetch metadata and download audio (yt-dlp)
2. Ensure 16 kHz mono WAV via ffmpeg
3. Chunk long audio (`CHUNK_SECONDS`, default 900s)
4. Transcribe each chunk (Whisper CT2 or PyTorch)
5. Optional diarization and alignment (pyannote) if `HF_TOKEN` is set
6. Persist one `transcripts` row and many `segments` rows; mark video `completed`

States progress from `downloading` → `transcoding` → `transcribing` → `completed` or `failed`. Worker requeues stalled videos based on `RESCUE_STUCK_AFTER_SECONDS`.

## Search backends

Single endpoint for both native or YouTube captions:

```
GET /search?q=hello&source=native|youtube
```

-   Postgres FTS: `SEARCH_BACKEND=postgres` (GIN indices and triggers included in `sql/schema.sql`)
-   OpenSearch: `SEARCH_BACKEND=opensearch` (indices with synonyms/n-grams set up by the indexer script)

Indexer examples:

```bash
python scripts/backfill_fts.py --batch 500 --until-empty
python scripts/opensearch_indexer.py --recreate --batch 5000 --bulk-docs 1000 --refresh-off
```

## Exports

-   Native: `/videos/{id}/transcript.(json|srt|vtt|pdf)`
-   YouTube captions: `/videos/{id}/youtube-transcript.(json|srt|vtt)`

PDF export uses ReportLab with a serif font (set via `PDF_FONT_PATH`) and includes headers/footers/metadata. Export requests are logged for analytics. Free plans may be gated by daily limits; HTML requests to gated endpoints redirect to an upgrade route.

## Authentication and plans

-   OAuth providers: Google and Twitch
-   Session cookie with server-side lookup; `/auth/me` returns plan/quota
-   Admins (by email) can view analytics and set user plans
-   Free vs Pro: configurable daily limits for search and exports

Frontend includes a pricing/upgrade flow and an interstitial upgrade page that returns users to their original destination after upgrading.

## Billing (Stripe)

Endpoints

-   `POST /billing/checkout-session` → returns a Checkout URL
-   `GET  /billing/portal` → returns a Customer Portal URL
-   `POST /stripe/webhook` → subscription lifecycle (set plan to Pro on active/trialing; revert to Free on cancellation)

Environment

-   `STRIPE_API_KEY` = `sk_...`
-   `STRIPE_PRICE_PRO_MONTHLY` / `STRIPE_PRICE_PRO_YEARLY` = `price_...`
-   `STRIPE_WEBHOOK_SECRET` = `whsec_...`
-   `STRIPE_SUCCESS_URL` / `STRIPE_CANCEL_URL` use `{origin}` which resolves to `FRONTEND_ORIGIN`

Tip: For local testing, use Stripe CLI to forward events to `http://localhost:8000/stripe/webhook` and create a Checkout session from the Pricing page or via the API.

## API reference (selected)

Jobs

-   `POST /jobs` → `{ url: string, kind: "single"|"channel" }` → enqueues
-   `GET /jobs/{id}` → status

Videos

-   `GET /videos/{id}` → details
-   `GET /videos/{id}/transcript` → merged segments (JSON)
-   `GET /videos/{id}/transcript.(srt|vtt|pdf)`
-   `GET /videos/{id}/youtube-transcript.(json|srt|vtt)`

Search

-   `GET /search?q=...&source=native|youtube` → grouped hits with timestamps and highlights

Admin

-   `POST /admin/users/{user_id}/plan` body `{ "plan": "free"|"pro" }`
-   `GET /admin/events` / `/admin/events.csv` / `/admin/events/summary`

Billing

-   `POST /billing/checkout-session` (body can include `period: "monthly"|"yearly"`)
-   `GET /billing/portal`

Auth

-   `GET /auth/me`, `GET /auth/login/google`, `GET /auth/login/twitch`, callbacks, `POST /auth/logout`

Health

-   `GET /health` → basic health check for load balancers
-   `GET /live` → Kubernetes liveness probe
-   `GET /ready` → Kubernetes readiness probe (checks critical dependencies)
-   `GET /health/detailed` → comprehensive component status (database, OpenSearch, storage, worker)

See [docs/health-checks.md](docs/health-checks.md) for detailed health check documentation.

All endpoints return structured JSON or a redirect/byte stream where applicable. See `app/routes/` for full definitions.

## Environment configuration

The backend reads `.env` via `pydantic-settings` in `app/settings.py`. Highlights:

-   Core: `DATABASE_URL`, `SESSION_SECRET`, `FRONTEND_ORIGIN`, `ADMIN_EMAILS`
-   Whisper/GPU: `WHISPER_BACKEND`, `WHISPER_MODEL`, `FORCE_GPU`, `GPU_DEVICE_PREFERENCE` (e.g., `hip,cuda`), `GPU_COMPUTE_TYPES`, `GPU_MODEL_FALLBACKS`
-   Chunking/cleanup: `CHUNK_SECONDS`, `CLEANUP_*`, `RESCUE_STUCK_AFTER_SECONDS`
-   Diarization: `HF_TOKEN` (optional)
-   Search: `SEARCH_BACKEND`, `OPENSEARCH_*`
-   Quotas/plans: `FREE_DAILY_SEARCH_LIMIT`, `FREE_DAILY_EXPORT_LIMIT`, `PRO_PLAN_NAME`
-   PDF: `PDF_FONT_PATH`
-   Stripe: as listed in the Billing section above

Frontend env: `frontend/.env` supports `VITE_API_BASE` to point the web app at a non-default API origin.

Consult `.env.example` for a complete list and defaults. Compose sets `DATABASE_URL` to the internal `db` service automatically.

## Running without Docker (dev)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Terminal 1 – API
uvicorn app.main:app --reload --port 8000

# Terminal 2 – Worker
python -m worker.loop

# Terminal 3 – Frontend
cd frontend && npm install && npm run dev
```

## GPU notes (ROCm/CUDA)

-   Compose passes `/dev/kfd` and `/dev/dri` and adds the `video` group for ROCm
-   Set `GPU_DEVICE_PREFERENCE=hip,cuda` to try ROCm first, then CUDA, or vice versa
-   To force GPU and fail fast when not available: `FORCE_GPU=true`
-   If VRAM is tight, reduce `WHISPER_MODEL` or set `GPU_MODEL_FALLBACKS`

## OpenSearch (optional)

-   Compose includes OpenSearch and Dashboards on ports 9200/5601 with security disabled for local dev
-   Configure `SEARCH_BACKEND=opensearch` and run `scripts/opensearch_indexer.py` to create/populate indices
-   Synonyms live in `config/opensearch/analysis/synonyms.txt`

## Monitoring (Prometheus & Grafana)

The application includes comprehensive monitoring with Prometheus metrics and Grafana dashboards.

**Quick Access:**

-   Grafana dashboards: <http://localhost:3000> (admin/admin)
-   Prometheus: <http://localhost:9090>
-   API metrics: <http://localhost:8000/metrics>
-   Worker metrics: <http://localhost:8001/metrics>

**Pre-configured Dashboards:**

1. **Overview**: Service health, request rates, job statistics, queue depth
2. **API Performance**: Request rates, latency percentiles, error rates, concurrent requests
3. **Transcription Pipeline**: Processing durations, queue status, model performance

**Key Metrics:**

-   HTTP request rates and latency
-   Job creation and completion rates
-   Video processing pipeline stages
-   Whisper model load and transcription times
-   Database query performance
-   GPU memory usage (when available)

For detailed documentation, see [docs/MONITORING.md](docs/MONITORING.md) including:

-   Adding custom metrics
-   Alert configuration
-   Troubleshooting
-   Performance tuning

## Troubleshooting

-   Worker fails to start on GPU: verify ROCm drivers; try a different `ROCM_WHEEL_INDEX` build arg; set `FORCE_GPU=false` to allow CPU fallback when using `faster-whisper`
-   402 responses on export/search: expected for Free plan beyond quotas; upgrade or adjust limits in `.env`
-   Webhook not firing: ensure `STRIPE_WEBHOOK_SECRET` matches and that Stripe CLI or a public URL forwards to `/stripe/webhook`
-   CORS: set `FRONTEND_ORIGIN` to your web app origin
-   Schema: Compose auto-applies `sql/schema.sql`; to re-apply manually: `psql $DATABASE_URL -f sql/schema.sql`

## Testing

### Unit Tests

**Backend (Python + pytest)**:

```bash
# Run all backend tests
pytest tests/

# Run specific test file
pytest tests/test_routes_auth.py

# Run with coverage
pytest --cov=app --cov=worker tests/
```

**Frontend (Vitest)**:

```bash
cd frontend

# Run all unit tests
npm test

# Run with UI
npm run test:ui

# Run with coverage
npm run test:coverage
```

### Integration Tests

```bash
# Start PostgreSQL service
docker compose up -d db

# Run integration tests
pytest tests/integration/ -v
```

### E2E Tests (Playwright)

Full end-to-end tests covering user workflows across browsers and mobile devices.

```bash
cd e2e

# Install dependencies (first time)
npm install
npx playwright install --with-deps

# Start services (in separate terminals)
cd .. && uvicorn app.main:app --reload --port 8000  # Backend
cd frontend && npm run dev                          # Frontend

# Seed test database
npm run seed-db

# Run E2E tests
npm test                    # All tests
npm run test:headed        # With visible browser
npm run test:ui            # Interactive UI mode
npm run test:critical      # Fast critical tests only
```

**Coverage**: 255 E2E tests across:

-   Authentication & sessions
-   Job creation & processing
-   Search with filters & deeplinks
-   Export features (SRT, VTT, PDF, JSON)
-   Billing & quotas
-   Error handling & 404 pages
-   Mobile responsiveness
-   Cross-browser (Chromium, Firefox, WebKit)

See [docs/E2E-TESTING.md](docs/E2E-TESTING.md) for comprehensive guide and [e2e/README.md](e2e/README.md) for detailed documentation.

## Contributing

We welcome contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for:

-   Development setup instructions
-   Code quality guidelines and linting
-   CI/CD pipeline documentation
-   Pull request process
-   Branch protection requirements

### Quick Start

```bash
# Install pre-commit hooks
./scripts/setup_precommit.sh

# Backend linting
ruff check app/ worker/ scripts/
black --check app/ worker/ scripts/
isort --check-only app/ worker/

# Frontend linting
cd frontend
npm run lint
npm run format:check
```

For detailed guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

### Development Setup (Legacy Section - see CONTRIBUTING.md for full details)

1. Install pre-commit hooks for security and code quality:

    ```bash
    # Quick setup (recommended)
    ./scripts/setup_precommit.sh

    # Or manual setup
    pip install pre-commit
    pre-commit install
    ```

    The pre-commit hooks automatically run:

    - **ruff**: Fast Python linter for code quality and style
    - **black**: Code formatter for consistent Python style
    - **isort**: Import sorting for organized imports
    - **gitleaks**: Secret detection to prevent credential leaks
    - Additional checks for trailing whitespace, YAML/JSON/TOML syntax, etc.

2. Manual linting and formatting:

    ```bash
    # Check all Python files
    ruff check app/ worker/ scripts/
    black --check app/ worker/ scripts/
    isort --check-only app/ worker/ scripts/

    # Auto-fix issues
    ruff check --fix app/ worker/ scripts/
    black app/ worker/ scripts/
    isort app/ worker/ scripts/

    # Type checking (optional)
    mypy app/ worker/
    ```

    All linting tools are configured in `pyproject.toml` with line-length=120 and consistent rules.

3. Before committing, ensure security checks pass:

    ```bash
    pre-commit run --all-files
    pip-audit -r requirements.txt
    ```

4. Follow security guidelines in [SECURITY.md](SECURITY.md)

## Testing

This project includes comprehensive test coverage:

### Unit Tests

```bash
# Run all unit tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov=worker --cov-report=html

# Run specific test file
pytest tests/test_routes_jobs.py -v
```

### Integration Tests

End-to-end integration tests validate complete workflows. See [tests/integration/README.md](tests/integration/README.md) for details.

```bash
# Run all integration tests
pytest tests/integration/ -v

# Run specific integration test suite
pytest tests/integration/test_job_flow.py -v

# Run with timeouts
pytest tests/integration/ --timeout=120 -v
```

Integration tests cover:

-   Job creation and processing workflows
-   Video transcription and export (SRT, PDF)
-   Search functionality (native and YouTube captions)
-   Worker processing and state transitions
-   Authentication and authorization flows
-   Billing and payment processing (mocked)
-   Database integrity and concurrency

### CI/CD Testing

All tests run automatically in CI on every pull request:

-   Unit tests with PostgreSQL
-   Integration tests (subset on PR, full suite nightly)
-   Security scans and linting

## Security

This project follows security best practices:

-   All dependencies are pinned with specific versions
-   Automated vulnerability scanning via GitHub Actions
-   Pre-commit hooks prevent accidental secret commits
-   Secrets managed via environment variables only

See [SECURITY.md](SECURITY.md) for:

-   Reporting security vulnerabilities
-   Secrets management guidelines
-   Production security checklist
-   Dependency update procedures

## License

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

For information about third-party dependencies and their licenses, see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## GitHub project automation

-   Auto-triage: New issues are automatically labeled `status: triage` and added to Project 7 via `.github/workflows/auto-triage.yml`.
-   Milestone backfill: Run manually from the Actions tab using "Backfill milestones on issues". Start with dry_run=true to preview; set to false to apply.
-   Project saved views: To create helpful saved views (Priority and Milestone) for Project 7, run:
    -   Make executable: `chmod +x scripts/setup_project_views.sh`
    -   Run with defaults: `OWNER=onnwee PROJECT_NUMBER=7 ./scripts/setup_project_views.sh`
