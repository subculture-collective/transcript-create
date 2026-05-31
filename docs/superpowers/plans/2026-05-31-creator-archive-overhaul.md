# Creator Archive Overhaul Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Recommended path:
> dispatch a fresh subagent per task, review each result with `review-quality`,
> then continue. For complex multi-agent splits, use
> `parallel-feature-development`, `team-composition-patterns`, and
> `team-communication-protocols`. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Reposition Transcript Create as a production-grade **Creator Archive**: a searchable, timestamped memory for one creator's complete body of work.

**Architecture:** Ship production vertical slices that use existing search/video/favorites primitives first, then add minimal durable API contracts where the frontend cannot honestly render archive behavior from current data. Avoid fake AI/topic/people/lore output; topic pages and mention maps are citation-backed search-derived summaries until extraction pipelines exist.

**Tech Stack:** FastAPI, PostgreSQL SQLAlchemy text queries, Pydantic schemas, Vite, React 19, React Router 7, Tailwind v4, Vitest, Playwright.

---

## Scope Decisions

- Product position: **Creator Archive**.
- Implementation depth: **Production slices**.
- Persistence mode: **Repo plan** in `docs/superpowers/plans/`.
- Do not implement unsupported AI claims. “Opinion over time,” lore, people, and claim finder must be represented as disabled/future affordances or citation-backed primitives only.
- Keep backwards compatibility for current flat `/search` consumers where possible.

## File Structure

### Backend

- Modify `app/schemas.py`
  - Add archive/search/topic/timeline schemas: `ArchiveSummary`, `EpisodeSearchGroup`, `SearchMoment`, `GroupedSearchResponse`, `MentionMap`, `TimelineBucket`, `SavedSearch*`.
  - Add optional metadata fields to `SearchHit` for progressive compatibility.
- Modify `app/crud.py`
  - Add aggregation helpers for archive summary, grouped search metadata, mention map, timeline buckets, and saved searches.
- Modify `app/routes/search.py`
  - Add grouped search mode or `/search/grouped`.
  - Add `/search/mention-map` from current searchable segments.
- Create `app/routes/archive.py`
  - `GET /archive/summary`
  - `GET /archive/timeline`
- Create `app/routes/saved_searches.py`
  - `GET /users/me/saved-searches`
  - `POST /users/me/saved-searches`
  - `DELETE /users/me/saved-searches/{id}`
- Modify `app/main.py`
  - Register new routers.
- Add Alembic migration
  - Create `saved_searches` table only. Do not add topic/person/lore tables until extraction model is designed.
- Add backend tests
  - `tests/test_archive_routes.py`
  - `tests/test_grouped_search.py`
  - `tests/test_saved_searches.py`

### Frontend

- Modify `frontend/src/types/api.ts`
  - Add archive/grouped search/mention map/timeline/saved search types.
- Modify `frontend/src/services/api.ts`
  - Add client methods for archive summary, grouped search, mention map, timeline, saved searches.
  - Extend `api.search` options to include all existing backend filters.
- Modify `frontend/src/main.tsx`
  - Add explicit `/search`, `/episodes`, `/topics/:query`, `/timeline`, `/saved` routes.
  - Keep aliases for `/streams` and `/favorites` to avoid breaking existing links/tests.
- Modify `frontend/src/routes/AppLayout.tsx`
  - Rebrand to Creator Archive.
  - Update nav labels.
- Create `frontend/src/routes/HomePage.tsx`
  - Creator archive landing page.
- Modify `frontend/src/routes/SearchPage.tsx`
  - Creator archive search page with filters and grouped episode cards.
- Modify or wrap `frontend/src/routes/StreamsPage.tsx`
  - Reframe as Episodes page.
- Modify `frontend/src/routes/VideoPage.tsx`
  - Reframe as Episode page with search-inside-episode polish.
- Create `frontend/src/routes/TopicPage.tsx`
  - Mention map and grouped moments for a query.
- Create `frontend/src/routes/TimelinePage.tsx`
  - Archive timeline from backend buckets.
- Modify `frontend/src/routes/FavoritesPage.tsx`
  - Reframe as Saved Moments and include Saved Searches if authenticated.
- Add small UI helpers under `frontend/src/features/archive/`
  - formatting helpers for durations, dates, timestamps, grouped search labels.
- Add/update frontend tests
  - `frontend/src/tests/HomePage.test.tsx`
  - `frontend/src/tests/SearchPage.test.tsx`
  - `frontend/src/tests/TopicPage.test.tsx`
  - `frontend/src/tests/TimelinePage.test.tsx`
  - `frontend/src/tests/api.test.ts`

---

## Task 1: Backend Archive Summary

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/crud.py`
- Create: `app/routes/archive.py`
- Modify: `app/main.py`
- Test: `tests/test_archive_routes.py`

- [ ] **Step 1: Add failing route tests**

Create tests that assert `GET /archive/summary` returns:

```json
{
  "creator_name": "Creator Archive",
  "video_count": 2,
  "total_duration_seconds": 5400,
  "transcript_word_count": 12,
  "updated_at": "...",
  "recent_videos": [],
  "popular_searches": []
}
```

Run: `pytest tests/test_archive_routes.py -v`
Expected: FAIL because route/schema do not exist.

- [ ] **Step 2: Add schemas**

Add Pydantic models for:

```python
class ArchivePopularSearch(BaseModel):
    term: str
    frequency: int

class ArchiveSummary(BaseModel):
    creator_name: str = "Creator Archive"
    video_count: int = 0
    total_duration_seconds: int = 0
    transcript_word_count: int = 0
    updated_at: Optional[datetime] = None
    recent_videos: List[VideoInfo] = Field(default_factory=list)
    popular_searches: List[ArchivePopularSearch] = Field(default_factory=list)
```

- [ ] **Step 3: Add CRUD aggregation**

Add `get_archive_summary(db, recent_limit: int = 6, popular_limit: int = 8)` that:
- counts videos with any transcript source,
- sums `videos.duration_seconds`,
- estimates transcript words using `segments.text` plus `youtube_segments.text`,
- returns recent videos using existing `list_videos`,
- returns popular searches from `search_suggestions` if table exists, else empty list.

- [ ] **Step 4: Add router and register it**

Create `app/routes/archive.py` with `router = APIRouter(prefix="", tags=["Archive"])` and `@router.get("/archive/summary", response_model=ArchiveSummary)`.

Register in `app/main.py` alongside existing routers.

- [ ] **Step 5: Verify**

Run:

```bash
pytest tests/test_archive_routes.py -v
python3 -m compileall -q app tests
```

Expected: PASS.

---

## Task 2: Grouped Episode Search Contract

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/crud.py`
- Modify: `app/routes/search.py`
- Test: `tests/test_grouped_search.py`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/services/api.ts`
- Test: `frontend/src/tests/api.test.ts`

- [ ] **Step 1: Add failing backend tests**

Test `GET /search/grouped?q=rent` returns `groups[]`, each with `video` and `moments[]`, preserving timestamp links and source.

Run: `pytest tests/test_grouped_search.py -v`
Expected: FAIL.

- [ ] **Step 2: Add schemas**

Add:

```python
class SearchMoment(BaseModel):
    id: int
    video_id: uuid.UUID
    start_ms: int
    end_ms: int
    snippet: str
    source: Literal["whisper", "youtube", "merged"] = "whisper"

class EpisodeSearchGroup(BaseModel):
    video: VideoInfo
    moments: List[SearchMoment]

class GroupedSearchResponse(BaseModel):
    total_moments: int
    total_videos: int
    groups: List[EpisodeSearchGroup]
    query_time_ms: Optional[int] = None
```

- [ ] **Step 3: Implement grouped query**

Use existing search helpers, then batch-load `VideoInfo` metadata for returned video IDs. Group in backend to avoid N+1 frontend calls.

- [ ] **Step 4: Add frontend API types and client**

Add `GroupedSearchResponse`, `EpisodeSearchGroup`, and `SearchMoment` in `frontend/src/types/api.ts`.

Add `api.searchGrouped(q, opts)` in `frontend/src/services/api.ts` and extend filter options for existing `api.search`.

- [ ] **Step 5: Verify**

Run:

```bash
pytest tests/test_grouped_search.py -v
cd frontend && npm test -- src/tests/api.test.ts --run
```

Expected: PASS.

---

## Task 3: Creator Archive Homepage

**Files:**
- Create: `frontend/src/routes/HomePage.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/routes/AppLayout.tsx`
- Test: `frontend/src/tests/HomePage.test.tsx`

- [ ] **Step 1: Add failing homepage test**

Assert the homepage renders:
- “Creator Archive”
- “Search the complete archive”
- search input placeholder “Search anything they’ve ever talked about...”
- corpus stats
- recent episodes
- suggested searches

Run: `cd frontend && npm test -- src/tests/HomePage.test.tsx --run`
Expected: FAIL.

- [ ] **Step 2: Implement `HomePage`**

Use `api.getArchiveSummary()` and render token-based archive/library UI. Search submit should navigate to `/search?q=<query>`.

- [ ] **Step 3: Route homepage separately from search**

In `frontend/src/main.tsx`, set index route to `HomePage`; add `{ path: 'search', element: <SearchPage /> }`.

- [ ] **Step 4: Rebrand layout**

In `AppLayout`, set brand to `Creator Archive`; nav labels: Home, Search, Episodes, Timeline, Saved, Pricing. Keep admin/auth behavior unchanged.

- [ ] **Step 5: Verify**

Run:

```bash
cd frontend && npm test -- src/tests/HomePage.test.tsx src/tests/auth.test.tsx --run
cd frontend && npm run build
```

Expected: PASS.

---

## Task 4: Archive Search UI with Filters

**Files:**
- Modify: `frontend/src/routes/SearchPage.tsx`
- Create: `frontend/src/features/archive/format.ts`
- Modify: `frontend/src/features/searchTranscript/matches.ts`
- Test: `frontend/src/tests/SearchPage.test.tsx`

- [ ] **Step 1: Add failing tests**

Tests should cover:
- search header says “Search the creator archive”,
- filters serialize into API params,
- grouped episode card shows title, date, match count, moments,
- `Copy timestamp` writes a deep link,
- `Open episode` links to `/v/:videoId`.

- [ ] **Step 2: Implement grouped search rendering**

Use `api.searchGrouped` for query results. Fall back gracefully to flat search only if grouped endpoint fails.

- [ ] **Step 3: Add filters**

Expose date range, duration range, source, and sort. Use existing backend parameters exactly:
- `date_from`
- `date_to`
- `min_duration`
- `max_duration`
- `source`
- `sort_by`

- [ ] **Step 4: Add “Mention Map” summary strip**

For a query, link to `/topics/${encodeURIComponent(q)}` and show `total_moments` / `total_videos` from grouped response.

- [ ] **Step 5: Verify**

Run:

```bash
cd frontend && npm test -- src/tests/SearchPage.test.tsx --run
cd frontend && npm run lint
```

Expected: PASS.

---

## Task 5: Episode Page Polish

**Files:**
- Modify: `frontend/src/routes/VideoPage.tsx`
- Test: `frontend/src/tests/YouTubePlayer.test.tsx` or new `VideoPage.test.tsx`

- [ ] **Step 1: Add tests for archive wording**

Assert the page says “Episode transcript” and the input says “Search inside this episode...”.

- [ ] **Step 2: Add episode metadata card**

Render channel, upload date, duration, transcript source. Use fields already present on `VideoInfo` and `TranscriptResponse`.

- [ ] **Step 3: Add topic/related placeholders only as disabled future cards**

Show “Topic extraction coming later” only if it is clearly disabled and does not pretend data exists.

- [ ] **Step 4: Verify**

Run:

```bash
cd frontend && npm test -- src/tests/YouTubePlayer.test.tsx --run
cd frontend && npm run build
```

Expected: PASS.

---

## Task 6: Topic Page and Mention Map Foundation

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/routes/search.py`
- Create/modify: backend tests for mention map
- Create: `frontend/src/routes/TopicPage.tsx`
- Modify: `frontend/src/main.tsx`
- Test: `frontend/src/tests/TopicPage.test.tsx`

- [ ] **Step 1: Add failing mention map tests**

Test `GET /search/mention-map?q=rent` returns:
- query,
- total moments,
- video count,
- first mention if present,
- latest mention if present,
- top episodes.

- [ ] **Step 2: Implement citation-backed mention map**

Compute from real search results only. Do not summarize opinions.

- [ ] **Step 3: Add `TopicPage`**

Render:
- “Topic: <query>”
- first mention,
- most recent mention,
- top episodes,
- grouped results via `api.searchGrouped`.

- [ ] **Step 4: Verify**

Run:

```bash
pytest tests/test_grouped_search.py -v
cd frontend && npm test -- src/tests/TopicPage.test.tsx --run
```

Expected: PASS.

---

## Task 7: Timeline Page

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/crud.py`
- Modify: `app/routes/archive.py`
- Create: `frontend/src/routes/TimelinePage.tsx`
- Modify: `frontend/src/main.tsx`
- Test: `frontend/src/tests/TimelinePage.test.tsx`

- [ ] **Step 1: Add failing timeline tests**

Assert `GET /archive/timeline` buckets videos by year/month and the UI renders grouped episodes.

- [ ] **Step 2: Implement backend timeline**

Use `videos.uploaded_at` if available, else `created_at`. Include only videos with completed transcript sources by default.

- [ ] **Step 3: Implement frontend timeline**

Render archive chronology with optional query link to `/search?date_from=...&date_to=...`.

- [ ] **Step 4: Verify**

Run:

```bash
pytest tests/test_archive_routes.py -v
cd frontend && npm test -- src/tests/TimelinePage.test.tsx --run
```

Expected: PASS.

---

## Task 8: Episodes Page Rename and Compatibility

**Files:**
- Modify: `frontend/src/routes/StreamsPage.tsx`
- Modify: `frontend/src/main.tsx`
- Test: `frontend/src/tests/StreamsPage.test.tsx`

- [ ] **Step 1: Update tests from streams language to episodes language**

Expected visible copy: “Episodes”, “Browse the archive”, “Search titles, channels, or notes...”.

- [ ] **Step 2: Update route aliases**

Add `/episodes` route pointing to `StreamsPage`. Keep `/streams` as an alias for existing links/tests.

- [ ] **Step 3: Verify**

Run:

```bash
cd frontend && npm test -- src/tests/StreamsPage.test.tsx --run
```

Expected: PASS.

---

## Task 9: Saved Moments and Saved Searches

**Files:**
- Add Alembic migration for `saved_searches`
- Modify: `app/schemas.py`
- Create: `app/routes/saved_searches.py`
- Modify: `app/main.py`
- Test: `tests/test_saved_searches.py`
- Modify: `frontend/src/routes/FavoritesPage.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: Add failing backend tests**

Authenticated users can list, create, and delete saved searches. Unauthenticated users get empty or unauthorized behavior consistent with favorites.

- [ ] **Step 2: Add migration**

Create table:

```sql
CREATE TABLE saved_searches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, query)
);
```

- [ ] **Step 3: Implement routes and frontend client**

Expose saved searches under `/users/me/saved-searches`.

- [ ] **Step 4: Reframe Favorites page**

Visible page title: “Saved”. Sections: “Saved moments” and “Saved searches”. Keep local favorites fallback.

- [ ] **Step 5: Verify**

Run:

```bash
pytest tests/test_saved_searches.py -v
cd frontend && npm test -- src/tests/favorites.test.ts --run
```

Expected: PASS.

---

## Task 10: Final Quality Gates

**Files:**
- Update docs if any public routes changed: `docs/ADVANCED_SEARCH.md`, `README.md` highlights if appropriate.

- [ ] **Step 1: Backend verification**

Run:

```bash
python3 -m compileall -q app tests alembic
pytest tests/test_archive_routes.py tests/test_grouped_search.py tests/test_saved_searches.py -v
```

- [ ] **Step 2: Frontend verification**

Run:

```bash
cd frontend && npm run lint
cd frontend && npm test -- --run
cd frontend && npm run build
```

- [ ] **Step 3: E2E smoke**

Run when local services are available:

```bash
cd e2e && npm test -- search.spec.ts
```

- [ ] **Step 4: Manual acceptance checklist**

- Homepage feels like a creator archive, not a single-video transcript tool.
- Search answers “where and when did they talk about this?”
- Results are grouped by episode with timestamped moments.
- Episode pages still play and deep-link correctly.
- Topic pages only make citation-backed claims.
- Timeline uses real episode dates.
- Saved page includes moments and authenticated saved searches.
- Existing `/streams`, `/favorites`, and `/v/:videoId` links still work.

---

## Deferred Features

- Opinion over time: requires citation-backed summarization workflow and tests against unsupported claims.
- People/guest pages: requires entity extraction or guest metadata.
- Lore tracker: requires curated or extracted recurring bits.
- Claim finder: requires claim classification model or deterministic extractor.
- New mentions since last visit: requires saved-search snapshots and notification/read-state design.
- Creator-branded multi-tenant config: requires deployment/config product decision.
