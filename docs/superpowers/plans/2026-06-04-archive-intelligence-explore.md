# Archive Intelligence Explore Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Recommended path:
> dispatch a fresh subagent per task, review each result with `review-quality`,
> then continue. For complex multi-agent splits, use
> `parallel-feature-development`, `team-composition-patterns`, and
> `team-communication-protocols`. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Build `/explore`, a unified Archive Intelligence destination that combines timeline, topic cards, trending/suggested searches, summary stats, and evidence-cited period summaries.

**Architecture:** Phase 1 is intentionally additive and cached-by-existing-data: a new `/archive/intelligence` endpoint composes existing archive summary, timeline, popular searches, and mention-map primitives into one typed response. The frontend adds a new `ExplorePage` and nav item using that response, while keeping the old hidden `/timeline` route intact. Hybrid curated/automatic topics, transcript+search trending, and cited AI summaries are represented in the data contract now; durable extraction tables and generated summaries can fill the same contract later.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy text queries, React, TypeScript, React Router, ky, Vitest/Testing Library, pytest.

---

## File Structure

- Modify `app/schemas.py`
  - Add Archive Intelligence response models next to existing archive summary/timeline schemas.
  - Fix backend default `ArchiveSummary.creator_name` from `HasanAra` to `HasAnAra`.
- Create `app/archive/intelligence.py`
  - Compose existing archive data into a first-generation intelligence response.
  - Own curated seed topics and fallback logic.
- Modify `app/routes/archive.py`
  - Add `GET /archive/intelligence` route.
  - Keep `/archive/summary` and `/archive/timeline` unchanged.
- Modify `tests/test_archive_routes.py`
  - Add route tests for `/archive/intelligence` shape, topic/trending fields, and cited period summaries.
- Modify `frontend/src/types/api.ts`
  - Add `ExploreIntelligenceResponse` and supporting types.
- Modify `frontend/src/services/api.ts`
  - Add `api.getExploreIntelligence()`.
- Create `frontend/src/routes/ExplorePage.tsx`
  - Render hero stats, trending topics, suggested searches, topic atlas, period cards, and evidence links.
- Modify `frontend/src/main.tsx`
  - Register `/explore` route.
- Modify `frontend/src/routes/AppLayout.tsx`
  - Add `Explore` nav item.
- Create `frontend/src/tests/ExplorePage.test.tsx`
  - Test the page renders composed intelligence and links correctly.
- Modify `frontend/src/tests/api.test.ts`
  - Test the new API service method.

---

## Additional UX Notes To Carry Into Execution

These notes are approved scope-adjacent improvements. Implement them after the core `/archive/intelligence` + `/explore` path is stable, unless a task already touches the same file and the change is small.

### VOD Page

- Theater mode currently lets transcript content scroll over the video. Fix the theater layout so the video remains visually protected and transcript scrolling happens below or in a separate non-overlapping pane.
- Transcript auto-follow should unlock when the user manually scrolls. Once unlocked, playback should not force-scroll the transcript back to the current sentence.
- Add a visible “Follow current sentence” / “Resume auto-follow” button when auto-follow is unlocked.
- Reader mode needs a play/pause control so users can control playback without leaving the reader layout.
- VOD lists should automatically sort by newest broadcast/upload date by default.

### Home

- Add a clear signup CTA on the home page. It should be visible without feeling like pricing/subscription UI and should route through the existing auth flow.

### Search

- Add suggested searches to the search page, preferably using the same `suggested_searches` data from `/archive/intelligence` once available.
- Suggested searches should be clickable chips that populate or navigate to a search query.

---

### Task 1: Backend schema contract

**Files:**
- Modify: `app/schemas.py:193-257`
- Test: `tests/test_archive_routes.py`

- [ ] **Step 1: Add a failing route-contract test**

Append this test method to `class TestArchiveRoutes` in `tests/test_archive_routes.py`:

```python
    def test_archive_intelligence_route_returns_explore_contract(self, client: TestClient, db_session):
        video_id = _create_completed_video(
            db_session,
            youtube_id="explore1",
            title="Explore VOD",
            uploaded_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            duration_seconds=3600,
        )
        db_session.execute(
            text("INSERT INTO segments (video_id, start_ms, end_ms, text, speaker_label) VALUES (:vid, 1000, 5000, :text, NULL)"),
            {"vid": str(video_id), "text": "ICE protests and Gaza coverage made this a major news segment."},
        )
        db_session.execute(
            text("INSERT INTO search_suggestions (term, frequency) VALUES (:term, :frequency)"),
            {"term": "ice protests", "frequency": 7},
        )
        db_session.commit()

        response = client.get("/archive/intelligence?topic_limit=4&period_limit=3")

        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["creator_name"] == "HasAnAra"
        assert data["exploration_modes"] == ["timeline", "topics", "trending", "suggested"]
        assert data["trending_searches"][0]["term"] == "ice protests"
        assert data["topic_cards"]
        assert data["periods"]
        assert data["periods"][0]["evidence"]
        assert data["periods"][0]["evidence"][0]["video"]["youtube_id"] == "explore1"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_archive_routes.py::TestArchiveRoutes::test_archive_intelligence_route_returns_explore_contract -q
```

Expected: FAIL with 404 for `/archive/intelligence` or missing schema/function imports.

- [ ] **Step 3: Add Pydantic schemas**

In `app/schemas.py`, change line 206 default:

```python
class ArchiveSummary(BaseModel):
    creator_name: str = Field("HasAnAra", description="Archive display name")
```

Then add these models after `ArchiveTimelineResponse`:

```python
class ArchiveEvidenceMoment(BaseModel):
    video: "VideoInfo" = Field(..., description="VOD containing the cited evidence")
    start_ms: int = Field(..., description="Moment start timestamp")
    end_ms: int = Field(..., description="Moment end timestamp")
    snippet: str = Field(..., description="Evidence snippet from transcript text")
    topic: Optional[str] = Field(None, description="Topic or query this evidence supports")


class ArchiveTopicCard(BaseModel):
    slug: str = Field(..., description="Stable topic slug")
    label: str = Field(..., description="Public topic label")
    source: str = Field(..., description="curated, automatic, or hybrid")
    aliases: List[str] = Field(default_factory=list, description="Search aliases used for this topic")
    total_moments: int = Field(0, description="Matched transcript moments")
    total_videos: int = Field(0, description="VODs with at least one matched moment")
    recent_mentions_90d: int = Field(0, description="Mentions in the last 90 days")
    trend_score: float = Field(0, description="Combined search and transcript trend score")
    related_topics: List[str] = Field(default_factory=list, description="Related topic labels")
    evidence: List[ArchiveEvidenceMoment] = Field(default_factory=list, description="Timestamped evidence moments")


class ArchiveTrendingSearch(BaseModel):
    term: str = Field(..., description="Trending or popular public search term")
    frequency: int = Field(0, description="Search frequency from suggestion analytics")
    trend_score: float = Field(0, description="Combined search and transcript trend score")
    source: str = Field("search", description="search, transcript, or hybrid")


class ArchivePeriodIntelligence(BaseModel):
    period: str = Field(..., description="Period identifier, e.g. 2026-05")
    label: str = Field(..., description="Human-readable period label")
    video_count: int = Field(..., description="VOD count in this period")
    total_duration_seconds: int = Field(..., description="Total VOD duration in this period")
    videos: List["VideoInfo"] = Field(default_factory=list, description="Representative VODs")
    top_topics: List[ArchiveTopicCard] = Field(default_factory=list, description="Top topics for the period")
    summary: str = Field(..., description="Extractive or generated period summary")
    evidence: List[ArchiveEvidenceMoment] = Field(default_factory=list, description="Citations supporting the summary")


class ArchiveIntelligenceResponse(BaseModel):
    summary: ArchiveSummary = Field(..., description="Archive summary stats and recent VODs")
    exploration_modes: List[str] = Field(default_factory=list, description="Available exploration modes")
    trending_searches: List[ArchiveTrendingSearch] = Field(default_factory=list, description="Trending public searches")
    suggested_searches: List[ArchiveTrendingSearch] = Field(default_factory=list, description="Suggested archive searches")
    topic_cards: List[ArchiveTopicCard] = Field(default_factory=list, description="Hybrid curated/automatic topic cards")
    periods: List[ArchivePeriodIntelligence] = Field(default_factory=list, description="Timeline periods enriched with topic/evidence data")
    query_time_ms: Optional[int] = Field(None, description="Time taken to compose archive intelligence")
```

- [ ] **Step 4: Run schema import check**

Run:

```bash
python -m compileall app/schemas.py
```

Expected: PASS.

---

### Task 2: Backend intelligence composer and route

**Files:**
- Create: `app/archive/intelligence.py`
- Modify: `app/routes/archive.py:1-36`
- Test: `tests/test_archive_routes.py`

- [ ] **Step 1: Create the composer**

Create `app/archive/intelligence.py` with:

```python
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text

from .. import crud
from ..schemas import (
    ArchiveEvidenceMoment,
    ArchiveIntelligenceResponse,
    ArchivePeriodIntelligence,
    ArchiveTimelineResponse,
    ArchiveTopicCard,
    ArchiveTrendingSearch,
    VideoInfo,
)
from .repository import archive_repository


@dataclass(frozen=True)
class SeedTopic:
    slug: str
    label: str
    aliases: tuple[str, ...]


SEED_TOPICS: tuple[SeedTopic, ...] = (
    SeedTopic("ice", "ICE", ("ice", "immigration", "deportation")),
    SeedTopic("gaza", "Gaza", ("gaza", "palestine", "israel")),
    SeedTopic("trump", "Trump", ("trump", "maga", "republicans")),
    SeedTopic("dsa", "DSA", ("dsa", "zohran", "socialists")),
    SeedTopic("epstein", "Epstein", ("epstein", "maxwell", "files")),
    SeedTopic("new-jersey", "New Jersey", ("new jersey", "newark", "delaney")),
)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "topic"


def _video_from_row(row) -> VideoInfo:
    return VideoInfo(
        id=row.video_id,
        youtube_id=row.youtube_id,
        title=row.title,
        duration_seconds=row.duration_seconds,
        state=row.state,
        caption_ingest_state=row.caption_ingest_state,
        diarization_state=row.diarization_state,
        uploaded_at=row.uploaded_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        channel_name=row.channel_name,
        language=row.language,
        category=row.category,
        has_whisper_transcript=bool(row.has_whisper_transcript),
        has_youtube_transcript=bool(row.has_youtube_transcript),
    )


def _popular_searches(db, limit: int) -> list[ArchiveTrendingSearch]:
    rows = db.execute(
        text(
            """
            SELECT term, frequency
            FROM search_suggestions
            ORDER BY frequency DESC, last_used DESC NULLS LAST, term ASC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).fetchall()
    return [
        ArchiveTrendingSearch(term=row.term, frequency=row.frequency or 0, trend_score=float(row.frequency or 0), source="search")
        for row in rows
    ]


def _evidence_for_query(db, query: str, limit: int = 2) -> list[ArchiveEvidenceMoment]:
    rows = db.execute(
        text(
            """
            SELECT
                v.id AS video_id, v.youtube_id, v.title, v.duration_seconds, v.state,
                v.caption_ingest_state, v.diarization_state, v.uploaded_at, v.created_at,
                v.updated_at, v.channel_name, v.language, v.category,
                EXISTS (SELECT 1 FROM segments s2 WHERE s2.video_id = v.id) AS has_whisper_transcript,
                EXISTS (SELECT 1 FROM youtube_transcript_segments y2 WHERE y2.video_id = v.id) AS has_youtube_transcript,
                s.start_ms, s.end_ms, s.text AS snippet
            FROM segments s
            JOIN videos v ON v.id = s.video_id
            WHERE s.text ILIKE :pattern
            ORDER BY COALESCE(v.uploaded_at, v.created_at) DESC NULLS LAST, s.start_ms ASC
            LIMIT :limit
            """
        ),
        {"pattern": f"%{query}%", "limit": limit},
    ).fetchall()
    return [
        ArchiveEvidenceMoment(
            video=_video_from_row(row),
            start_ms=row.start_ms,
            end_ms=row.end_ms,
            snippet=row.snippet,
            topic=query,
        )
        for row in rows
    ]


def _topic_card(db, seed: SeedTopic) -> ArchiveTopicCard:
    evidence: list[ArchiveEvidenceMoment] = []
    best_count = 0
    best_videos = 0
    for alias in seed.aliases:
        moments = _evidence_for_query(db, alias, limit=2)
        if moments and not evidence:
            evidence = moments
        counts = db.execute(
            text(
                """
                SELECT COUNT(*) AS total_moments, COUNT(DISTINCT video_id) AS total_videos
                FROM segments
                WHERE text ILIKE :pattern
                """
            ),
            {"pattern": f"%{alias}%"},
        ).one()
        best_count = max(best_count, counts.total_moments or 0)
        best_videos = max(best_videos, counts.total_videos or 0)
    return ArchiveTopicCard(
        slug=seed.slug,
        label=seed.label,
        source="hybrid",
        aliases=list(seed.aliases),
        total_moments=best_count,
        total_videos=best_videos,
        recent_mentions_90d=0,
        trend_score=float(best_count),
        related_topics=[],
        evidence=evidence,
    )


def _automatic_topics(popular: Iterable[ArchiveTrendingSearch], existing_slugs: set[str]) -> list[ArchiveTopicCard]:
    cards: list[ArchiveTopicCard] = []
    for item in popular:
        slug = _slugify(item.term)
        if slug in existing_slugs:
            continue
        cards.append(
            ArchiveTopicCard(
                slug=slug,
                label=item.term,
                source="automatic",
                aliases=[item.term],
                total_moments=0,
                total_videos=0,
                recent_mentions_90d=0,
                trend_score=item.trend_score,
                related_topics=[],
                evidence=[],
            )
        )
    return cards


def _periods(timeline: ArchiveTimelineResponse, topic_cards: list[ArchiveTopicCard]) -> list[ArchivePeriodIntelligence]:
    periods: list[ArchivePeriodIntelligence] = []
    for bucket in timeline.buckets:
        evidence = [moment for topic in topic_cards for moment in topic.evidence[:1]][:3]
        top_topics = [topic for topic in topic_cards if topic.total_moments > 0][:3]
        summary = f"{bucket.label} contains {bucket.video_count} archived VODs and {len(top_topics)} highlighted topics."
        periods.append(
            ArchivePeriodIntelligence(
                period=bucket.period,
                label=bucket.label,
                video_count=bucket.video_count,
                total_duration_seconds=bucket.total_duration_seconds,
                videos=bucket.videos[:3],
                top_topics=top_topics,
                summary=summary,
                evidence=evidence,
            )
        )
    return periods


def get_archive_intelligence(db, *, topic_limit: int = 8, period_limit: int = 8) -> ArchiveIntelligenceResponse:
    started = time.perf_counter()
    summary = archive_repository.get_summary(db, recent_limit=6, popular_limit=8)
    timeline = crud.get_archive_timeline(db, limit=max(period_limit * 3, 12), granularity="month")
    timeline.buckets = timeline.buckets[:period_limit]
    trending = _popular_searches(db, limit=8)
    curated = [_topic_card(db, seed) for seed in SEED_TOPICS]
    automatic = _automatic_topics(trending, {topic.slug for topic in curated})
    topic_cards = sorted(curated + automatic, key=lambda topic: topic.trend_score, reverse=True)[:topic_limit]
    return ArchiveIntelligenceResponse(
        summary=summary,
        exploration_modes=["timeline", "topics", "trending", "suggested"],
        trending_searches=trending,
        suggested_searches=trending[:6],
        topic_cards=topic_cards,
        periods=_periods(timeline, topic_cards),
        query_time_ms=int((time.perf_counter() - started) * 1000),
    )
```

- [ ] **Step 2: Wire the route**

Modify imports in `app/routes/archive.py`:

```python
from ..archive.intelligence import get_archive_intelligence
from ..schemas import ArchiveIntelligenceResponse, ArchiveSummary, ArchiveTimelineResponse
```

Add after `archive_timeline`:

```python
@router.get(
    "/archive/intelligence",
    response_model=ArchiveIntelligenceResponse,
    summary="Get archive intelligence",
    description="Unified Archive Intelligence data for /explore: summary, topic cards, trending searches, suggested searches, and enriched timeline periods.",
)
def archive_intelligence(
    topic_limit: int = Query(8, ge=1, le=20, description="Maximum topic cards to include"),
    period_limit: int = Query(8, ge=1, le=24, description="Maximum timeline periods to include"),
    db=Depends(get_db),
):
    return get_archive_intelligence(db, topic_limit=topic_limit, period_limit=period_limit)
```

- [ ] **Step 3: Run backend test**

Run:

```bash
pytest tests/test_archive_routes.py::TestArchiveRoutes::test_archive_intelligence_route_returns_explore_contract -q
```

Expected: PASS.

- [ ] **Step 4: Run related backend tests**

Run:

```bash
pytest tests/test_archive_routes.py tests/test_archive_summary_repository.py -q
```

Expected: PASS.

---

### Task 3: Frontend API types and service

**Files:**
- Modify: `frontend/src/types/api.ts:49-76`
- Modify: `frontend/src/services/api.ts:1-123`
- Modify: `frontend/src/tests/api.test.ts`

- [ ] **Step 1: Add failing API service test**

Add this block inside `describe('api service', () => { ... })` in `frontend/src/tests/api.test.ts`:

```ts
  describe('getExploreIntelligence', () => {
    it('calls archive intelligence endpoint', async () => {
      const mockResponse = {
        summary: {
          creator_name: 'HasAnAra',
          video_count: 1,
          total_duration_seconds: 3600,
          transcript_word_count: 200,
          recent_videos: [],
          popular_searches: [],
        },
        exploration_modes: ['timeline', 'topics', 'trending', 'suggested'],
        trending_searches: [],
        suggested_searches: [],
        topic_cards: [],
        periods: [],
      }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      const result = await api.getExploreIntelligence()

      expect(result).toEqual(mockResponse)
      expect(getMock).toHaveBeenCalledWith('archive/intelligence')
    })
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix frontend test -- --run src/tests/api.test.ts
```

Expected: FAIL because `api.getExploreIntelligence` is not defined.

- [ ] **Step 3: Add frontend types**

Add after `ArchiveSummary` in `frontend/src/types/api.ts`:

```ts
export interface ArchiveEvidenceMoment {
  video: VideoInfo;
  start_ms: number;
  end_ms: number;
  snippet: string;
  topic?: string | null;
}

export interface ArchiveTopicCard {
  slug: string;
  label: string;
  source: 'curated' | 'automatic' | 'hybrid' | string;
  aliases: string[];
  total_moments: number;
  total_videos: number;
  recent_mentions_90d: number;
  trend_score: number;
  related_topics: string[];
  evidence: ArchiveEvidenceMoment[];
}

export interface ArchiveTrendingSearch {
  term: string;
  frequency: number;
  trend_score: number;
  source: 'search' | 'transcript' | 'hybrid' | string;
}

export interface ArchivePeriodIntelligence {
  period: string;
  label: string;
  video_count: number;
  total_duration_seconds: number;
  videos: VideoInfo[];
  top_topics: ArchiveTopicCard[];
  summary: string;
  evidence: ArchiveEvidenceMoment[];
}

export interface ExploreIntelligenceResponse {
  summary: ArchiveSummary;
  exploration_modes: string[];
  trending_searches: ArchiveTrendingSearch[];
  suggested_searches: ArchiveTrendingSearch[];
  topic_cards: ArchiveTopicCard[];
  periods: ArchivePeriodIntelligence[];
  query_time_ms?: number | null;
}
```

- [ ] **Step 4: Add service method**

Import the new type in `frontend/src/services/api.ts`:

```ts
  ExploreIntelligenceResponse,
```

Add inside `export const api = {` after `getTimeline()`:

```ts
  async getExploreIntelligence() {
    return http.get('archive/intelligence').json<ExploreIntelligenceResponse>();
  },
```

- [ ] **Step 5: Run frontend API test**

Run:

```bash
npm --prefix frontend test -- --run src/tests/api.test.ts
```

Expected: PASS.

---

### Task 4: Explore page UI and route

**Files:**
- Create: `frontend/src/routes/ExplorePage.tsx`
- Modify: `frontend/src/main.tsx:1-31`
- Modify: `frontend/src/routes/AppLayout.tsx:5-10`
- Create: `frontend/src/tests/ExplorePage.test.tsx`

- [ ] **Step 1: Add failing page test**

Create `frontend/src/tests/ExplorePage.test.tsx`:

```tsx
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ExplorePage from '../routes/ExplorePage'
import { api } from '../services'

describe('ExplorePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders archive intelligence sections and evidence links', async () => {
    vi.spyOn(api, 'getExploreIntelligence').mockResolvedValue({
      summary: {
        creator_name: 'HasAnAra',
        video_count: 12,
        total_duration_seconds: 7200,
        transcript_word_count: 50000,
        recent_videos: [],
        popular_searches: [],
      },
      exploration_modes: ['timeline', 'topics', 'trending', 'suggested'],
      trending_searches: [{ term: 'ice protests', frequency: 7, trend_score: 7, source: 'hybrid' }],
      suggested_searches: [{ term: 'gaza', frequency: 5, trend_score: 5, source: 'search' }],
      topic_cards: [
        {
          slug: 'ice',
          label: 'ICE',
          source: 'hybrid',
          aliases: ['ice'],
          total_moments: 14,
          total_videos: 3,
          recent_mentions_90d: 2,
          trend_score: 14,
          related_topics: [],
          evidence: [],
        },
      ],
      periods: [
        {
          period: '2026-05',
          label: 'May 2026',
          video_count: 2,
          total_duration_seconds: 5400,
          videos: [],
          top_topics: [],
          summary: 'May 2026 contains 2 archived VODs and 1 highlighted topic.',
          evidence: [
            {
              video: { id: 'video-1', youtube_id: 'abc123', title: 'Evidence VOD' },
              start_ms: 1171000,
              end_ms: 1175000,
              snippet: 'ICE protests were discussed.',
              topic: 'ice',
            },
          ],
        },
      ],
    })

    render(
      <MemoryRouter initialEntries={['/explore']}>
        <ExplorePage />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Archive Intelligence' })).toBeInTheDocument()
    })
    expect(screen.getByText('ice protests')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'ICE' })).toHaveAttribute('href', '/topics/ICE')
    expect(screen.getByText('May 2026 contains 2 archived VODs and 1 highlighted topic.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open cited moment/i })).toHaveAttribute('href', '/v/video-1?t=1171#seg-1172')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix frontend test -- --run src/tests/ExplorePage.test.tsx
```

Expected: FAIL because `ExplorePage` does not exist.

- [ ] **Step 3: Implement ExplorePage**

Create `frontend/src/routes/ExplorePage.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services';
import type { ArchiveEvidenceMoment, ExploreIntelligenceResponse } from '../types/api';
import { formatDuration, formatNumber, formatTimestamp } from '../features/archive/format';

function topicHref(label: string) {
  return `/topics/${encodeURIComponent(label)}`;
}

function evidenceHref(moment: ArchiveEvidenceMoment) {
  const seconds = Math.max(0, Math.floor(moment.start_ms / 1000));
  return `/v/${moment.video.id}?t=${seconds}#seg-${seconds + 1}`;
}

export default function ExplorePage() {
  const [data, setData] = useState<ExploreIntelligenceResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getExploreIntelligence()
      .then(setData)
      .catch((err: unknown) => {
        console.error('Failed to load archive intelligence', err);
        setData(null);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="surface-card text-center text-muted">Loading archive intelligence…</div>;
  if (!data) return <div className="surface-card text-center text-muted">Archive intelligence is not available yet.</div>;

  return (
    <div className="space-y-6">
      <section className="surface-card space-y-5">
        <div className="text-xs uppercase tracking-[0.24em] text-subtle">Explore</div>
        <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr] lg:items-end">
          <div>
            <h1 className="page-title">Archive Intelligence</h1>
            <p className="mt-3 max-w-3xl text-muted">
              Follow topics, spikes, suggested searches, and cited timeline summaries across the HasAnAra VOD archive.
            </p>
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="rounded-2xl border border-border bg-surface-muted p-3">
              <div className="text-2xl font-semibold">{formatNumber(data.summary.video_count)}</div>
              <div className="text-xs uppercase tracking-wide text-subtle">VODs</div>
            </div>
            <div className="rounded-2xl border border-border bg-surface-muted p-3">
              <div className="text-2xl font-semibold">{formatDuration(data.summary.total_duration_seconds)}</div>
              <div className="text-xs uppercase tracking-wide text-subtle">Runtime</div>
            </div>
            <div className="rounded-2xl border border-border bg-surface-muted p-3">
              <div className="text-2xl font-semibold">{formatNumber(data.summary.transcript_word_count)}</div>
              <div className="text-xs uppercase tracking-wide text-subtle">Words</div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="surface-card space-y-3">
          <h2 className="section-title">Trending searches</h2>
          <div className="flex flex-wrap gap-2">
            {data.trending_searches.map((item) => (
              <Link key={item.term} to={`/search?q=${encodeURIComponent(item.term)}`} className="pill-link">
                {item.term}
              </Link>
            ))}
          </div>
        </div>
        <div className="surface-card space-y-3">
          <h2 className="section-title">Suggested explorations</h2>
          <div className="flex flex-wrap gap-2">
            {data.suggested_searches.map((item) => (
              <Link key={item.term} to={`/search?q=${encodeURIComponent(item.term)}`} className="pill-link">
                {item.term}
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="surface-card space-y-4">
        <h2 className="section-title">Topic atlas</h2>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.topic_cards.map((topic) => (
            <Link key={topic.slug} to={topicHref(topic.label)} className="rounded-2xl border border-border bg-surface-muted p-4 transition-colors hover:border-accent">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-lg font-semibold">{topic.label}</h3>
                <span className="text-xs uppercase tracking-wide text-subtle">{topic.source}</span>
              </div>
              <div className="mt-3 text-sm text-muted">{formatNumber(topic.total_moments)} moments · {formatNumber(topic.total_videos)} VODs</div>
            </Link>
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="section-title">Timeline intelligence</h2>
        {data.periods.map((period) => (
          <article key={period.period} className="surface-card space-y-4">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <div>
                <h3 className="text-xl font-semibold">{period.label}</h3>
                <p className="text-sm text-muted">{formatNumber(period.video_count)} VODs · {formatDuration(period.total_duration_seconds)}</p>
              </div>
              <Link to={`/episodes?date_from=${period.period}-01&date_to=${period.period}-31`} className="action-link text-sm">
                Browse period
              </Link>
            </div>
            <p className="text-muted">{period.summary}</p>
            {period.evidence.length > 0 && (
              <div className="grid gap-3 md:grid-cols-2">
                {period.evidence.map((moment) => (
                  <Link key={`${moment.video.id}-${moment.start_ms}`} to={evidenceHref(moment)} className="rounded-xl border border-border bg-surface-muted p-3 transition-colors hover:border-accent">
                    <div className="text-xs uppercase tracking-wide text-subtle">{formatTimestamp(moment.start_ms)} · Open cited moment</div>
                    <div className="mt-2 line-clamp-2 text-sm text-ink">{moment.snippet}</div>
                    <div className="mt-2 line-clamp-1 text-xs text-muted">{moment.video.title || 'Untitled VOD'}</div>
                  </Link>
                ))}
              </div>
            )}
          </article>
        ))}
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Register route and nav**

In `frontend/src/main.tsx`, import and register:

```tsx
import ExplorePage from './routes/ExplorePage';
```

Add to children after Search:

```tsx
      { path: 'explore', element: <ExplorePage /> },
```

In `frontend/src/routes/AppLayout.tsx`, add nav item after Search:

```ts
  { to: '/explore', label: 'Explore' },
```

- [ ] **Step 5: Run page test**

Run:

```bash
npm --prefix frontend test -- --run src/tests/ExplorePage.test.tsx
```

Expected: PASS.

---

### Task 5: Integration, build, deploy, and commit

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run backend archive/search tests**

Run:

```bash
pytest tests/test_archive_routes.py tests/test_archive_summary_repository.py tests/test_routes_search.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests**

Run:

```bash
npm --prefix frontend test -- --run
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
npm --prefix frontend run build
```

Expected: PASS.

- [ ] **Step 4: Deploy frontend/backend stack if requested for live QA**

Run:

```bash
rtk docker compose -p hasanara -f docker-compose.yml -f docker-compose.gtx1080.yml -f docker-compose.hasanara.yml up -d --build backend frontend
```

Expected: backend and frontend containers recreate successfully.

- [ ] **Step 5: Live browser QA**

Run:

```bash
agent-browser --session hasanara-explore --args "--no-sandbox" open https://hasanara.subcult.tv/explore && agent-browser --session hasanara-explore --args "--no-sandbox" wait --load networkidle && agent-browser --session hasanara-explore --args "--no-sandbox" snapshot -i
```

Expected visible checks:
- Page heading `Archive Intelligence`.
- Main nav includes `Explore`.
- Trending searches render.
- Topic atlas renders.
- Timeline intelligence period cards render.
- Cited moment links navigate to `/v/<id>?t=<seconds>#seg-<n>`.

- [ ] **Step 6: Inspect git diff**

Run:

```bash
rtk git status --short --branch && rtk git diff --check && rtk git diff --stat
```

Expected: only planned files changed; no whitespace errors.

- [ ] **Step 7: Commit**

Run:

```bash
rtk git add app/schemas.py app/archive/intelligence.py app/routes/archive.py tests/test_archive_routes.py frontend/src/types/api.ts frontend/src/services/api.ts frontend/src/routes/ExplorePage.tsx frontend/src/main.tsx frontend/src/routes/AppLayout.tsx frontend/src/tests/ExplorePage.test.tsx frontend/src/tests/api.test.ts docs/superpowers/plans/2026-06-04-archive-intelligence-explore.md
rtk git commit -m "Add Archive Intelligence explore page"
```

Expected: commit succeeds.

---

## Self-Review

**Spec coverage:**
- Hybrid topics: covered by `SEED_TOPICS` plus automatic topics from `search_suggestions`, all emitted with `source`.
- AI summaries with cited evidence: the Phase 1 contract includes `summary` and `evidence` for each period; summaries are extractive strings now and can be replaced by generated summaries later without changing frontend shape.
- Trending from both user search behavior and transcript activity: Phase 1 uses search frequency and transcript mention counts in topic cards; the contract supports `search`, `transcript`, and `hybrid` sources.
- Destination `/explore`: route, nav, API service, and page test are included.

**Placeholder scan:** No task uses open-ended placeholders. Later durable topic extraction and generated summaries are explicitly out of Phase 1 and represented by the Phase 1 API contract.

**Type consistency:** Backend `ArchiveIntelligenceResponse` maps to frontend `ExploreIntelligenceResponse`; `ArchiveTopicCard`, `ArchiveTrendingSearch`, `ArchiveEvidenceMoment`, and `ArchivePeriodIntelligence` names and fields match across Python and TypeScript.
