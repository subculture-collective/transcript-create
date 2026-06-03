# Architecture Deepening All Findings Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Recommended path:
> dispatch a fresh subagent per task, review each result with `review-quality`,
> then continue. For complex multi-agent splits, use
> `parallel-feature-development`, `team-composition-patterns`, and
> `team-communication-protocols`. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Implement all architecture review findings by turning shallow workflow/query/UI modules into deeper modules with smaller interfaces, better locality, and clearer test surfaces.

**Architecture:** Execute as ordered tracks. Start with vocabulary/docs, then worker caption/YouTube seams, then native video pipeline, then backend search/archive seams, then frontend product kernels. Keep compatibility wrappers during each track so the running HasanAra deployment can continue processing VODs.

**Tech Stack:** Python, FastAPI, SQLAlchemy Core, PostgreSQL/Alembic, yt-dlp, faster-whisper, React, TypeScript, Vite, Vitest, Docker Compose.

---

## Task 0: Create Domain And Decision Grounding

**Files:**
- Create: `CONTEXT.md`
- Create: `LANGUAGE.md`
- Create: `docs/adr/0001-staged-caption-first-ingestion.md`
- Modify: `docs/development/architecture.md`

- [ ] **Step 1: Create `CONTEXT.md`**

Define domain terms: `VOD`, `Video`, `Job`, `Channel Job`, `Staged Batch`, `YouTube Transcript`, `Native Transcript`, `Segment`, `Caption Ingest State`, `Archive Summary`, `Rolling Mode`.

- [ ] **Step 2: Create `LANGUAGE.md`**

Define architecture terms: **Module**, **Interface**, **Implementation**, **Depth**, **Seam**, **Adapter**, **Leverage**, **Locality**, **Deletion test**.

- [ ] **Step 3: Create ADR**

Create `docs/adr/0001-staged-caption-first-ingestion.md` documenting why HasanAra imports YouTube transcripts first, why Whisper can run in rolling mode, and why rate-limited caption work must not block native transcription forever.

- [ ] **Step 4: Update architecture docs**

Update `docs/development/architecture.md` to remove stale billing/pricing-as-live-product claims and link to `CONTEXT.md` and `docs/adr/`.

- [ ] **Step 5: Verify**

Run: `python3 -m compileall -q app worker alembic scripts`

Expected: pass.

---

## Task 1: Deepen Caption Ingestion

**Files:**
- Create: `worker/caption_ingest.py`
- Modify: `worker/loop.py`
- Modify: `worker/pipeline.py`
- Test: `tests/worker/test_caption_ingest.py`

**Problem:** `worker/loop.py`, `worker/pipeline.py`, and `worker/youtube_captions.py` share one concept: caption-first ingestion. The current **Interface** is implicit and shallow: callers must know staged batches, terminal states, cooldown, fallback behavior, and DB updates.

**Target Interface:**

```python
@dataclass(frozen=True)
class CaptionIngestionResult:
    attempted: int
    completed: int
    unavailable: int
    failed: int
    rate_limited: bool
    cooldown_seconds: int | None

def ingest_available_captions(db: Session, *, batch_id: str | None = None, limit: int = 1) -> CaptionIngestionResult:
    ...
```

- [ ] Write failing tests for `CaptionIngestionResult` and rate-limit behavior.
- [ ] Move caption selection SQL from `worker/loop.py` into `worker/caption_ingest.py`.
- [ ] Move `pipeline.capture_youtube_captions_for_unprocessed` behavior into the new Module.
- [ ] Keep `pipeline.capture_youtube_captions_for_unprocessed` as a compatibility wrapper.
- [ ] Make `worker/loop.py` call only `ingest_available_captions(...)` and react to `CaptionIngestionResult`.
- [ ] Verify with `python3 -m pytest tests/worker/test_caption_ingest.py tests/worker/test_loop_queue_sql.py -q` and `python3 -m py_compile worker/caption_ingest.py worker/loop.py worker/pipeline.py`.

---

## Task 2: Deepen The YouTube Adapter

**Files:**
- Create: `worker/youtube/service.py`
- Modify: `worker/youtube_captions.py`
- Modify: `worker/audio.py`
- Modify: `worker/youtube/yt_dlp_executor.py`
- Test: `tests/worker/test_youtube_service.py`

**Problem:** `worker/youtube_captions.py` mixes direct HTTP, yt-dlp subprocesses, PO tokens, cookies, EJS fallback, parsing, and metrics. The **Seam** exists only partially in `worker/youtube/yt_dlp_executor.py`.

**Target Interface:**

```python
@dataclass(frozen=True)
class YouTubeCaptionResult:
    track: YTCaptionTrack
    segments: list[YTSegment]
    source: Literal["direct", "yt-dlp"]

class YouTubeAdapter:
    def fetch_metadata(self, url: str) -> dict[str, Any]: ...
    def fetch_auto_captions(self, youtube_id: str) -> YouTubeCaptionResult | None: ...
    def download_audio(self, url: str, output_dir: Path) -> Path: ...
```

- [ ] Write tests for direct caption success, direct 429 + yt-dlp success, and direct 429 + yt-dlp 429.
- [ ] Move `_download_caption_with_ytdlp` into `worker/youtube/service.py`.
- [ ] Move yt-dlp metadata invocation from `worker/youtube_captions.py` into `YouTubeAdapter.fetch_metadata`.
- [ ] Keep old functions as compatibility wrappers.
- [ ] Ensure EJS fallback stays active via `--remote-components ejs:github`.
- [ ] Verify with `python3 -m pytest tests/worker/test_youtube_service.py tests/worker/test_youtube_captions.py tests/worker/test_yt_dlp_executor.py -q`.

---

## Task 3: Deepen Native Video Pipeline

**Files:**
- Create: `worker/pipeline_stages.py`
- Modify: `worker/pipeline.py`
- Modify: `worker/video_pipeline.py`
- Test: `tests/worker/test_pipeline_stages.py`
- Test: `tests/worker/test_video_pipeline_interface.py`

**Problem:** `worker/pipeline.py::process_video` is a 324-line shallow Module. Its **Interface** is “process a video,” but maintainers must understand download, transcode, chunk, Whisper, diarization, persistence, cleanup, and errors.

**Target Interface:**

```python
class PipelineStage(Protocol):
    name: str
    def run(self, ctx: VideoPipelineContext) -> VideoPipelineContext: ...

@dataclass
class VideoPipelineContext:
    db: Session
    video: VideoRecord
    work_dir: Path
    audio_path: Path | None = None
    transcript: TranscriptResult | None = None
```

- [ ] Add tests for each stage with fake adapters.
- [ ] Introduce `VideoPipelineContext`.
- [ ] Move download/transcode block from `process_video` into stage classes.
- [ ] Move Whisper block into `TranscribeStage`.
- [ ] Move persistence block into `PersistTranscriptStage`.
- [ ] Leave `process_video(video_id, db, ...)` as compatibility wrapper.
- [ ] Verify with `python3 -m pytest tests/worker/test_pipeline.py tests/worker/test_pipeline_stages.py tests/worker/test_video_pipeline_interface.py -q`.

---

## Task 4: Split Search SQL Out Of `app/crud.py`

**Files:**
- Modify: `app/search/repositories.py`
- Modify: `app/search/service.py`
- Modify: `app/crud.py`
- Test: `tests/test_search_repository.py`
- Test: `tests/test_search_service.py`

**Problem:** `app/search/` exists but is shallow. The actual advanced search **Implementation** still lives in `app/crud.py`: `search_youtube_segments_advanced` and `search_best_segments_advanced`.

**Target Interface:**

```python
class SearchRepository:
    def search_native(self, query: SearchQuery) -> list[SearchHit]: ...
    def search_youtube(self, query: SearchQuery) -> list[SearchHit]: ...
    def search_best(self, query: SearchQuery) -> list[SearchHit]: ...
```

- [ ] Add repository tests for native, YouTube, and best-source search.
- [ ] Move SQL query text from `crud.py` to `SearchRepository`.
- [ ] Update `PostgresSearchBackend` to use `SearchRepository`.
- [ ] Keep `crud.search_best_segments_advanced` as wrapper calling repository for compatibility.
- [ ] Remove wrapper after route tests pass, if no callers remain.
- [ ] Verify with `python3 -m pytest tests/test_search_repository.py tests/test_search_service.py tests/test_routes_search.py -q`.

---

## Task 5: Deepen Search Route Orchestration

**Files:**
- Create: `app/search/orchestrator.py`
- Modify: `app/routes/search.py`
- Modify: `app/search/types.py`
- Test: `tests/test_search_orchestrator.py`
- Test: `tests/test_routes_search.py`

**Problem:** `app/routes/search.py` is 1016 lines. The `search` function is 274 lines and mixes auth, analytics event writes, query normalization, backend selection, suggestions, search results, and error handling.

**Target Interface:**

```python
@dataclass(frozen=True)
class SearchRequestContext:
    user_id: str | None
    session_token: str | None
    is_admin: bool

class SearchOrchestrator:
    def search(self, db: Session, query: SearchQuery, context: SearchRequestContext) -> SearchResponse: ...
    def mention_map(self, db: Session, query: MentionMapQuery, context: SearchRequestContext) -> MentionMapResponse: ...
```

- [ ] Write tests for anonymous search, authenticated search event logging, and mention map.
- [ ] Move event tracking from route into `SearchOrchestrator`.
- [ ] Move suggestion update from route into `SearchOrchestrator`.
- [ ] Route becomes request parsing + response serialization only.
- [ ] Verify no quota logic remains.
- [ ] Verify with `python3 -m pytest tests/test_search_orchestrator.py tests/test_routes_search.py -q`.

---

## Task 6: Deepen Archive Summary

**Files:**
- Create: `app/archive/repository.py`
- Create: `app/archive/refresher.py`
- Modify: `scripts/refresh_archive_summary_stats.py`
- Modify: `app/crud.py`
- Modify: `app/routes/archive.py`
- Test: `tests/test_archive_summary_repository.py`
- Test: `tests/test_archive_routes.py`

**Problem:** The cached archive summary fix improved performance, but the logic still sits in `app/crud.py` and a standalone script. This is a shallow split: cache table, refresh script, summary route, and recent/popular queries are not one deep Module yet.

**Target Interface:**

```python
class ArchiveRepository:
    def get_summary(self, recent_limit: int, popular_limit: int) -> ArchiveSummary: ...
    def refresh_cached_stats(self) -> ArchiveSummaryStats: ...
```

- [ ] Add repository tests for cached stats present, cached stats missing, and recent VOD selection.
- [ ] Move `get_archive_summary` implementation into `app/archive/repository.py`.
- [ ] Move `scripts/refresh_archive_summary_stats.py` SQL into `app/archive/refresher.py`.
- [ ] Keep `crud.get_archive_summary` wrapper calling the archive Module.
- [ ] Update `app/routes/archive.py` to call archive Module directly.
- [ ] Verify with `python3 -m pytest tests/test_archive_summary_repository.py tests/test_archive_routes.py -q`.

---

## Task 7: Frontend Product Kernels

**Files:**
- Create: `frontend/src/features/videoTranscript/`
- Create: `frontend/src/features/searchArchive/`
- Modify: `frontend/src/routes/VideoPage.tsx`
- Modify: `frontend/src/routes/SearchPage.tsx`
- Test: `frontend/src/tests/videoTranscript.test.ts`
- Test: `frontend/src/tests/searchArchive.test.ts`

**Problem:** `VideoPage.tsx` and `SearchPage.tsx` mix routing, data fetch, URL state, view-model transforms, event handlers, saved moments, copy logic, and rendering. Their **Interface** is the page itself, so tests have to mount large UI trees.

- [ ] Write tests for transcript block selection, match navigation, and source label fallback.
- [ ] Move transcript block/match/quote formatting into `features/videoTranscript`.
- [ ] Write tests for search param normalization and filter URL building.
- [ ] Move search query/filter logic into `features/searchArchive`.
- [ ] Keep pages responsible only for rendering and calling hooks.
- [ ] Verify with `npm --prefix frontend test -- --run src/tests/videoTranscript.test.ts src/tests/searchArchive.test.ts src/tests/SearchPage.test.tsx` and `npm --prefix frontend run build`.

---

## Task 8: Remove Dead Billing/Pricing Remnants

**Files:**
- Delete: `app/routes/billing.py` if no longer routed
- Delete: `app/billing/policy.py` if no longer used
- Delete or rewrite: billing tests if obsolete
- Modify: `app/settings.py`
- Modify: `docs/development/architecture.md`
- Modify: `README.md`

**Problem:** Pricing was removed from the live app, but code remnants remain: `app/billing/policy.py`, limit settings, exception types, billing tests, and architecture docs. These are shallow leftovers future maintainers will misread as live behavior.

- [ ] Search for `billing`, `Stripe`, `FREE_DAILY`, `QuotaExceededError`, `can_export_format`.
- [ ] Delete truly unused billing Modules.
- [ ] Remove unused settings only if no tests or docs require them.
- [ ] Remove stale tests or rewrite them to assert unlimited access.
- [ ] Update docs to match HasanAra.
- [ ] Verify with `python3 -m py_compile app/main.py app/settings.py app/exceptions.py`, backend route tests, and frontend build.

---

## Task 9: Integration Verification And Deployment Safety

**Files:**
- Modify: this plan with final verification notes if desired.

- [ ] Run `python3 -m compileall -q app worker alembic scripts`.
- [ ] Run `python3 -m pytest tests/worker tests/test_search_service.py tests/test_routes_search.py tests/test_archive_routes.py tests/test_routes_exports.py -q`.
- [ ] Run `npm --prefix frontend test -- --run`.
- [ ] Run `npm --prefix frontend run build`.
- [ ] Rebuild API/frontend: `rtk docker compose -p hasanara -f docker-compose.yml -f docker-compose.gtx1080.yml -f docker-compose.hasanara.yml up -d --build api frontend`.
- [ ] Rebuild worker only after queue-safe checkpoint: `rtk docker compose -p hasanara -f docker-compose.yml -f docker-compose.gtx1080.yml -f docker-compose.hasanara.yml up -d --build worker`.
- [ ] Verify public endpoints:

```bash
rtk curl -fsS https://hasanara.subcult.tv/api/health
rtk curl -fsS 'https://hasanara.subcult.tv/api/archive/summary?recent_limit=2&popular_limit=3'
rtk curl -fsS 'https://hasanara.subcult.tv/api/search?q=hasan&source=best&limit=1'
```

Expected: all return successful JSON.

---

## Execution Order

1. Task 0: docs/vocabulary/ADR
2. Task 1: caption ingest Module
3. Task 2: YouTube Adapter
4. Task 3: native video pipeline
5. Task 4: search repository split
6. Task 5: search orchestrator
7. Task 6: archive summary Module
8. Task 7: frontend product kernels
9. Task 8: dead billing cleanup
10. Task 9: integration verification

Do not run Task 3 while a long Whisper job is near completion unless restarting the worker is acceptable.

Do not change live worker deployment until Task 1 and Task 2 tests pass.

After each task, run task-specific tests, run compile/build checks for touched files, and review with `review-quality` before continuing.
