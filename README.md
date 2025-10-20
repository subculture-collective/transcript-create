<img src="public/icon.png" alt="Logo" width="64" height="64" align="right" />

# Transcript Create

[![Backend CI](https://github.com/subculture-collective/transcript-create/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/subculture-collective/transcript-create/actions/workflows/backend-ci.yml)
[![Frontend CI](https://github.com/subculture-collective/transcript-create/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/subculture-collective/transcript-create/actions/workflows/frontend-ci.yml)

Create searchable, exportable transcripts from YouTube videos or channels. The stack includes a FastAPI backend, PostgreSQL queue/store, a GPU-accelerated Whisper worker (ROCm or CUDA), optional pyannote diarization, and a Vite React frontend with search, deep links, and export tools.

## Highlights

- Ingest a single video or entire channel with yt-dlp
- Transcribe with Whisper large-v3 (GPU preferred) and optional speaker diarization
- Long-audio chunking with automatic time-offset merging
- YouTube auto-captions ingestion to compare vs native transcripts
- Full-text search across native or YouTube captions (Postgres FTS or OpenSearch)
- Exports: SRT, VTT, JSON (native and YouTube), plus pretty PDF with headers/footers
- OAuth login (Google, Twitch), favorites, admin analytics
- Monetization-ready: free vs pro plans, daily limits, Stripe checkout/portal/webhook
- Horizontal-safe worker queue using Postgres SKIP LOCKED

## Architecture (at a glance)

- API (FastAPI): modular routers for auth, billing, jobs, videos, favorites, events, admin, search, exports
- Database (PostgreSQL): `jobs`, `videos`, `transcripts`, `segments`, plus YouTube captions tables
- Worker: selects one pending video with `FOR UPDATE SKIP LOCKED`, runs the pipeline, updates status
- Optional: OpenSearch for richer search and highlighting
- Frontend (Vite + React + Tailwind): search/group-by-video, timestamp deep links, export menu, pricing/upgrade flow

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

- API available at http://localhost:8000
- Postgres exposed on host port 5434 (inside network: db:5432)
- If your host ROCm version ≠ 6.0, use a different build arg, e.g.:

```bash
docker compose build --build-arg ROCM_WHEEL_INDEX=https://download.pytorch.org/whl/rocm6.1
docker compose up -d
```

3. Start the frontend (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

4. Ingest a video

```bash
curl -s -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=VIDEOID","kind":"single"}'
```

Check status and fetch transcript when complete (see API section below).

## Repository layout

- Backend: `app/` (routers in `app/routes/`, settings in `app/settings.py`)
- Worker: `worker/` (pipeline + whisper runner + diarization)
- Frontend: `frontend/` (Vite + React + Tailwind)
- SQL schema: `sql/schema.sql` (auto-applied on first compose up)
- Data storage: `data/VIDEO_UUID/` mounted as `/data` in containers
- OpenSearch analysis: `config/opensearch/analysis/`

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

- Postgres FTS: `SEARCH_BACKEND=postgres` (GIN indices and triggers included in `sql/schema.sql`)
- OpenSearch: `SEARCH_BACKEND=opensearch` (indices with synonyms/n-grams set up by the indexer script)

Indexer examples:

```bash
python scripts/backfill_fts.py --batch 500 --until-empty
python scripts/opensearch_indexer.py --recreate --batch 5000 --bulk-docs 1000 --refresh-off
```

## Exports

- Native: `/videos/{id}/transcript.(json|srt|vtt|pdf)`
- YouTube captions: `/videos/{id}/youtube-transcript.(json|srt|vtt)`

PDF export uses ReportLab with a serif font (set via `PDF_FONT_PATH`) and includes headers/footers/metadata. Export requests are logged for analytics. Free plans may be gated by daily limits; HTML requests to gated endpoints redirect to an upgrade route.

## Authentication and plans

- OAuth providers: Google and Twitch
- Session cookie with server-side lookup; `/auth/me` returns plan/quota
- Admins (by email) can view analytics and set user plans
- Free vs Pro: configurable daily limits for search and exports

Frontend includes a pricing/upgrade flow and an interstitial upgrade page that returns users to their original destination after upgrading.

## Billing (Stripe)

Endpoints

- `POST /billing/checkout-session` → returns a Checkout URL
- `GET  /billing/portal` → returns a Customer Portal URL
- `POST /stripe/webhook` → subscription lifecycle (set plan to Pro on active/trialing; revert to Free on cancellation)

Environment

- `STRIPE_API_KEY` = `sk_...`
- `STRIPE_PRICE_PRO_MONTHLY` / `STRIPE_PRICE_PRO_YEARLY` = `price_...`
- `STRIPE_WEBHOOK_SECRET` = `whsec_...`
- `STRIPE_SUCCESS_URL` / `STRIPE_CANCEL_URL` use `{origin}` which resolves to `FRONTEND_ORIGIN`

Tip: For local testing, use Stripe CLI to forward events to `http://localhost:8000/stripe/webhook` and create a Checkout session from the Pricing page or via the API.

## API reference (selected)

Jobs

- `POST /jobs` → `{ url: string, kind: "single"|"channel" }` → enqueues
- `GET /jobs/{id}` → status

Videos

- `GET /videos/{id}` → details
- `GET /videos/{id}/transcript` → merged segments (JSON)
- `GET /videos/{id}/transcript.(srt|vtt|pdf)`
- `GET /videos/{id}/youtube-transcript.(json|srt|vtt)`

Search

- `GET /search?q=...&source=native|youtube` → grouped hits with timestamps and highlights

Admin

- `POST /admin/users/{user_id}/plan` body `{ "plan": "free"|"pro" }`
- `GET /admin/events` / `/admin/events.csv` / `/admin/events/summary`

Billing

- `POST /billing/checkout-session` (body can include `period: "monthly"|"yearly"`)
- `GET /billing/portal`

Auth

- `GET /auth/me`, `GET /auth/login/google`, `GET /auth/login/twitch`, callbacks, `POST /auth/logout`

All endpoints return structured JSON or a redirect/byte stream where applicable. See `app/routes/` for full definitions.

## Environment configuration

The backend reads `.env` via `pydantic-settings` in `app/settings.py`. Highlights:

- Core: `DATABASE_URL`, `SESSION_SECRET`, `FRONTEND_ORIGIN`, `ADMIN_EMAILS`
- Whisper/GPU: `WHISPER_BACKEND`, `WHISPER_MODEL`, `FORCE_GPU`, `GPU_DEVICE_PREFERENCE` (e.g., `hip,cuda`), `GPU_COMPUTE_TYPES`, `GPU_MODEL_FALLBACKS`
- Chunking/cleanup: `CHUNK_SECONDS`, `CLEANUP_*`, `RESCUE_STUCK_AFTER_SECONDS`
- Diarization: `HF_TOKEN` (optional)
- Search: `SEARCH_BACKEND`, `OPENSEARCH_*`
- Quotas/plans: `FREE_DAILY_SEARCH_LIMIT`, `FREE_DAILY_EXPORT_LIMIT`, `PRO_PLAN_NAME`
- PDF: `PDF_FONT_PATH`
- Stripe: as listed in the Billing section above

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

- Compose passes `/dev/kfd` and `/dev/dri` and adds the `video` group for ROCm
- Set `GPU_DEVICE_PREFERENCE=hip,cuda` to try ROCm first, then CUDA, or vice versa
- To force GPU and fail fast when not available: `FORCE_GPU=true`
- If VRAM is tight, reduce `WHISPER_MODEL` or set `GPU_MODEL_FALLBACKS`

## OpenSearch (optional)

- Compose includes OpenSearch and Dashboards on ports 9200/5601 with security disabled for local dev
- Configure `SEARCH_BACKEND=opensearch` and run `scripts/opensearch_indexer.py` to create/populate indices
- Synonyms live in `config/opensearch/analysis/synonyms.txt`

## Troubleshooting

- Worker fails to start on GPU: verify ROCm drivers; try a different `ROCM_WHEEL_INDEX` build arg; set `FORCE_GPU=false` to allow CPU fallback when using `faster-whisper`
- 402 responses on export/search: expected for Free plan beyond quotas; upgrade or adjust limits in `.env`
- Webhook not firing: ensure `STRIPE_WEBHOOK_SECRET` matches and that Stripe CLI or a public URL forwards to `/stripe/webhook`
- CORS: set `FRONTEND_ORIGIN` to your web app origin
- Schema: Compose auto-applies `sql/schema.sql`; to re-apply manually: `psql $DATABASE_URL -f sql/schema.sql`

## Contributing

- Code structure: see `app/routes/*`, `worker/*`, and `frontend/src/*`
- Style: prefer SQLAlchemy Core and parameterized SQL; keep worker idempotent and stateful via DB
- Small PRs welcome; please include minimal repro steps and note any env additions

### Development Setup

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

## Security

This project follows security best practices:
- All dependencies are pinned with specific versions
- Automated vulnerability scanning via GitHub Actions
- Pre-commit hooks prevent accidental secret commits
- Secrets managed via environment variables only

See [SECURITY.md](SECURITY.md) for:
- Reporting security vulnerabilities
- Secrets management guidelines
- Production security checklist
- Dependency update procedures

## License

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

For information about third-party dependencies and their licenses, see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## GitHub project automation

- Auto-triage: New issues are automatically labeled `status: triage` and added to Project 7 via `.github/workflows/auto-triage.yml`.
- Milestone backfill: Run manually from the Actions tab using "Backfill milestones on issues". Start with dry_run=true to preview; set to false to apply.
- Project saved views: To create helpful saved views (Priority and Milestone) for Project 7, run:
  - Make executable: `chmod +x scripts/setup_project_views.sh`
  - Run with defaults: `OWNER=onnwee PROJECT_NUMBER=7 ./scripts/setup_project_views.sh`
