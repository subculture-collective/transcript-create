# Systems Hardening 15 Findings Implementation Plan

> **For agentic workers:** This plan is the durable record requested before
> implementation. Execute in stages, not as one broad sweep. Each task should be
> small enough to review independently. Prefer adding or updating tests before
> behavior changes, and run the verification commands listed per task.

**Goal:** Address the 15 systems-report recommendations while preserving current
HasanAra behavior for existing archive/search/transcript users.

**Approved scope at creation:** Plan only. No implementation was performed when
this file was created.

**Recommended implementation strategy:** Stage 1 launch hardening first, then
correctness/contract stability, then scale/readiness, then docs cleanup.

**Tech stack:** Python, FastAPI, SQLAlchemy Core, PostgreSQL/Alembic, Redis,
OpenSearch, Prometheus/Grafana, Docker Compose, Kubernetes manifests, React,
TypeScript, Vite, ky.

---

## Stage 1: Launch Hardening

### Task 1: Lock Down Production Compose Exposure

**Finding:** Production compose inherits local-development host port exposure for
internal services.

**Files likely touched:**
- `docker-compose.prod.yml`
- `docker-compose.yml`
- `docker-compose.hasanara.yml`
- `docs/deployment/docker-compose.md` or `README.md`

**Plan:**
- [x] Decide whether production should be a standalone compose file or a strict
  override that removes inherited ports.
- [x] Ensure only the intended public entrypoints are exposed in production,
  normally Caddy `80/443` and possibly no direct API host port.
- [x] Keep Postgres, Redis, OpenSearch, Dashboards, Prometheus, and Grafana on
  private compose networks by default.
- [x] Replace Grafana `admin/admin` default with required env/secret input.
- [x] Document local-vs-production port behavior clearly.

**Verification:**
- `docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml config`
- Confirm rendered prod config does not publish DB/Redis/OpenSearch/Dashboards/
  Prometheus/Grafana unintentionally.

---

### Task 2: Require Auth And Quotas For `POST /jobs`

**Finding:** Public job creation can trigger expensive YouTube/GPU/disk work.

**Files likely touched:**
- `app/routes/jobs.py`
- `app/security.py`
- `app/common/session.py`
- `app/schemas.py`
- `sql/schema.sql` / Alembic migration if quota persistence is needed
- `tests/test_routes_jobs.py`
- `tests/test_openapi.py`
- `docs/api-reference.md`

**Plan:**
- [ ] Require an authenticated user or valid API key for `POST /jobs`.
- [ ] Keep `GET /jobs/{job_id}` public only if job IDs remain unguessable and no
  sensitive data is exposed; otherwise scope it to the job owner/admin.
- [ ] Add job ownership metadata or column if needed for quota enforcement.
- [ ] Add per-user daily or rolling-window job limits.
- [ ] Add channel job caps: max videos, staged batch limits, and duplicate
  suppression by canonical YouTube ID.
- [ ] Return structured `401`, `403`, and `429` errors with clear messages.

**Verification:**
- `python3 -m pytest tests/test_routes_jobs.py tests/test_openapi.py -q`
- Add/verify tests for anonymous rejection, authenticated creation, API-key
  creation, quota exceeded, and channel cap behavior.

---

### Task 3: Add Fail-Closed Production Config Validation

**Finding:** Unsafe defaults such as `SESSION_SECRET="change-me"` can survive
into production.

**Files likely touched:**
- `app/settings.py`
- `app/main.py`
- `worker/loop.py`
- `tests/test_settings.py` or new config tests
- `.env.example`

**Plan:**
- [x] Add a central validation function, e.g. `validate_production_settings()`.
- [x] Fail startup in `ENVIRONMENT=production` when critical defaults are unsafe:
  `SESSION_SECRET`, DB password fallback, OAuth secrets if auth is enabled,
  permissive CORS, default Grafana/OpenSearch production settings, missing
  `FRONTEND_ORIGIN`, and weak backup/secret configuration where applicable.
- [x] Call validation from both API and worker startup paths.
- [x] Keep development behavior permissive.
- [x] Document every required production env var.

**Verification:**
- `python3 -m pytest tests/test_settings.py tests/test_routes_health.py -q`
- Manual smoke: import settings with `ENVIRONMENT=production` and unsafe values;
  assert startup fails with actionable error.

---

### Task 4: Implement Missing `GET /admin/users`

**Finding:** Frontend and docs expect `/admin/users`, but backend only supports
plan updates.

**Files likely touched:**
- `app/routes/admin.py`
- `app/schemas.py`
- `tests/integration/test_auth_flow.py`
- `frontend/src/routes/admin/AdminUsers.tsx` if response shape changes

**Plan:**
- [x] Add admin-only `GET /admin/users` with `q`, `limit`, and `offset`.
- [x] Return `{items, page_info}` or preserve current frontend expectation
  `{items}` and document it.
- [x] Include safe fields only: `id`, `email`, `name`, `avatar_url`, `plan`,
  `role`, `created_at`, `updated_at`.
- [x] Standardize admin authorization on `require_role(ROLE_ADMIN)` for the new route.

**Verification:**
- `python3 -m pytest tests/integration/test_auth_flow.py tests/test_routes_auth.py -q`
- Add route tests for unauthenticated, non-admin, admin, search, and pagination.

---

### Task 5: Fix Frontend Cookie Credentials And API Base Hardcoding

**Finding:** Cookie auth may fail in split-origin deployments, and some frontend
paths hardcode `/api`.

**Files likely touched:**
- `frontend/src/services/api.ts`
- `frontend/src/services/auth.tsx`
- `frontend/src/components/ExportMenu.tsx`
- `frontend/src/services/analytics.ts`
- `frontend/src/routes/admin/AdminEvents.tsx`
- `clients/javascript/src/client.ts`
- `frontend/vite.config.ts`

**Plan:**
- [x] Set ky credentials deliberately, likely `credentials: 'include'`.
- [x] Export a helper to build API URLs from `VITE_API_BASE` for redirects,
  downloads, beacons, and CSV links.
- [x] Replace hardcoded `/api/...` usages in frontend code.
- [x] Ensure same-origin proxy dev still works.
- [ ] Update JS SDK default base URL if appropriate, or document explicit base
  requirement.

**Verification:**
- `cd frontend && npm run build`
- `cd frontend && npm run lint`
- Add/verify tests for URL construction when `VITE_API_BASE` is default and when
  it is an absolute URL.

---

## Stage 2: Correctness And Contract Stability

### Task 6: Add Worker Cache Invalidation Or Versioned Cache Keys

**Finding:** Cached video/transcript/search/archive data can remain stale after
worker writes.

**Files likely touched:**
- `app/cache.py`
- `app/crud.py`
- `worker/native_pipeline.py`
- `worker/caption_ingest.py`
- `worker/pipeline.py`
- `app/routes/videos.py`
- cache-related tests

**Plan:**
- [ ] Inventory all cached functions and key formats.
- [ ] Add explicit invalidation helpers for `video:{id}`, transcript segments,
  YouTube transcript data, search results, archive summary/intelligence, and
  transcript blocks.
- [ ] Call invalidation after native transcript writes, YouTube caption writes,
  metadata updates, and archive label/period mutations.
- [ ] Consider versioned cache keys based on `videos.updated_at` and formatter
  version for transcript endpoints.

**Verification:**
- `python3 -m pytest tests/test_routes_videos.py tests/test_cache.py -q`
- Add a regression test that cached transcript data changes after reprocessing.

---

### Task 7: Generate Frontend Types From OpenAPI

**Finding:** Frontend API types are hand-maintained and drifting from backend
responses.

**Files likely touched:**
- `frontend/package.json`
- `frontend/src/types/api.ts`
- new generated types path, e.g. `frontend/src/types/generated/api.ts`
- `scripts/` helper for OpenAPI export/type generation
- CI workflows

**Plan:**
- [ ] Choose a generator, e.g. `openapi-typescript`, and add a deterministic
  script.
- [ ] Generate types from `/openapi.json` or from FastAPI app import in CI.
- [ ] Migrate frontend wrappers to generated response/request types where
  practical.
- [ ] Keep hand-written view-model types only where they intentionally differ.
- [ ] Add CI check that generated types are up to date.

**Verification:**
- `python3 -m pytest tests/test_openapi.py -q`
- `cd frontend && npm run build`
- `cd frontend && npm run typecheck` if a typecheck script is added.

---

### Task 8: Normalize Metrics Endpoint Labels

**Finding:** Prometheus labels use raw request paths, creating high-cardinality
series for UUID endpoints.

**Files likely touched:**
- `app/main.py`
- `app/metrics.py`
- `tests/test_metrics.py`
- Grafana/Prometheus dashboards if they depend on raw paths

**Plan:**
- [ ] Replace raw `request.url.path` labels with route templates when available.
- [ ] Fallback-normalize UUIDs, numeric IDs, and known path patterns.
- [ ] Keep method/status labels.
- [ ] Update tests and dashboards to use normalized endpoint labels.

**Verification:**
- `python3 -m pytest tests/test_metrics.py tests/test_middleware.py -q`
- Confirm `/videos/<uuid>` records as `/videos/{video_id}` or equivalent.

---

### Task 9: Validate Events And Add Retention Plan

**Finding:** `/events` and `/events/batch` accept arbitrary unauthenticated
payloads with no size/type limits.

**Files likely touched:**
- `app/routes/events.py`
- `app/schemas.py`
- `app/settings.py`
- Alembic migration only if retention/rollups require schema changes
- admin analytics tests

**Plan:**
- [ ] Add Pydantic request models for event type, payload, and batch.
- [ ] Restrict event type length and allowed characters.
- [ ] Limit payload byte size and batch size.
- [ ] Keep unauthenticated tracking only if product needs it; otherwise require
  auth for sensitive/admin events.
- [ ] Add retention setting and cleanup script/job for old raw events.
- [ ] Preserve admin analytics by either retaining enough raw history or adding
  aggregate tables before deletion.

**Verification:**
- `python3 -m pytest tests/test_routes_events.py tests/test_routes_admin.py -q`
- Add tests for too-large payloads, too-large batches, invalid event types, and
  valid anonymous/authenticated events.

---

### Task 10: Align OpenSearch Index Mapping With Queries

**Finding:** App queries OpenSearch fields that may not be indexed by the
indexer mapping.

**Files likely touched:**
- `scripts/opensearch_indexer.py`
- `app/search/orchestrator.py`
- `config/opensearch/analysis/*`
- `tests/test_search_orchestrator.py`
- OpenSearch integration tests if available

**Plan:**
- [ ] Define a single expected index document shape for native and YouTube
  segments.
- [ ] Include fields used by app queries: `video_id`, `start_ms`, `end_ms`,
  `text`, `uploaded_at`, `duration_seconds`, `channel_name`, `language`,
  `category`, `has_speaker_labels`, and source metadata.
- [ ] Update indexer mapping and bulk indexing SQL.
- [ ] Add compatibility behavior for missing fields or old indexes.
- [ ] Decide whether OpenSearch errors should fail search or fall back to
  Postgres for production resilience.

**Verification:**
- `python3 -m pytest tests/test_search_orchestrator.py tests/test_search_repository.py -q`
- Run indexer in a disposable OpenSearch environment and query filtered search.

---

## Stage 3: Scale And Readiness

### Task 11: Add Cursor Pagination For Videos And Search

**Finding:** Offset pagination will degrade for deep result sets.

**Files likely touched:**
- `app/schemas.py`
- `app/routes/videos.py`
- `app/routes/search.py`
- `app/crud.py`
- `app/search/segment_repository.py`
- `frontend/src/services/api.ts`
- frontend list/search pages

**Plan:**
- [ ] Keep `limit`/`offset` compatibility initially.
- [ ] Add cursor params and cursor fields to `PageInfo`.
- [ ] Use stable sort keys: uploaded/date/id for videos, rank/start/id for
  search.
- [ ] Add cursor encoding/decoding helpers.
- [ ] Migrate frontend list/search pagination to cursors once backend support is
  stable.

**Verification:**
- `python3 -m pytest tests/test_routes_videos.py tests/test_routes_search.py -q`
- Add tests for first page, next page, previous/invalid cursor behavior, and
  stable ordering under duplicate timestamps.

---

### Task 12: Add Transcript Window/Range APIs

**Finding:** Full transcript responses load all segments and blocks
synchronously.

**Files likely touched:**
- `app/routes/videos.py`
- `app/transcripts/service.py`
- `app/transcripts/blocks.py`
- `app/transcripts/merged.py`
- `app/crud.py`
- `frontend/src/routes/VideoPage.tsx`

**Plan:**
- [ ] Add optional `start_ms`, `end_ms`, `segment_offset`, or `block_cursor`
  params to transcript endpoints, or create a dedicated range endpoint.
- [ ] Preserve current full transcript behavior for compatibility.
- [ ] Ensure merged/best source behavior works inside a time window.
- [ ] Return window metadata so frontend can request nearby segments.
- [ ] Update cache keys to include window and source/mode.

**Verification:**
- `python3 -m pytest tests/test_routes_videos.py tests/test_routes_exports.py -q`
- Add tests for native, YouTube, merged, and best windowed transcript output.

---

### Task 13: Replace In-Memory Rate Limiting With Redis-Backed Limits

**Finding:** Current app rate limiter is per-process memory and IP-only.

**Files likely touched:**
- `app/middleware.py`
- `app/settings.py`
- `app/cache.py` or new `app/rate_limit.py`
- `tests/test_middleware.py`
- Compose/env docs

**Plan:**
- [ ] Add Redis-backed sliding-window or token-bucket limiter.
- [ ] Keep in-memory fallback for local development when Redis is disabled.
- [ ] Define separate limits for global requests, auth endpoints, job creation,
  search, events, and exports.
- [ ] Respect trusted proxy headers only when configured.
- [ ] Emit consistent `429` responses and `Retry-After` headers.

**Verification:**
- `python3 -m pytest tests/test_middleware.py tests/test_routes_jobs.py tests/test_routes_events.py -q`
- Add tests for shared limits across middleware instances if Redis fake/mocking is
  available.

---

### Task 14: Add Query Timeouts And Monitoring Coverage

**Finding:** Search/database queries need guardrails and dashboards before archive
growth.

**Files likely touched:**
- `app/search/orchestrator.py`
- `app/search/segment_repository.py`
- `app/crud.py`
- `app/db.py`
- `app/metrics.py`
- `config/prometheus/alerts.yml`
- `config/grafana/dashboards/*.json`

**Plan:**
- [ ] Add configurable DB statement timeout for expensive search/export queries.
- [ ] Ensure OpenSearch timeout is configurable instead of hardcoded.
- [ ] Add metrics for search duration, backend used, timeout count, and fallback
  count.
- [ ] Add alerts for high timeout/error rate.
- [ ] Update dashboards to show search latency and backend health.

**Verification:**
- `python3 -m pytest tests/test_routes_search.py tests/test_metrics.py -q`
- Run `scripts/validate_monitoring.py` if available and applicable.

---

## Stage 4: Documentation Cleanup

### Task 15: Resolve Docs Drift

**Finding:** README/docs mention stale ports, schema bootstrapping, billing, and
some routes that differ from implementation.

**Files likely touched:**
- `README.md`
- `docs/api-reference.md`
- `docs/development/architecture.md`
- `docs/development/testing.md`
- `docs/deployment/docker-compose.md`
- `docs/ADVANCED_FEATURES.md`
- `docs/MONITORING.md`
- `docs/SECURITY.md`

**Plan:**
- [ ] Update documented compose ports to match actual defaults.
- [ ] Clarify Alembic is the migration path and `schema.sql` is not auto-applied
  by compose.
- [ ] Remove or mark billing/Stripe claims as not currently wired if no billing
  route is present.
- [ ] Document `/admin/users` after backend implementation, or remove references
  if not implemented.
- [ ] Document auth requirement/quota behavior for `POST /jobs`.
- [ ] Document production hardening requirements and unsafe local defaults.
- [ ] Update frontend API base/cookie deployment guidance.

**Verification:**
- Review docs against `app/main.py` router registration, compose rendered config,
  and `frontend/src/services/api.ts`.
- Optional: run docs link/check tooling if configured.

---

## Cross-Cutting Acceptance Criteria

- [ ] Existing public archive browsing/search/transcript behavior remains
  backward compatible unless explicitly documented.
- [ ] Every behavior-changing backend task includes route or service tests.
- [ ] Every frontend contract change builds with TypeScript.
- [ ] Production safety changes fail closed in production and remain ergonomic in
  development.
- [ ] Docs are updated after behavior changes, not before.
- [ ] OpenAPI schema remains valid and frontend types are aligned once type
  generation is introduced.

---

## Suggested Execution Batches

### Batch A: Minimal Launch Hardening

1. Task 1 — production compose exposure
2. Task 3 — production config validation
3. Task 4 — `GET /admin/users`
4. Task 5 — frontend API base/credentials

### Batch B: Abuse And Data Correctness

1. Task 2 — auth/quota for `POST /jobs`
2. Task 6 — cache invalidation/versioning
3. Task 8 — metrics normalization
4. Task 9 — event validation limits

### Batch C: Search/Scale Readiness

1. Task 10 — OpenSearch parity
2. Task 11 — cursor pagination
3. Task 12 — transcript windowing
4. Task 13 — Redis rate limiting
5. Task 14 — query timeouts/dashboards

### Batch D: Contract And Docs Finalization

1. Task 7 — OpenAPI-generated TypeScript types
2. Task 15 — docs drift cleanup

---

## Known Dependencies And Sequencing Notes

- Do Task 4 before finalizing docs that reference `/admin/users`.
- Do Task 2 before documenting public ingestion behavior.
- Do Task 6 before Task 12 if transcript windowing changes cache keys.
- Do Task 10 before making OpenSearch the preferred production search backend.
- Do Task 7 after major API response shapes stabilize.
- Do Task 15 last in each batch, or once implementation decisions are final.

---

## Initial Verification Matrix

Run the smallest relevant subset per task, then a broader suite at batch end.

```bash
python3 -m pytest tests/test_routes_jobs.py tests/test_routes_videos.py tests/test_routes_search.py -q
python3 -m pytest tests/test_middleware.py tests/test_metrics.py tests/test_openapi.py -q
python3 -m pytest tests/integration/test_auth_flow.py -q
cd frontend && npm run build
cd frontend && npm run lint
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```
