# Archive Metadata and Explore Overhaul Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Recommended path:
> dispatch a fresh subagent per task, review each result with `review-quality`,
> then continue. For complex multi-agent splits, use
> `parallel-feature-development`, `team-composition-patterns`, and
> `team-communication-protocols`. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Add admin-managed VOD-level people and content tags, correct curated archive periods, and redesign `/explore` around period, person, and tag discovery.

**Architecture:** Keep this pass VOD-level only: people/guests and labels like `chadvice`, `okbuddy`, `gaming`, and `guests` attach to videos, not transcript segments or time ranges. Add normalized metadata tables with join tables, expose them through admin APIs and selected public video/explore contracts, then redesign `/explore` into a discovery dashboard that can grow into segment-level labels later without schema churn.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy text queries, Alembic, PostgreSQL, React, TypeScript, React Router, ky, Vitest/Testing Library, pytest.

---

## Confirmed Scope

- Remove `october-7-leadup` from curated period seeds.
- Keep `october-7` and `october-7-fallout` unless a future request removes them.
- Add Russian invasion of Ukraine periods:
  - `russia-ukraine-invasion-leadup`: `2021-11-01` → `2022-02-23`, kind `leadup`.
  - `russia-ukraine-invasion`: `2022-02-24` → `2022-03-31`, kind `event`.
  - `russia-ukraine-invasion-fallout`: `2022-02-24` → `2022-12-31`, kind `fallout`.
- Add current midterms leadup:
  - `2026-midterms-leadup`: generated from current date at seed time through `2026-11-03`, kind `leadup`.
- Add annual `8/21` date periods for every archive year represented in videos, plus at least the current year seed if there are no videos for that year.
- Add video-level people/guest metadata first; do not implement segment/time-range person appearance yet.
- Add video-level content tags/categories first for labels like `chadvice`, `okbuddy`, `gaming`, `guests`; do not mutate transcript segments yet.
- Add admin table/editor for video metadata.
- Show people/tags on public VOD page and VOD cards where space allows.
- Include `/explore` layout overhaul in this work.

## Explicit Non-Goals

- No automatic face/speaker recognition.
- No segment-level or timestamp-range labels in this pass.
- No public people/tag filters on `/search` in this pass unless required by `/explore` internal links.
- No destructive hard-delete for metadata terms; use status fields (`published`/`hidden`) to preserve joins.
- No pricing/billing changes.

## File Structure

### Backend

- Create: `alembic/versions/20260604_1800_add_video_metadata.py`
  - Tables: `archive_people`, `archive_video_people`, `archive_video_tags`, `archive_video_taggings`.
- Modify: `app/schemas.py`
  - Public metadata models: `ArchivePerson`, `ArchiveVideoTag`.
  - Admin models: create/update/list responses for people, tags, and video metadata.
  - Extend `VideoInfo` with `people` and `tags` arrays.
- Create: `app/archive/video_metadata_repository.py`
  - Own metadata CRUD, video joins, seed tags, and list helpers.
- Modify: `app/archive/repository.py`
  - Include people/tags in archive summary recent/relevant VOD cards if those cards use `VideoInfo`.
- Modify: `app/crud.py`
  - Include people/tags in `get_video`, `list_videos`, and any helper that constructs `VideoInfo` dictionaries.
- Modify: `app/routes/videos.py`
  - Ensure `/videos/{id}` returns people/tags through `VideoInfo`.
- Modify: `app/routes/archive.py`
  - Correct curated period seeds if the seed route delegates there, or keep seed data in repository only.
  - Add admin routes under `/admin/archive/metadata/*`.
  - Add public explore metadata endpoints if the redesigned `/explore` needs them.
- Modify: `app/archive/intelligence_repository.py`
  - Period seed corrections.
  - Add people/tag facets to intelligence response if `/explore` consumes one composed endpoint.
- Modify: `scripts/backfill_archive_intelligence.py`
  - Ensure seed mode handles corrected period seeds and default metadata tags without duplicate rows.

### Frontend

- Modify: `frontend/src/types/api.ts`
  - Add `ArchivePerson`, `ArchiveVideoTag`, `ArchiveVideoMetadataAdmin*` types.
  - Extend `VideoInfo` with `people` and `tags`.
- Modify: `frontend/src/services/api.ts`
  - Add typed helpers only if existing conventions prefer service wrappers; otherwise direct `http` usage in admin pages is acceptable.
- Create: `frontend/src/routes/admin/AdminVideoMetadata.tsx`
  - Admin editor for people, tags, and assigning them to VODs.
- Modify: `frontend/src/routes/admin/AdminLayout.tsx`
  - Add `Metadata` nav link.
- Modify: `frontend/src/main.tsx`
  - Add `/admin/metadata` route.
- Modify: `frontend/src/routes/VideoPage.tsx`
  - Display people/tags near title and metadata panel.
- Modify: VOD card/list components or pages that render `VideoInfo`
  - Candidate files: `frontend/src/routes/HomePage.tsx`, `frontend/src/routes/StreamsPage.tsx`, `frontend/src/routes/ExplorePage.tsx`.
  - Add compact chips where there is space.
- Rewrite: `frontend/src/routes/ExplorePage.tsx`
  - New layout: discovery header, period selector/sidebar, featured period panel, people/tag rails, topic cards, evidence/timeline section.
- Modify tests:
  - `tests/test_archive_routes.py`
  - `tests/test_archive_summary_repository.py`
  - Create `tests/test_video_metadata_repository.py`
  - `frontend/src/tests/AdminVideoMetadata.test.tsx`
  - `frontend/src/tests/VideoPage.test.tsx` or existing video tests
  - `frontend/src/tests/ExplorePage.test.tsx`
  - `frontend/src/tests/api.test.ts`

---

## Data Model Contract

### `archive_people`

```sql
CREATE TABLE archive_people (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'published',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `archive_video_people`

```sql
CREATE TABLE archive_video_people (
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    person_id UUID NOT NULL REFERENCES archive_people(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'guest',
    confidence TEXT NOT NULL DEFAULT 'admin',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (video_id, person_id)
);
```

### `archive_video_tags`

```sql
CREATE TABLE archive_video_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'category',
    description TEXT,
    status TEXT NOT NULL DEFAULT 'published',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Initial tag seeds:

```text
chadvice, okbuddy, gaming, guests, news, politics, react, debate, interview
```

### `archive_video_taggings`

```sql
CREATE TABLE archive_video_taggings (
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES archive_video_tags(id) ON DELETE CASCADE,
    confidence TEXT NOT NULL DEFAULT 'admin',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (video_id, tag_id)
);
```

### Public API Shapes

```python
class ArchivePerson(BaseModel):
    slug: str
    display_name: str
    aliases: list[str] = []
    description: str | None = None
    role: str | None = None


class ArchiveVideoTag(BaseModel):
    slug: str
    label: str
    kind: str = "category"
    description: str | None = None
```

Extend `VideoInfo`:

```python
people: list[ArchivePerson] = Field(default_factory=list)
tags: list[ArchiveVideoTag] = Field(default_factory=list)
```

---

## `/explore` Layout Contract

The current `/explore` page no longer fits once periods, people, topics, and tags are all first-class. Replace the single long stacked page with a dashboard layout:

1. **Hero / command strip**
   - Title: `Explore the HasanAbi VOD archive`.
   - Quick stats: total VODs, transcript hours, selected period count.
   - Primary controls: period kind tabs and selected period dropdown.
2. **Left discovery rail on desktop, collapsible top rail on mobile**
   - Period groups: Latest, Months, Weeks, Events, Leadups, Fallout, Holidays, Anniversaries, Dates.
   - Highlight current selection.
3. **Main selected-period panel**
   - Period title, date range, VOD count, duration, summary.
   - Evidence moments with video/time links.
4. **Discovery facets**
   - People rail: top people/guests for current selection or recently tagged VODs.
   - Tags rail: content tags such as chadvice/okbuddy/gaming/guests.
   - Topic cards remain but move below the selected period panel.
5. **Timeline/evidence section**
   - Timeline should show only the selected period scope by default.
   - Provide clear empty states for periods with no calculated rows.

Responsive acceptance:

- 320px: single column, rails become horizontal chip groups.
- 768px: controls and selected period panel stack cleanly.
- 1024px+: left rail + main content two-column layout.
- 1440px: max width remains readable; no overly wide evidence text.

---

## Task 1: Period Seed Corrections

**Files:**
- Modify: `app/archive/intelligence_repository.py`
- Modify: `tests/test_archive_summary_repository.py` or create focused test in `tests/test_archive_routes.py`

- [ ] **Step 1: Write a failing seed test**

Add a test that calls `seed_named_periods(db_session)` and verifies the curated period set.

```python
def test_seed_named_periods_corrects_current_curated_windows(db_session):
    from app.archive.intelligence_repository import seed_named_periods
    from sqlalchemy import text

    seed_named_periods(db_session)
    db_session.commit()

    rows = db_session.execute(
        text("SELECT slug, kind, date_from, date_to FROM archive_named_periods")
    ).mappings().all()
    by_slug = {row["slug"]: row for row in rows}

    assert "october-7-leadup" not in by_slug
    assert by_slug["russia-ukraine-invasion-leadup"]["kind"] == "leadup"
    assert str(by_slug["russia-ukraine-invasion-leadup"]["date_from"]) == "2021-11-01"
    assert str(by_slug["russia-ukraine-invasion-leadup"]["date_to"]) == "2022-02-23"
    assert by_slug["russia-ukraine-invasion"]["kind"] == "event"
    assert str(by_slug["russia-ukraine-invasion"]["date_from"]) == "2022-02-24"
    assert by_slug["russia-ukraine-invasion-fallout"]["kind"] == "fallout"
    assert str(by_slug["russia-ukraine-invasion-fallout"]["date_to"]) == "2022-12-31"
    assert by_slug["2026-midterms-leadup"]["kind"] == "leadup"
    assert str(by_slug["2026-midterms-leadup"]["date_to"]) == "2026-11-03"
    assert any(slug.endswith("-august-21") for slug in by_slug)
```

- [ ] **Step 2: Run the focused test and verify failure**

Run:

```bash
uv run --no-project --with fastapi --with httpx --with sqlalchemy --with psycopg --with psycopg-binary --with pytest --with pydantic --with pydantic-settings --with python-multipart --with itsdangerous --with passlib --with bcrypt --with email-validator --with pyjwt --with pytest-asyncio --with redis --with alembic --with openai --with slowapi --with psutil --with reportlab --with prometheus-client python -c "import app.ytdlp_validation, pytest, sys; sys.exit(pytest.main(['tests/test_archive_summary_repository.py::test_seed_named_periods_corrects_current_curated_windows','-q']))"
```

Expected: FAIL because `october-7-leadup` still exists and Ukraine/midterms/annual 8/21 periods are missing.

- [ ] **Step 3: Update curated period generation**

In `app/archive/intelligence_repository.py`:

- Remove the static `october-7-leadup` entry.
- Add static Ukraine entries shown above.
- Add `2026-midterms-leadup` with `date_from=date.today()` and `date_to=date(2026, 11, 3)`; clamp `date_from` to no later than `2026-11-03` so seed remains valid after election day.
- Add a helper that returns annual August 21 date periods for archive years derived from videos plus current year:

```python
def _annual_august_21_periods(db) -> list[dict[str, object]]:
    years = {
        row[0]
        for row in db.execute(
            text("SELECT DISTINCT EXTRACT(YEAR FROM uploaded_at)::int FROM videos WHERE uploaded_at IS NOT NULL")
        ).all()
        if row[0]
    }
    years.add(date.today().year)
    return [
        {
            "slug": f"{year}-august-21",
            "label": f"August 21, {year}",
            "kind": "anniversary",
            "date_from": date(year, 8, 21),
            "date_to": date(year, 8, 21),
            "description": "Annual August 21 archive marker",
        }
        for year in sorted(years)
    ]
```

Make `seed_named_periods(db)` seed `CURATED_NAMED_PERIODS + tuple(_annual_august_21_periods(db))`.

- [ ] **Step 4: Run focused test and archive tests**

Run the focused test, then:

```bash
uv run --no-project --with fastapi --with httpx --with sqlalchemy --with psycopg --with psycopg-binary --with pytest --with pydantic --with pydantic-settings --with python-multipart --with itsdangerous --with passlib --with bcrypt --with email-validator --with pyjwt --with pytest-asyncio --with redis --with alembic --with openai --with slowapi --with psutil --with reportlab --with prometheus-client python -c "import app.ytdlp_validation, pytest, sys; sys.exit(pytest.main(['tests/test_archive_routes.py','tests/test_archive_summary_repository.py','-q']))"
```

Expected: PASS with existing skips only.

- [ ] **Step 5: Commit**

```bash
rtk git add app/archive/intelligence_repository.py tests/test_archive_summary_repository.py tests/test_archive_routes.py
rtk git commit -m "Update curated archive periods"
```

---

## Task 2: Metadata Migration and Backend Repository

**Files:**
- Create: `alembic/versions/20260604_1800_add_video_metadata.py`
- Create: `app/archive/video_metadata_repository.py`
- Create: `tests/test_video_metadata_repository.py`

- [ ] **Step 1: Write repository tests first**

Create tests for:

- Creating/listing people.
- Creating/listing tags.
- Assigning people/tags to a video.
- Getting metadata for multiple video IDs.
- Hidden people/tags are excluded from public metadata but visible to admin list helpers.

Example core assertions:

```python
def test_video_metadata_assignment_round_trip(db_session):
    from app.archive.video_metadata_repository import (
        create_person,
        create_tag,
        set_video_metadata,
        get_video_metadata_map,
    )

    video_id = _create_completed_video(db_session, youtube_id="meta1", title="Metadata VOD")
    person = create_person(db_session, {"display_name": "Guest One", "slug": "guest-one"})
    tag = create_tag(db_session, {"label": "Chadvice", "slug": "chadvice", "kind": "category"})

    set_video_metadata(
        db_session,
        video_id,
        people=[{"slug": person["slug"], "role": "guest"}],
        tags=[{"slug": tag["slug"]}],
    )
    db_session.commit()

    metadata = get_video_metadata_map(db_session, [video_id])

    assert metadata[str(video_id)]["people"][0]["display_name"] == "Guest One"
    assert metadata[str(video_id)]["people"][0]["role"] == "guest"
    assert metadata[str(video_id)]["tags"][0]["label"] == "Chadvice"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run --no-project --with fastapi --with httpx --with sqlalchemy --with psycopg --with psycopg-binary --with pytest --with pydantic --with pydantic-settings --with python-multipart --with itsdangerous --with passlib --with bcrypt --with email-validator --with pyjwt --with pytest-asyncio --with redis --with alembic --with openai --with slowapi --with psutil --with reportlab --with prometheus-client python -c "import app.ytdlp_validation, pytest, sys; sys.exit(pytest.main(['tests/test_video_metadata_repository.py','-q']))"
```

Expected: FAIL because migration/repository do not exist.

- [ ] **Step 3: Add migration**

Create the four tables from the Data Model Contract. Add indexes:

```python
op.create_index("ix_archive_people_status", "archive_people", ["status"])
op.create_index("ix_archive_video_people_video_id", "archive_video_people", ["video_id"])
op.create_index("ix_archive_video_people_person_id", "archive_video_people", ["person_id"])
op.create_index("ix_archive_video_tags_status", "archive_video_tags", ["status"])
op.create_index("ix_archive_video_taggings_video_id", "archive_video_taggings", ["video_id"])
op.create_index("ix_archive_video_taggings_tag_id", "archive_video_taggings", ["tag_id"])
```

Downgrade drops indexes and tables in reverse dependency order.

- [ ] **Step 4: Add repository implementation**

Implement `app/archive/video_metadata_repository.py` with these functions:

```python
def slugify(value: str) -> str: ...
def seed_default_tags(db) -> dict[str, int]: ...
def create_person(db, payload: dict) -> dict: ...
def update_person(db, slug: str, payload: dict) -> dict | None: ...
def list_people_admin(db, q: str | None = None, status: str | None = None, limit: int = 200, offset: int = 0) -> list[dict]: ...
def create_tag(db, payload: dict) -> dict: ...
def update_tag(db, slug: str, payload: dict) -> dict | None: ...
def list_tags_admin(db, q: str | None = None, status: str | None = None, kind: str | None = None, limit: int = 200, offset: int = 0) -> list[dict]: ...
def set_video_metadata(db, video_id, people: list[dict], tags: list[dict]) -> dict: ...
def get_video_metadata_map(db, video_ids: list) -> dict[str, dict[str, list[dict]]]: ...
def search_videos_for_admin(db, q: str | None = None, limit: int = 50) -> list[dict]: ...
```

Implementation rules:

- Slug defaults come from display name/label.
- Duplicate slug raises the project validation exception if available; otherwise let DB uniqueness surface and tests can assert non-500 route behavior later.
- `set_video_metadata` replaces all joins for a video in one transaction but does not commit.
- Public `get_video_metadata_map` filters to `status='published'` people/tags.

- [ ] **Step 5: Run repository tests**

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
rtk git add alembic/versions/20260604_1800_add_video_metadata.py app/archive/video_metadata_repository.py tests/test_video_metadata_repository.py
rtk git commit -m "Add video metadata repository"
```

---

## Task 3: Backend API and VideoInfo Contract

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/crud.py`
- Modify: `app/routes/videos.py`
- Modify: `app/routes/archive.py`
- Modify: `tests/test_archive_routes.py`

- [ ] **Step 1: Add failing API route tests**

Add tests that assert:

- Unauthenticated `/admin/archive/metadata/people` returns `401` or `403` according to existing admin behavior.
- Admin route registrations exist in OpenAPI.
- `/videos/{id}` includes `people` and `tags` arrays.

Route list to test:

```text
GET /admin/archive/metadata/people
POST /admin/archive/metadata/people
PATCH /admin/archive/metadata/people/{slug}
GET /admin/archive/metadata/tags
POST /admin/archive/metadata/tags
PATCH /admin/archive/metadata/tags/{slug}
GET /admin/archive/metadata/videos
GET /admin/archive/metadata/videos/{video_id}
PUT /admin/archive/metadata/videos/{video_id}
POST /admin/archive/metadata/seed-tags
```

- [ ] **Step 2: Run route tests and verify failure**

Expected: FAIL due to missing schema/routes.

- [ ] **Step 3: Add schemas**

Add public and admin Pydantic models in `app/schemas.py`:

```python
class ArchivePerson(BaseModel):
    slug: str
    display_name: str
    aliases: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    role: Optional[str] = None


class ArchiveVideoTag(BaseModel):
    slug: str
    label: str
    kind: str = "category"
    description: Optional[str] = None


class ArchivePersonAdminResponse(ArchivePerson):
    id: uuid.UUID
    status: str = "published"
    sort_order: int = 0


class ArchiveVideoTagAdminResponse(ArchiveVideoTag):
    id: uuid.UUID
    status: str = "published"
    sort_order: int = 0


class ArchivePersonUpsert(BaseModel):
    slug: Optional[str] = None
    display_name: str
    aliases: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    status: str = "published"
    sort_order: int = 0


class ArchiveVideoTagUpsert(BaseModel):
    slug: Optional[str] = None
    label: str
    kind: str = "category"
    description: Optional[str] = None
    status: str = "published"
    sort_order: int = 0


class ArchiveVideoMetadataAssignment(BaseModel):
    people: List[dict] = Field(default_factory=list)
    tags: List[dict] = Field(default_factory=list)
```

Extend `VideoInfo` with `people: List[ArchivePerson]` and `tags: List[ArchiveVideoTag]`.

- [ ] **Step 4: Update video query builders**

Where `VideoInfo` dictionaries are returned, collect video IDs and merge metadata from `get_video_metadata_map`. If a helper builds one video, pass a one-item list.

Acceptance:

```json
{
  "id": "...",
  "title": "...",
  "people": [{"slug":"guest-one","display_name":"Guest One","role":"guest"}],
  "tags": [{"slug":"chadvice","label":"Chadvice","kind":"category"}]
}
```

- [ ] **Step 5: Add admin routes**

Add routes in `app/routes/archive.py` using `Depends(require_role(ROLE_ADMIN))`:

```python
@router.get("/admin/archive/metadata/people")
@router.post("/admin/archive/metadata/people")
@router.patch("/admin/archive/metadata/people/{slug}")
@router.get("/admin/archive/metadata/tags")
@router.post("/admin/archive/metadata/tags")
@router.patch("/admin/archive/metadata/tags/{slug}")
@router.get("/admin/archive/metadata/videos")
@router.get("/admin/archive/metadata/videos/{video_id}")
@router.put("/admin/archive/metadata/videos/{video_id}")
@router.post("/admin/archive/metadata/seed-tags")
```

Admin video search response should include basic video fields plus assigned people/tags.

- [ ] **Step 6: Run tests**

Run backend archive route tests and repository tests. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
rtk git add app/schemas.py app/crud.py app/routes/videos.py app/routes/archive.py tests/test_archive_routes.py
rtk git commit -m "Expose video metadata APIs"
```

---

## Task 4: Admin Metadata UI

**Files:**
- Create: `frontend/src/routes/admin/AdminVideoMetadata.tsx`
- Modify: `frontend/src/routes/admin/AdminLayout.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/src/tests/AdminVideoMetadata.test.tsx`

- [ ] **Step 1: Write UI tests first**

Tests should mock `http` and cover:

- Rendering people/tags tabs or sections.
- Creating a person.
- Creating a tag.
- Searching videos.
- Assigning people/tags to a video.
- Seed default tags button.

Expected mocked calls:

```text
POST admin/archive/metadata/people
POST admin/archive/metadata/tags
GET admin/archive/metadata/videos?q=...
PUT admin/archive/metadata/videos/{video_id}
POST admin/archive/metadata/seed-tags
```

- [ ] **Step 2: Run UI test and verify failure**

```bash
npm --prefix frontend test -- --run src/tests/AdminVideoMetadata.test.tsx
```

Expected: FAIL because page does not exist.

- [ ] **Step 3: Add frontend types**

Add types matching backend schema in `frontend/src/types/api.ts` and extend `VideoInfo`.

- [ ] **Step 4: Implement admin page**

Use existing admin visual primitives (`surface-card`, `form-control`, `btn`, dense tables). Layout:

- Header: `Video metadata`.
- Section 1: People editor table/form.
- Section 2: Tags editor table/form with seed button.
- Section 3: Video assignment editor:
  - Search VODs by title/youtube_id.
  - Select a VOD.
  - Multi-select people and tags with checkboxes.
  - Save assignment.

Avoid complex combo-box libraries; use native controls and checkboxes for reliability.

- [ ] **Step 5: Wire admin nav/route**

Add `Metadata` link to `AdminLayout` and route child `{ path: 'metadata', element: <AdminVideoMetadata /> }` in `main.tsx`.

- [ ] **Step 6: Run tests/build**

```bash
npm --prefix frontend test -- --run src/tests/AdminVideoMetadata.test.tsx
npm --prefix frontend run build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
rtk git add frontend/src/routes/admin/AdminVideoMetadata.tsx frontend/src/routes/admin/AdminLayout.tsx frontend/src/main.tsx frontend/src/types/api.ts frontend/src/tests/AdminVideoMetadata.test.tsx
rtk git commit -m "Add admin video metadata editor"
```

---

## Task 5: Public Video Metadata Display

**Files:**
- Modify: `frontend/src/routes/VideoPage.tsx`
- Modify candidate VOD card/list files: `frontend/src/routes/HomePage.tsx`, `frontend/src/routes/StreamsPage.tsx`, `frontend/src/routes/ExplorePage.tsx`
- Modify tests: existing video/page tests where appropriate

- [ ] **Step 1: Add failing display tests**

Update a video page test fixture so `video.people` contains `Guest One` and `video.tags` contains `Chadvice`. Assert both chips render near the title/metadata section.

- [ ] **Step 2: Implement reusable chip markup locally**

No new component is required unless duplication grows. Use accessible lists:

```tsx
{video.people?.length ? (
  <div aria-label="People on stream" className="flex flex-wrap gap-2">
    {video.people.map((person) => (
      <span key={person.slug} className="rounded-full border border-border bg-surface-muted px-2 py-1 text-xs text-muted">
        {person.display_name}
      </span>
    ))}
  </div>
) : null}
```

Add tags similarly.

- [ ] **Step 3: Add compact chips to cards where safe**

Show at most 3 chips per card and `+N` overflow to avoid clutter.

- [ ] **Step 4: Run frontend tests/build**

```bash
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/routes/VideoPage.tsx frontend/src/routes/HomePage.tsx frontend/src/routes/StreamsPage.tsx frontend/src/routes/ExplorePage.tsx frontend/src/tests
rtk git commit -m "Show people and tags on VODs"
```

---

## Task 6: `/explore` Redesign

**Files:**
- Modify: `app/schemas.py` if intelligence response gets facet fields
- Modify: `app/archive/intelligence.py` or `app/archive/intelligence_repository.py`
- Modify: `app/routes/archive.py`
- Modify: `frontend/src/routes/ExplorePage.tsx`
- Modify: `frontend/src/tests/ExplorePage.test.tsx`
- Modify: `frontend/src/tests/api.test.ts`

- [ ] **Step 1: Decide endpoint shape from current implementation**

Prefer extending existing `/archive/intelligence` instead of creating multiple frontend calls. Add optional fields:

```python
people: List[ArchivePerson] = Field(default_factory=list)
tags: List[ArchiveVideoTag] = Field(default_factory=list)
```

If naming conflicts with selected period evidence, use `featured_people` and `featured_tags`.

- [ ] **Step 2: Add failing contract tests**

Update `tests/test_archive_routes.py` to assert `/archive/intelligence?period=...` includes people/tags arrays, even if empty, and selected-period VODs include metadata.

- [ ] **Step 3: Implement backend facets**

Use `get_video_metadata_map` against the videos already selected for the current period. Aggregate unique published people/tags by frequency and sort by frequency desc, then `sort_order`/label.

- [ ] **Step 4: Add failing frontend layout test**

Update `ExplorePage.test.tsx` fixture with:

```ts
people: [{ slug: 'guest-one', display_name: 'Guest One' }],
tags: [{ slug: 'gaming', label: 'Gaming', kind: 'category' }]
```

Assert:

- Page has `Explore the HasanAbi VOD archive`.
- Period rail exists.
- Selected period panel exists.
- `Guest One` and `Gaming` appear in discovery facets.
- Evidence section still links to video timestamps.

- [ ] **Step 5: Rewrite `ExplorePage.tsx` layout**

Implement the layout contract above. Preserve existing behavior:

- Default selected period remains latest calculated month.
- Period picker still supports predefined periods.
- Topic count selector remains if still useful, but move it into an advanced/control area.
- Timeline stays scoped to selected period.
- No free-form date inputs.

- [ ] **Step 6: Responsive and accessibility pass**

Check:

- 320px no horizontal scroll.
- All filters are labels/buttons, not div-only click targets.
- Loading/error states remain visible.
- Dark mode uses tokens.

- [ ] **Step 7: Run tests/build**

```bash
npm --prefix frontend test -- --run src/tests/ExplorePage.test.tsx src/tests/api.test.ts
npm --prefix frontend run build
uv run --no-project --with fastapi --with httpx --with sqlalchemy --with psycopg --with psycopg-binary --with pytest --with pydantic --with pydantic-settings --with python-multipart --with itsdangerous --with passlib --with bcrypt --with email-validator --with pyjwt --with pytest-asyncio --with redis --with alembic --with openai --with slowapi --with psutil --with reportlab --with prometheus-client python -c "import app.ytdlp_validation, pytest, sys; sys.exit(pytest.main(['tests/test_archive_routes.py','tests/test_archive_summary_repository.py','tests/test_video_metadata_repository.py','-q']))"
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
rtk git add app/schemas.py app/archive/intelligence.py app/archive/intelligence_repository.py app/routes/archive.py frontend/src/routes/ExplorePage.tsx frontend/src/tests/ExplorePage.test.tsx frontend/src/tests/api.test.ts tests/test_archive_routes.py
rtk git commit -m "Overhaul Explore metadata discovery"
```

---

## Task 7: Deployment, Backfill, and Live QA

**Files:**
- Modify only if validation uncovers issues.

- [ ] **Step 1: Run full local validation**

```bash
npm --prefix frontend test -- --run
npm --prefix frontend run build
uv run --no-project --with fastapi --with httpx --with sqlalchemy --with psycopg --with psycopg-binary --with pytest --with pydantic --with pydantic-settings --with python-multipart --with itsdangerous --with passlib --with bcrypt --with email-validator --with pyjwt --with pytest-asyncio --with redis --with alembic --with openai --with slowapi --with psutil --with reportlab --with prometheus-client python -c "import app.ytdlp_validation, pytest, sys; sys.exit(pytest.main(['tests/test_archive_routes.py','tests/test_archive_summary_repository.py','tests/test_video_metadata_repository.py','-q']))"
```

Expected: frontend full tests pass, frontend build passes, backend archive/metadata tests pass with only known skips/warnings.

- [ ] **Step 2: Deploy containers**

```bash
rtk docker compose -p hasanara -f docker-compose.yml -f docker-compose.gtx1080.yml -f docker-compose.hasanara.yml up -d --build api frontend archive-intelligence-refresher
```

- [ ] **Step 3: Run migrations if deployment does not auto-run them**

Use the repo's current migration command/runbook. If unsure, inspect existing deployment scripts before running raw Alembic.

- [ ] **Step 4: Seed/backfill**

```bash
rtk docker exec hasanara-api python3 /app/scripts/backfill_archive_intelligence.py --all --quick
```

Expected:

- Period seed count includes Ukraine/midterms/annual 8/21.
- `october-7-leadup` is not re-created by seed code.
- Default tags are present after metadata seed.

- [ ] **Step 5: Live smoke checks**

Use HTTP/browser checks:

- `/explore` loads and defaults to latest calculated month.
- Period kind lists include leadup/fallout/anniversary where seeded.
- `russia-ukraine-invasion-leadup`, `russia-ukraine-invasion-fallout`, `2026-midterms-leadup`, and a `YYYY-august-21` period are available.
- `/admin/periods` still loads.
- `/admin/metadata` loads shell for authenticated admin, and unauthenticated API calls return `401`/`403`.
- A VOD with assigned metadata shows people/tags on its public page.

- [ ] **Step 6: Final status and commit if needed**

```bash
rtk git status --short --branch
rtk git log --oneline -8
```

If any deployment fixes were needed:

```bash
rtk git add <changed-files>
rtk git commit -m "Stabilize archive metadata deployment"
```

Do not push unless the user explicitly requests it; previous sessions were blocked by missing `git.subcult.tv` credentials.

---

## Review Checklist

- [ ] `october-7-leadup` removed from seed code and not recreated by backfill.
- [ ] Ukraine periods use Ukraine, not Iran.
- [ ] Midterms leadup is present and date range is valid.
- [ ] Annual `8/21` periods exist for archive years/current year.
- [ ] People/guests are VOD-level only.
- [ ] Content labels are VOD-level only.
- [ ] Public `VideoInfo` includes `people` and `tags` arrays without breaking old consumers.
- [ ] Admin metadata routes are admin-gated.
- [ ] `/explore` layout supports periods, people, tags, topics, and evidence without reintroducing free-form date inputs.
- [ ] Tests/build/backend validation pass.
- [ ] Live deploy/backfill/smoke checks pass.

## Execution Recommendation

Use subagent-driven implementation with review gates:

1. Backend seed corrections.
2. Backend metadata migration/repository/API.
3. Admin metadata UI.
4. Public VOD metadata display.
5. `/explore` redesign.
6. Deploy/backfill/live QA.

This split keeps schema decisions isolated before UI work and lets `/explore` consume stable contracts.
