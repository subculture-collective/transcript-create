# Robust Topic Extraction and Stream Labeling Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Recommended path:
> dispatch a fresh subagent per task, review each result with `review-quality`,
> then continue. For complex multi-agent splits, use
> `parallel-feature-development`, `team-composition-patterns`, and
> `team-communication-protocols`. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Build HasanAra’s killer feature: a citation-backed, automatically growing intelligence layer that discovers topics, people, recurring stream formats, events, chapters, segments, and VOD labels from both Whisper and YouTube transcripts.

**Architecture:** Add a new extraction/candidate layer separate from today’s public `archive_topics`, manual people, and video tags. The system should aggressively auto-publish only high-confidence labels, keep lower-confidence discoveries as internal/shadow candidates, preserve exact timestamp evidence, and support configurable extraction tiers from local/cheap to premium. Existing Explore, topic cards, named periods, and video metadata become consumers of this evidence-backed labeling layer rather than the source of truth.

**Tech Stack:** FastAPI, PostgreSQL, SQLAlchemy text queries, Alembic, Pydantic, existing transcript tables (`segments`, `youtube_segments`), optional local embeddings/Ollama or API-based LLM tiers, React/TypeScript admin and Explore UI, pytest, Vitest.

---

## Product Contract

### User-approved direction

- First robust version should **auto-publish aggressively**, but only for high-confidence outputs.
- Target architecture should support the **full hierarchy**:
  - transcript segment labels
  - stable transcript windows
  - stream chapters/time ranges
  - VOD-level labels
  - people/guest appearances
  - topic clusters and aliases
  - recurring stream formats: `chadvice`, `okbuddy`, `gaming`, `guests`, etc.
- Extraction should support **configurable quality tiers**:
  - `cheap`: deterministic + local-only extraction
  - `balanced`: local extraction plus selective LLM naming/merge decisions
  - `premium`: higher-quality LLM/embedding passes for important backfills
- Public publishing should use **high-confidence only** rules.
- Every public label should be evidence-backed with timestamped citations.

### Core principle

Do not write raw LLM output directly into public topics or public video tags. Always go through:

```text
transcript/title/search/manual source
  -> extraction run
  -> candidates
  -> canonical labels
  -> evidence-backed assignments
  -> policy decision
  -> public rollups / Explore
```

---

## Current Codebase Facts

- Existing archive intelligence lives in `app/archive/intelligence_repository.py`:
  - `seed_archive_topics()` seeds curated topics.
  - `autopublish_search_topics()` currently creates public topics from `search_suggestions`.
  - `refresh_topic_mentions()` scans Whisper `segments` and YouTube `youtube_segments` for aliases.
  - `refresh_topic_period_stats()`, `refresh_period_summaries()`, and `refresh_named_period_stats()` create derived caches.
- Public composition lives in `app/archive/intelligence.py` and `app/routes/archive.py`.
- Existing topic tables were created in `alembic/versions/20260602_1545_add_archive_intelligence_tables.py`:
  - `archive_topics`
  - `archive_topic_aliases`
  - `archive_topic_mentions`
  - `archive_topic_period_stats`
  - `archive_period_summaries`
  - `archive_search_trends`
- Transcript sources:
  - Whisper/native: `transcripts`, `segments`
  - YouTube captions: `youtube_transcripts`, `youtube_segments`
  - formatted blocks: `transcript_blocks`
- Manual video metadata exists in `app/archive/video_metadata_repository.py` and admin UI `frontend/src/routes/admin/AdminVideoMetadata.tsx`:
  - `archive_people`
  - `archive_video_people`
  - `archive_video_tags`
  - `archive_video_taggings`
- Existing `/explore` UI is `frontend/src/routes/ExplorePage.tsx`.

---

## Target Data Model

## Naming Contract

Use these terms consistently:

- `extraction_tier`: extraction cost/quality mode: `cheap`, `balanced`, `premium`.
- `publish_tier`: confidence/publication tier: `gold`, `silver`, `bronze`, `shadow`.
- Do not add new `quality_tier` columns because the term is ambiguous.

Public visibility rules:

- `gold` assignments may auto-publish when policy allows.
- `silver` assignments may auto-publish only for existing canonical labels or explicitly safe categories/series.
- `bronze` assignments are admin-review candidates.
- `shadow` assignments are stored for debugging/evaluation only.

### New tables

Create migration: `alembic/versions/20260604_2300_add_label_extraction_system.py`

#### `archive_extraction_runs`

Tracks every automatic extraction/backfill pass.

```sql
CREATE TABLE archive_extraction_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope TEXT NOT NULL,
    extraction_tier TEXT NOT NULL DEFAULT 'cheap',
    video_id UUID NULL REFERENCES videos(id) ON DELETE SET NULL,
    model_name TEXT,
    model_version TEXT,
    prompt_version TEXT,
    config_hash TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);
```

Allowed `scope`: `video`, `batch`, `period`, `backfill`.

Allowed `extraction_tier`: `cheap`, `balanced`, `premium`.

Allowed `status`: `running`, `completed`, `failed`, `cancelled`.

#### `archive_labels`

Canonical labels for topics, people, series, categories, events, games, orgs, and stream formats.

```sql
CREATE TABLE archive_labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    kind TEXT NOT NULL,
    parent_id UUID NULL REFERENCES archive_labels(id) ON DELETE SET NULL,
    canonical_id UUID NULL REFERENCES archive_labels(id) ON DELETE SET NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'candidate',
    source TEXT NOT NULL DEFAULT 'automatic',
    publish_tier TEXT NOT NULL DEFAULT 'shadow',
    confidence_score NUMERIC NOT NULL DEFAULT 0,
    created_by_run_id UUID NULL REFERENCES archive_extraction_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Allowed `kind`: `topic`, `person`, `series`, `category`, `event`, `game`, `org`, `meme`, `place`, `issue`.

Allowed `status`: `candidate`, `review`, `published`, `hidden`, `rejected`, `merged`.

Allowed `source`: `admin`, `automatic`, `hybrid`, `seed`.

Allowed `publish_tier`: `gold`, `silver`, `bronze`, `shadow`.

#### `archive_label_aliases`

Aliases with ambiguity support.

```sql
CREATE TABLE archive_label_aliases (
    id BIGSERIAL PRIMARY KEY,
    label_id UUID NOT NULL REFERENCES archive_labels(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    weight NUMERIC NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'automatic',
    status TEXT NOT NULL DEFAULT 'active',
    is_ambiguous BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(label_id, normalized_alias)
);
```

#### `archive_transcript_windows`

Stable extraction units derived from Whisper and YouTube caption segments.

```sql
CREATE TABLE archive_transcript_windows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    segment_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    text_hash TEXT NOT NULL,
    text TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    transcript_quality NUMERIC NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(video_id, source, start_ms, end_ms, text_hash)
);
```

Allowed `source`: `whisper`, `youtube`.

#### `archive_video_chapters`

Candidate or published stream chapters/time ranges.

```sql
CREATE TABLE archive_video_chapters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    chapter_index INTEGER NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    title TEXT,
    summary TEXT,
    confidence_score NUMERIC NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'candidate',
    source TEXT NOT NULL DEFAULT 'automatic',
    run_id UUID NULL REFERENCES archive_extraction_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(video_id, chapter_index)
);
```

#### `archive_label_assignments`

Evidence-backed scoped labels.

```sql
CREATE TABLE archive_label_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label_id UUID NOT NULL REFERENCES archive_labels(id) ON DELETE CASCADE,
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    unit_type TEXT NOT NULL,
    chapter_id UUID NULL REFERENCES archive_video_chapters(id) ON DELETE CASCADE,
    window_id UUID NULL REFERENCES archive_transcript_windows(id) ON DELETE CASCADE,
    segment_source TEXT,
    segment_id BIGINT,
    start_ms INTEGER,
    end_ms INTEGER,
    status TEXT NOT NULL DEFAULT 'candidate',
    publish_tier TEXT NOT NULL DEFAULT 'shadow',
    confidence_score NUMERIC NOT NULL DEFAULT 0,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    source TEXT NOT NULL DEFAULT 'automatic',
    run_id UUID NULL REFERENCES archive_extraction_runs(id) ON DELETE SET NULL,
    assignment_key TEXT NOT NULL UNIQUE,
    component_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Allowed `unit_type`: `vod`, `chapter`, `window`, `segment`.

Allowed `status`: `candidate`, `auto_published`, `admin_approved`, `rejected`, `shadow`.

Allowed `source`: `alias`, `keyphrase`, `search`, `title`, `embedding_cluster`, `llm`, `metadata`, `admin`, `hybrid`.

#### `archive_label_feedback`

Admin and system correction loop.

```sql
CREATE TABLE archive_label_feedback (
    id BIGSERIAL PRIMARY KEY,
    label_id UUID NULL REFERENCES archive_labels(id) ON DELETE SET NULL,
    assignment_id UUID NULL REFERENCES archive_label_assignments(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    old_value JSONB NOT NULL DEFAULT '{}'::jsonb,
    new_value JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason TEXT,
    user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### `archive_label_policies`

Configurable auto-publish thresholds.

```sql
CREATE TABLE archive_label_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label_kind TEXT NOT NULL,
    unit_type TEXT NOT NULL,
    extraction_tier TEXT NOT NULL DEFAULT 'balanced',
    min_publish_score NUMERIC NOT NULL DEFAULT 0.90,
    min_review_score NUMERIC NOT NULL DEFAULT 0.65,
    min_evidence_count INTEGER NOT NULL DEFAULT 2,
    min_distinct_videos INTEGER NOT NULL DEFAULT 1,
    require_existing_canonical BOOLEAN NOT NULL DEFAULT false,
    auto_publish_enabled BOOLEAN NOT NULL DEFAULT true,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(label_kind, unit_type, extraction_tier)
);
```

### Required indexes

```sql
CREATE INDEX archive_labels_kind_status_idx ON archive_labels(kind, status);
CREATE INDEX archive_labels_status_confidence_idx ON archive_labels(status, confidence_score DESC);
CREATE INDEX archive_label_aliases_normalized_idx ON archive_label_aliases(normalized_alias);
CREATE INDEX archive_transcript_windows_video_idx ON archive_transcript_windows(video_id, source, start_ms);
CREATE INDEX archive_label_assignments_video_unit_idx ON archive_label_assignments(video_id, unit_type, status);
CREATE INDEX archive_label_assignments_label_status_idx ON archive_label_assignments(label_id, status, confidence_score DESC);
CREATE INDEX archive_label_assignments_public_idx ON archive_label_assignments(status, publish_tier, unit_type, video_id);
CREATE INDEX archive_label_assignments_time_idx ON archive_label_assignments(video_id, start_ms, end_ms);
CREATE INDEX archive_video_chapters_video_idx ON archive_video_chapters(video_id, chapter_index);
CREATE INDEX archive_extraction_runs_status_idx ON archive_extraction_runs(status, started_at DESC);
```

### Rerun and rejection contract

- `archive_label_assignments.assignment_key` makes extraction idempotent across reruns.
- `ON CONFLICT (assignment_key)` updates evidence/confidence but preserves `status='rejected'`.
- `archive_labels.status='rejected'` prevents new assignments for that label unless an admin changes it back to `candidate` or `published`.
- `archive_labels.status='merged'` means public reads resolve `COALESCE(canonical_id, id)` and never display the merged row as its own card.
- Alias collisions are allowed as data, but aliases with multiple active label matches must be marked `is_ambiguous=true` and cannot auto-publish new public labels.

---

## Confidence Rules

### Quality tiers

```text
gold   >= 0.90: auto-publish if policy allows
silver >= 0.75: auto-publish only for existing canonical labels or safe categories
bronze >= 0.60: store as review candidate
shadow <  0.60: store for debugging/evaluation only
```

### Score components

```text
final_score =
  0.25 evidence_strength
+ 0.20 distinct_video_support
+ 0.15 transcript_quality
+ 0.15 recurrence_or_duration_coverage
+ 0.10 title_or_metadata_boost
+ 0.10 cluster_cohesion
+ 0.05 admin_or_seed_prior
- penalties
```

### Penalties

- generic label: `news`, `politics`, `react`, `stream`
- single fleeting mention
- ambiguous alias: short names, acronyms, terms with multiple meanings
- low transcript quality
- no timestamp evidence
- label appears only in title but not transcript
- possible person-present vs person-mentioned confusion

---

## Task 1: Label Extraction Schema Foundation

**Files:**
- Create: `alembic/versions/20260604_2300_add_label_extraction_system.py`
- Create: `app/archive/labeling/__init__.py`
- Create: `app/archive/labeling/types.py`
- Test: `tests/test_labeling_schema.py`

- [ ] **Step 1: Write failing schema smoke tests**

Create `tests/test_labeling_schema.py`:

```python
from sqlalchemy import text


def test_labeling_tables_exist(db_session):
    expected = {
        "archive_extraction_runs",
        "archive_labels",
        "archive_label_aliases",
        "archive_transcript_windows",
        "archive_video_chapters",
        "archive_label_assignments",
        "archive_label_feedback",
        "archive_label_policies",
    }
    rows = db_session.execute(
        text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = ANY(:tables)
        """),
        {"tables": list(expected)},
    ).all()
    assert {row[0] for row in rows} == expected


def test_default_labeling_policies_seeded(db_session):
    rows = db_session.execute(
        text("""
        SELECT label_kind, unit_type, extraction_tier, min_publish_score, min_review_score
        FROM archive_label_policies
        ORDER BY label_kind, unit_type, extraction_tier
        """)
    ).mappings().all()
    assert {row["extraction_tier"] for row in rows} >= {"cheap", "balanced", "premium"}
    assert any(row["label_kind"] == "topic" and row["unit_type"] == "window" for row in rows)
    assert all(float(row["min_publish_score"]) >= float(row["min_review_score"]) for row in rows)
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
uv run --no-project --with fastapi --with sqlalchemy --with psycopg --with psycopg-binary --with pytest --with alembic --with pydantic --with pydantic-settings python -m pytest tests/test_labeling_schema.py -q
```

Expected: fails because tables do not exist.

- [ ] **Step 3: Add migration**

Create `alembic/versions/20260604_2300_add_label_extraction_system.py` using the SQL contracts above. Set:

```python
revision = "20260604_2300_label_extraction"
down_revision = "20260604_2100_recurring_periods"
```

Seed policies in `upgrade()`:

```sql
INSERT INTO archive_label_policies
  (label_kind, unit_type, extraction_tier, min_publish_score, min_review_score, min_evidence_count, min_distinct_videos, require_existing_canonical, auto_publish_enabled, config)
VALUES
  ('topic', 'window', 'cheap', 0.92, 0.65, 2, 1, false, true, '{"extractors":["alias","keyphrase"]}'::jsonb),
  ('topic', 'vod', 'cheap', 0.94, 0.70, 3, 1, false, true, '{"min_duration_share":0.05}'::jsonb),
  ('person', 'window', 'cheap', 0.95, 0.75, 2, 1, true, true, '{"person_presence_requires_seed":true}'::jsonb),
  ('series', 'vod', 'cheap', 0.90, 0.70, 2, 2, false, true, '{"series_requires_cross_video":true}'::jsonb),
  ('category', 'vod', 'cheap', 0.88, 0.65, 2, 1, false, true, '{"allowed_auto_categories":["gaming","chadvice","okbuddy","guests"]}'::jsonb),
  ('topic', 'window', 'balanced', 0.90, 0.62, 2, 1, false, true, '{"extractors":["alias","keyphrase","llm"]}'::jsonb),
  ('topic', 'vod', 'balanced', 0.92, 0.68, 3, 1, false, true, '{"min_duration_share":0.04}'::jsonb),
  ('topic', 'window', 'premium', 0.88, 0.60, 2, 1, false, true, '{"extractors":["alias","keyphrase","llm","embedding_cluster"]}'::jsonb);
```

- [ ] **Step 4: Add Python constants/types**

Create `app/archive/labeling/types.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

LabelKind = Literal["topic", "person", "series", "category", "event", "game", "org", "meme", "place", "issue"]
UnitType = Literal["vod", "chapter", "window", "segment"]
QualityTier = Literal["cheap", "balanced", "premium"]
PublishTier = Literal["gold", "silver", "bronze", "shadow"]


@dataclass(frozen=True)
class CandidateSignal:
    source: str
    label: str
    alias: str
    score: float
    evidence: dict


@dataclass(frozen=True)
class LabelCandidate:
    label: str
    kind: str
    aliases: tuple[str, ...]
    confidence_score: float
    component_scores: dict[str, float] = field(default_factory=dict)
    evidence: tuple[dict, ...] = ()
```

- [ ] **Step 5: Run tests**

Expected: schema tests pass.

- [ ] **Step 6: Commit**

```bash
rtk git add alembic/versions/20260604_2300_add_label_extraction_system.py app/archive/labeling tests/test_labeling_schema.py
rtk git commit -m "Add label extraction schema"
```

---

## Task 2: Transcript Window Builder

**Files:**
- Create: `app/archive/labeling/windows.py`
- Create: `tests/test_labeling_windows.py`

- [ ] **Step 1: Write windowing tests**

Create tests for stable 120-second windows over both transcript sources:

```python
def test_build_windows_merges_segments_into_stable_windows():
    from app.archive.labeling.windows import build_windows_from_segments

    segments = [
        {"id": 1, "start_ms": 0, "end_ms": 30_000, "text": "hello world"},
        {"id": 2, "start_ms": 30_000, "end_ms": 90_000, "text": "gaza discussion"},
        {"id": 3, "start_ms": 125_000, "end_ms": 150_000, "text": "new window"},
    ]
    windows = build_windows_from_segments(segments, source="whisper", window_ms=120_000)
    assert len(windows) == 2
    assert windows[0].start_ms == 0
    assert windows[0].end_ms == 90_000
    assert windows[0].segment_ids == [1, 2]
    assert "gaza discussion" in windows[0].text
    assert windows[0].text_hash


def test_window_hash_is_stable_for_same_text_and_bounds():
    from app.archive.labeling.windows import build_windows_from_segments

    segments = [{"id": 1, "start_ms": 0, "end_ms": 1000, "text": "same text"}]
    first = build_windows_from_segments(segments, source="youtube", window_ms=120_000)[0]
    second = build_windows_from_segments(segments, source="youtube", window_ms=120_000)[0]
    assert first.text_hash == second.text_hash
```

- [ ] **Step 2: Implement window builder**

Create `app/archive/labeling/windows.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptWindow:
    source: str
    start_ms: int
    end_ms: int
    segment_ids: list[int]
    text: str
    token_count: int
    text_hash: str


def _hash_window(source: str, start_ms: int, end_ms: int, text: str) -> str:
    payload = f"{source}:{start_ms}:{end_ms}:{' '.join(text.split())}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_windows_from_segments(segments: list[dict], source: str, window_ms: int = 120_000) -> list[TranscriptWindow]:
    ordered = sorted(
        [segment for segment in segments if (segment.get("text") or "").strip()],
        key=lambda segment: int(segment.get("start_ms") or 0),
    )
    windows: list[TranscriptWindow] = []
    current: list[dict] = []
    current_start: int | None = None

    def flush():
        nonlocal current, current_start
        if not current or current_start is None:
            return
        text = " ".join(str(segment.get("text") or "").strip() for segment in current if str(segment.get("text") or "").strip())
        end_ms = max(int(segment.get("end_ms") or segment.get("start_ms") or current_start) for segment in current)
        segment_ids = [int(segment["id"]) for segment in current if segment.get("id") is not None]
        windows.append(
            TranscriptWindow(
                source=source,
                start_ms=current_start,
                end_ms=end_ms,
                segment_ids=segment_ids,
                text=text,
                token_count=len(text.split()),
                text_hash=_hash_window(source, current_start, end_ms, text),
            )
        )
        current = []
        current_start = None

    for segment in ordered:
        start_ms = int(segment.get("start_ms") or 0)
        if current_start is None:
            current_start = start_ms
        if start_ms - current_start >= window_ms:
            flush()
            current_start = start_ms
        current.append(segment)
    flush()
    return windows
```

- [ ] **Step 3: Add persistence helpers**

Extend `windows.py`:

```python
from sqlalchemy import text


def load_source_segments(db, video_id: str, source: str) -> list[dict]:
    if source == "whisper":
        return list(db.execute(text("""
            SELECT id, start_ms, end_ms, text
            FROM segments
            WHERE video_id = :video_id
            ORDER BY start_ms ASC
        """), {"video_id": video_id}).mappings().all())
    if source == "youtube":
        return list(db.execute(text("""
            SELECT ys.id, ys.start_ms, ys.end_ms, ys.text
            FROM youtube_segments ys
            JOIN youtube_transcripts yt ON yt.id = ys.youtube_transcript_id
            WHERE yt.video_id = :video_id
            ORDER BY ys.start_ms ASC
        """), {"video_id": video_id}).mappings().all())
    raise ValueError(f"Unsupported transcript source: {source}")


def persist_windows(db, video_id: str, windows: list[TranscriptWindow]) -> int:
    if not windows:
        return 0
    rows = [
        {
            "video_id": video_id,
            "source": window.source,
            "start_ms": window.start_ms,
            "end_ms": window.end_ms,
            "segment_ids": window.segment_ids,
            "text_hash": window.text_hash,
            "text": window.text,
            "token_count": window.token_count,
        }
        for window in windows
    ]
    db.execute(text("""
        INSERT INTO archive_transcript_windows (
            video_id, source, start_ms, end_ms, segment_ids, text_hash, text, token_count, transcript_quality, created_at
        ) VALUES (
            :video_id, :source, :start_ms, :end_ms, CAST(:segment_ids AS jsonb), :text_hash, :text, :token_count, 1, now()
        )
        ON CONFLICT (video_id, source, start_ms, end_ms, text_hash) DO UPDATE SET
            text = EXCLUDED.text,
            token_count = EXCLUDED.token_count,
            segment_ids = EXCLUDED.segment_ids
    """), [{**row, "segment_ids": __import__("json").dumps(row["segment_ids"])} for row in rows])
    return len(rows)
```

- [ ] **Step 4: Run tests and commit**

```bash
uv run --no-project --with pytest --with sqlalchemy python -m pytest tests/test_labeling_windows.py -q
rtk git add app/archive/labeling/windows.py tests/test_labeling_windows.py
rtk git commit -m "Add transcript window builder"
```

---

## Task 3: Candidate Extractors

**Files:**
- Create: `app/archive/labeling/extractors.py`
- Create: `app/archive/labeling/normalization.py`
- Create: `tests/test_labeling_extractors.py`

- [ ] **Step 1: Add tests for deterministic candidates**

```python
def test_keyphrase_extractor_discovers_repeated_domain_phrases():
    from app.archive.labeling.extractors import extract_keyphrase_candidates

    windows = [
        {"id": "w1", "video_id": "v1", "text": "okbuddy segment starts and okbuddy is funny", "start_ms": 0, "end_ms": 60000},
        {"id": "w2", "video_id": "v2", "text": "people keep saying okbuddy during this stream", "start_ms": 0, "end_ms": 60000},
        {"id": "w3", "video_id": "v3", "text": "chadvice call segment and chadvice question", "start_ms": 0, "end_ms": 60000},
    ]
    candidates = extract_keyphrase_candidates(windows, min_distinct_videos=2, min_occurrences=2)
    labels = {candidate.label for candidate in candidates}
    assert "okbuddy" in labels
    assert "chadvice" not in labels


def test_alias_extractor_uses_existing_aliases_with_evidence():
    from app.archive.labeling.extractors import extract_alias_candidates

    windows = [{"id": "w1", "video_id": "v1", "text": "Trump and Gaza were discussed", "start_ms": 1000, "end_ms": 5000}]
    aliases = [{"label_id": "topic-gaza", "label": "Gaza", "alias": "gaza", "kind": "topic"}]
    candidates = extract_alias_candidates(windows, aliases)
    assert candidates[0].label == "Gaza"
    assert candidates[0].evidence[0]["window_id"] == "w1"
```

- [ ] **Step 2: Implement normalization**

Create `app/archive/labeling/normalization.py`:

```python
from __future__ import annotations

import re

STOP_TERMS = {
    "hasan", "hasanabi", "stream", "vod", "youtube", "twitch", "chat", "people", "like", "yeah", "okay",
}


def normalize_label(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    return value[:1].upper() + value[1:] if value else value


def normalized_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def slugify_label(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "label"


def is_junk_phrase(value: str) -> bool:
    normalized = normalized_alias(value)
    if not normalized or normalized in STOP_TERMS:
        return True
    if len(normalized) < 3:
        return True
    if normalized.isdigit():
        return True
    return False
```

- [ ] **Step 3: Implement extractors**

Create `app/archive/labeling/extractors.py`:

```python
from __future__ import annotations

from collections import Counter, defaultdict
from app.archive.labeling.normalization import is_junk_phrase, normalize_label, normalized_alias
from app.archive.labeling.types import LabelCandidate
from app.archive.intelligence_repository import alias_matches_text


def _ngrams(text: str, max_words: int = 3) -> list[str]:
    words = [word for word in normalized_alias(text).split() if word]
    phrases: list[str] = []
    for size in range(1, max_words + 1):
        for idx in range(0, max(0, len(words) - size + 1)):
            phrase = " ".join(words[idx: idx + size])
            if not is_junk_phrase(phrase):
                phrases.append(phrase)
    return phrases


def extract_keyphrase_candidates(windows: list[dict], min_distinct_videos: int = 3, min_occurrences: int = 5) -> list[LabelCandidate]:
    counts = Counter()
    videos_by_phrase: dict[str, set[str]] = defaultdict(set)
    evidence_by_phrase: dict[str, list[dict]] = defaultdict(list)
    for window in windows:
        video_id = str(window.get("video_id"))
        for phrase in _ngrams(str(window.get("text") or ""), max_words=3):
            counts[phrase] += 1
            videos_by_phrase[phrase].add(video_id)
            if len(evidence_by_phrase[phrase]) < 5:
                evidence_by_phrase[phrase].append({
                    "window_id": str(window.get("id")),
                    "video_id": video_id,
                    "start_ms": int(window.get("start_ms") or 0),
                    "end_ms": int(window.get("end_ms") or 0),
                    "snippet": str(window.get("text") or "")[:300],
                })
    candidates: list[LabelCandidate] = []
    for phrase, count in counts.items():
        distinct_videos = len(videos_by_phrase[phrase])
        if count < min_occurrences or distinct_videos < min_distinct_videos:
            continue
        confidence = min(0.95, 0.35 + (0.08 * distinct_videos) + (0.02 * count))
        candidates.append(LabelCandidate(
            label=normalize_label(phrase),
            kind="topic",
            aliases=(phrase,),
            confidence_score=confidence,
            component_scores={"occurrences": float(count), "distinct_videos": float(distinct_videos)},
            evidence=tuple(evidence_by_phrase[phrase]),
        ))
    return sorted(candidates, key=lambda candidate: candidate.confidence_score, reverse=True)


def extract_alias_candidates(windows: list[dict], aliases: list[dict]) -> list[LabelCandidate]:
    evidence_by_label: dict[str, list[dict]] = defaultdict(list)
    alias_by_label: dict[str, set[str]] = defaultdict(set)
    label_meta: dict[str, dict] = {}
    for alias in aliases:
        label_id = str(alias["label_id"])
        label_meta[label_id] = alias
        alias_by_label[label_id].add(str(alias["alias"]).lower())
    for window in windows:
        text = str(window.get("text") or "")
        lowered = text.lower()
        for label_id, terms in alias_by_label.items():
            if any(alias_matches_text(term, lowered) for term in terms):
                if len(evidence_by_label[label_id]) < 10:
                    evidence_by_label[label_id].append({
                        "window_id": str(window.get("id")),
                        "video_id": str(window.get("video_id")),
                        "start_ms": int(window.get("start_ms") or 0),
                        "end_ms": int(window.get("end_ms") or 0),
                        "snippet": text[:300],
                    })
    return [
        LabelCandidate(
            label=str(label_meta[label_id]["label"]),
            kind=str(label_meta[label_id].get("kind") or "topic"),
            aliases=tuple(sorted(alias_by_label[label_id])),
            confidence_score=min(0.98, 0.60 + 0.05 * len(evidence)),
            component_scores={"evidence_count": float(len(evidence))},
            evidence=tuple(evidence),
        )
        for label_id, evidence in evidence_by_label.items()
    ]
```

- [ ] **Step 4: Run tests and commit**

```bash
uv run --no-project --with pytest python -m pytest tests/test_labeling_extractors.py -q
rtk git add app/archive/labeling/extractors.py app/archive/labeling/normalization.py tests/test_labeling_extractors.py
rtk git commit -m "Add deterministic label candidate extractors"
```

---

## Task 4: Label Repository and Auto-Publish Policy

**Files:**
- Create: `app/archive/labeling/repository.py`
- Create: `app/archive/labeling/policy.py`
- Create: `tests/test_labeling_repository.py`
- Create: `tests/test_labeling_policy.py`

- [ ] **Step 1: Write policy tests**

```python
def test_policy_auto_publishes_gold_with_enough_evidence():
    from app.archive.labeling.policy import classify_candidate
    candidate = {
        "kind": "topic",
        "unit_type": "window",
        "confidence_score": 0.93,
        "evidence_count": 3,
        "distinct_videos": 2,
    }
    policy = {
        "min_publish_score": 0.90,
        "min_review_score": 0.65,
        "min_evidence_count": 2,
        "min_distinct_videos": 1,
        "require_existing_canonical": False,
        "auto_publish_enabled": True,
    }
    assert classify_candidate(candidate, policy, existing_canonical=False) == ("gold", "auto_published")


def test_policy_sends_weak_candidate_to_shadow():
    from app.archive.labeling.policy import classify_candidate
    candidate = {"kind": "topic", "unit_type": "window", "confidence_score": 0.40, "evidence_count": 1, "distinct_videos": 1}
    policy = {"min_publish_score": 0.90, "min_review_score": 0.65, "min_evidence_count": 2, "min_distinct_videos": 1, "require_existing_canonical": False, "auto_publish_enabled": True}
    assert classify_candidate(candidate, policy, existing_canonical=False) == ("shadow", "shadow")


def test_policy_marks_safe_existing_label_as_silver_auto_publish():
    from app.archive.labeling.policy import classify_candidate
    candidate = {"kind": "topic", "unit_type": "window", "confidence_score": 0.82, "evidence_count": 2, "distinct_videos": 1}
    policy = {"min_publish_score": 0.90, "min_review_score": 0.65, "min_evidence_count": 2, "min_distinct_videos": 1, "require_existing_canonical": True, "auto_publish_enabled": True}
    assert classify_candidate(candidate, policy, existing_canonical=True) == ("silver", "auto_published")
```

- [ ] **Step 2: Implement policy classifier**

Create `app/archive/labeling/policy.py`:

```python
from __future__ import annotations


def classify_candidate(candidate: dict, policy: dict, existing_canonical: bool) -> tuple[str, str]:
    score = float(candidate.get("confidence_score") or 0)
    evidence_count = int(candidate.get("evidence_count") or 0)
    distinct_videos = int(candidate.get("distinct_videos") or 0)
    min_publish = float(policy.get("min_publish_score") or 0.90)
    min_review = float(policy.get("min_review_score") or 0.65)
    min_evidence = int(policy.get("min_evidence_count") or 1)
    min_videos = int(policy.get("min_distinct_videos") or 1)
    require_existing = bool(policy.get("require_existing_canonical"))
    auto_publish = bool(policy.get("auto_publish_enabled", True))

    evidence_ok = evidence_count >= min_evidence and distinct_videos >= min_videos
    if score >= min_publish and evidence_ok and auto_publish and (existing_canonical or not require_existing):
        return "gold", "auto_published"
    if score >= max(min_review, min_publish - 0.12) and evidence_ok and auto_publish and existing_canonical:
        return "silver", "auto_published"
    if score >= min_review and evidence_count > 0:
        return "bronze", "candidate"
    return "shadow", "shadow"
```

- [ ] **Step 3: Add repository functions**

Create `app/archive/labeling/repository.py` with:

```python
from __future__ import annotations

import json
from sqlalchemy import text
from app.archive.labeling.normalization import normalized_alias, slugify_label


def create_extraction_run(db, scope: str, extraction_tier: str, video_id: str | None = None, model_name: str | None = None) -> str:
    row = db.execute(text("""
        INSERT INTO archive_extraction_runs (scope, extraction_tier, video_id, model_name, status, started_at)
        VALUES (:scope, :extraction_tier, :video_id, :model_name, 'running', now())
        RETURNING id
    """), {"scope": scope, "extraction_tier": extraction_tier, "video_id": video_id, "model_name": model_name}).first()
    return str(row[0])


def finish_extraction_run(db, run_id: str, status: str, metrics: dict, error: str | None = None):
    db.execute(text("""
        UPDATE archive_extraction_runs
        SET status = :status, metrics = CAST(:metrics AS jsonb), error = :error, finished_at = now()
        WHERE id = :run_id
    """), {"run_id": run_id, "status": status, "metrics": json.dumps(metrics), "error": error})


def upsert_label_candidate(db, *, label: str, kind: str, aliases: list[str], confidence_score: float, source: str, publish_tier: str, status: str, run_id: str | None) -> str:
    slug = slugify_label(label)
    row = db.execute(text("""
        INSERT INTO archive_labels (slug, label, kind, status, source, publish_tier, confidence_score, created_by_run_id, created_at, updated_at)
        VALUES (:slug, :label, :kind, :status, :source, :publish_tier, :confidence_score, :run_id, now(), now())
        ON CONFLICT (slug) DO UPDATE SET
            label = EXCLUDED.label,
            kind = EXCLUDED.kind,
            confidence_score = GREATEST(archive_labels.confidence_score, EXCLUDED.confidence_score),
            publish_tier = CASE WHEN EXCLUDED.confidence_score >= archive_labels.confidence_score THEN EXCLUDED.publish_tier ELSE archive_labels.publish_tier END,
            status = CASE WHEN archive_labels.status IN ('published', 'rejected', 'merged') THEN archive_labels.status ELSE EXCLUDED.status END,
            updated_at = now()
        RETURNING id
    """), {"slug": slug, "label": label, "kind": kind, "status": status, "source": source, "publish_tier": publish_tier, "confidence_score": confidence_score, "run_id": run_id}).first()
    label_id = str(row[0])
    for alias in aliases:
        db.execute(text("""
            INSERT INTO archive_label_aliases (label_id, alias, normalized_alias, source, status, weight, created_at)
            VALUES (:label_id, :alias, :normalized_alias, :source, 'active', 1, now())
            ON CONFLICT (label_id, normalized_alias) DO NOTHING
        """), {"label_id": label_id, "alias": alias, "normalized_alias": normalized_alias(alias), "source": source})
    return label_id


def assignment_key(label_id: str, video_id: str, unit_type: str, source: str, start_ms: int | None, end_ms: int | None, window_id: str | None, chapter_id: str | None) -> str:
    return f"{label_id}:{video_id}:{unit_type}:{source}:{chapter_id or ''}:{window_id or ''}:{start_ms if start_ms is not None else ''}:{end_ms if end_ms is not None else ''}"


def insert_assignment(db, *, label_id: str, video_id: str, unit_type: str, status: str, publish_tier: str, confidence_score: float, evidence: list[dict], source: str, run_id: str | None, start_ms: int | None = None, end_ms: int | None = None, window_id: str | None = None, chapter_id: str | None = None):
    key = assignment_key(label_id, video_id, unit_type, source, start_ms, end_ms, window_id, chapter_id)
    db.execute(text("""
        INSERT INTO archive_label_assignments (
            label_id, video_id, unit_type, chapter_id, window_id, start_ms, end_ms, status, publish_tier,
            confidence_score, evidence_count, evidence, source, run_id, assignment_key, component_scores, created_at, updated_at
        ) VALUES (
            :label_id, :video_id, :unit_type, :chapter_id, :window_id, :start_ms, :end_ms, :status, :publish_tier,
            :confidence_score, :evidence_count, CAST(:evidence AS jsonb), :source, :run_id, :assignment_key, '{}'::jsonb, now(), now()
        )
        ON CONFLICT (assignment_key) DO UPDATE SET
            confidence_score = GREATEST(archive_label_assignments.confidence_score, EXCLUDED.confidence_score),
            evidence = EXCLUDED.evidence,
            evidence_count = EXCLUDED.evidence_count,
            publish_tier = CASE WHEN archive_label_assignments.status = 'rejected' THEN archive_label_assignments.publish_tier ELSE EXCLUDED.publish_tier END,
            status = CASE WHEN archive_label_assignments.status = 'rejected' THEN 'rejected' ELSE EXCLUDED.status END,
            updated_at = now()
    """), {"label_id": label_id, "video_id": video_id, "unit_type": unit_type, "chapter_id": chapter_id, "window_id": window_id, "start_ms": start_ms, "end_ms": end_ms, "status": status, "publish_tier": publish_tier, "confidence_score": confidence_score, "evidence_count": len(evidence), "evidence": json.dumps(evidence), "source": source, "run_id": run_id, "assignment_key": key})
```

- [ ] **Step 4: Run tests and commit**

```bash
uv run --no-project --with pytest --with sqlalchemy --with psycopg --with psycopg-binary python -m pytest tests/test_labeling_policy.py tests/test_labeling_repository.py -q
rtk git add app/archive/labeling/repository.py app/archive/labeling/policy.py tests/test_labeling_repository.py tests/test_labeling_policy.py
rtk git commit -m "Add label candidate repository and policy"
```

---

## Task 5: Extraction Orchestrator

**Files:**
- Create: `app/archive/labeling/pipeline.py`
- Create: `scripts/backfill_label_extraction.py`
- Test: `tests/test_labeling_pipeline.py`

- [ ] **Step 1: Write orchestration test**

```python
def test_extract_labels_for_video_persists_windows_and_assignments(monkeypatch):
    from app.archive.labeling.pipeline import extract_labels_for_video

    class FakeDb:
        def __init__(self):
            self.actions = []
        def execute(self, sql, params=None):
            self.actions.append((str(sql), params))
            class Result:
                def mappings(self): return self
                def all(self): return []
                def first(self): return ["run-id"]
            return Result()

    db = FakeDb()
    result = extract_labels_for_video(db, video_id="00000000-0000-0000-0000-000000000001", extraction_tier="cheap")
    assert result["video_id"] == "00000000-0000-0000-0000-000000000001"
    assert result["extraction_tier"] == "cheap"
```

- [ ] **Step 2: Implement pipeline skeleton**

Create `app/archive/labeling/pipeline.py`:

```python
from __future__ import annotations

from sqlalchemy import text
from app.archive.labeling.extractors import extract_alias_candidates, extract_keyphrase_candidates
from app.archive.labeling.policy import classify_candidate
from app.archive.labeling.repository import create_extraction_run, finish_extraction_run, insert_assignment, upsert_label_candidate
from app.archive.labeling.windows import build_windows_from_segments, load_source_segments, persist_windows


def _load_existing_aliases(db) -> list[dict]:
    return list(db.execute(text("""
        SELECT l.id AS label_id, l.label, l.kind, a.alias
        FROM archive_labels l
        JOIN archive_label_aliases a ON a.label_id = l.id
        WHERE l.status IN ('published', 'candidate', 'review')
          AND a.status = 'active'
    """)).mappings().all())


def _load_policy(db, label_kind: str, unit_type: str, extraction_tier: str) -> dict:
    row = db.execute(text("""
        SELECT * FROM archive_label_policies
        WHERE label_kind = :label_kind AND unit_type = :unit_type AND extraction_tier = :extraction_tier
        LIMIT 1
    """), {"label_kind": label_kind, "unit_type": unit_type, "extraction_tier": extraction_tier}).mappings().first()
    return dict(row or {"min_publish_score": 0.90, "min_review_score": 0.65, "min_evidence_count": 2, "min_distinct_videos": 1, "require_existing_canonical": False, "auto_publish_enabled": True})


def extract_labels_for_video(db, video_id: str, extraction_tier: str = "cheap") -> dict:
    run_id = create_extraction_run(db, scope="video", extraction_tier=extraction_tier, video_id=video_id, model_name="deterministic")
    metrics = {"windows": 0, "candidates": 0, "assignments": 0}
    try:
        all_window_dicts: list[dict] = []
        for source in ("whisper", "youtube"):
            segments = load_source_segments(db, video_id, source)
            windows = build_windows_from_segments(segments, source=source)
            persist_windows(db, video_id, windows)
            metrics["windows"] += len(windows)
            all_window_dicts.extend([
                {"id": window.text_hash, "video_id": video_id, "text": window.text, "start_ms": window.start_ms, "end_ms": window.end_ms}
                for window in windows
            ])

        aliases = _load_existing_aliases(db)
        candidates = extract_alias_candidates(all_window_dicts, aliases)
        candidates.extend(extract_keyphrase_candidates(all_window_dicts, min_distinct_videos=1, min_occurrences=3))
        metrics["candidates"] = len(candidates)

        for candidate in candidates:
            evidence = list(candidate.evidence)
            distinct_videos = len({item.get("video_id") for item in evidence if item.get("video_id")})
            policy = _load_policy(db, candidate.kind, "window", extraction_tier)
            publish_tier, assignment_status = classify_candidate({
                "kind": candidate.kind,
                "unit_type": "window",
                "confidence_score": candidate.confidence_score,
                "evidence_count": len(evidence),
                "distinct_videos": distinct_videos,
            }, policy, existing_canonical=False)
            label_status = "published" if assignment_status == "auto_published" else "candidate"
            label_id = upsert_label_candidate(db, label=candidate.label, kind=candidate.kind, aliases=list(candidate.aliases), confidence_score=candidate.confidence_score, source="automatic", publish_tier=publish_tier, status=label_status, run_id=run_id)
            label_row = db.execute(text("SELECT status, canonical_id FROM archive_labels WHERE id = :label_id"), {"label_id": label_id}).mappings().first()
            if label_row and label_row["status"] in {"rejected", "merged"}:
                continue
            for item in evidence:
                insert_assignment(db, label_id=label_id, video_id=str(item["video_id"]), unit_type="window", status=assignment_status, publish_tier=publish_tier, confidence_score=candidate.confidence_score, evidence=[item], source="hybrid", run_id=run_id, start_ms=int(item.get("start_ms") or 0), end_ms=int(item.get("end_ms") or 0))
                metrics["assignments"] += 1
        finish_extraction_run(db, run_id, "completed", metrics)
        return {"video_id": video_id, "extraction_tier": extraction_tier, **metrics}
    except Exception as exc:
        finish_extraction_run(db, run_id, "failed", metrics, error=str(exc))
        raise
```

- [ ] **Step 3: Add backfill script**

Create `scripts/backfill_label_extraction.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.labeling.pipeline import extract_labels_for_video
from app.db import session_scope


def main(limit: int, extraction_tier: str):
    with session_scope() as db:
        rows = db.execute(text("""
            SELECT v.id
            FROM videos v
            WHERE EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id)
               OR EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id)
            ORDER BY COALESCE(v.uploaded_at, v.created_at) DESC NULLS LAST
            LIMIT :limit
        """), {"limit": limit}).all()
        total = {"videos": 0, "windows": 0, "candidates": 0, "assignments": 0}
        for row in rows:
            result = extract_labels_for_video(db, str(row[0]), extraction_tier=extraction_tier)
            total["videos"] += 1
            total["windows"] += int(result.get("windows") or 0)
            total["candidates"] += int(result.get("candidates") or 0)
            total["assignments"] += int(result.get("assignments") or 0)
        print("label extraction backfill complete: " + " ".join(f"{key}={value}" for key, value in sorted(total.items())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--extraction-tier", choices=["cheap", "balanced", "premium"], default="cheap")
    args = parser.parse_args()
    main(limit=args.limit, extraction_tier=args.extraction_tier)
```

- [ ] **Step 4: Run tests and script smoke**

```bash
uv run --no-project --with pytest --with sqlalchemy python -m pytest tests/test_labeling_pipeline.py -q
python3 scripts/backfill_label_extraction.py --limit 1 --extraction-tier cheap
```

- [ ] **Step 5: Commit**

```bash
rtk git add app/archive/labeling/pipeline.py scripts/backfill_label_extraction.py tests/test_labeling_pipeline.py
rtk git commit -m "Add automatic label extraction pipeline"
```

---

## Task 6: Admin Review and Correction API

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/routes/archive.py`
- Create: `tests/test_labeling_routes.py`

- [ ] **Step 1: Add schemas**

Add to `app/schemas.py`:

```python
class ArchiveLabelResponse(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    kind: str
    status: str
    source: str
    publish_tier: str
    confidence_score: float
    description: Optional[str] = None


class ArchiveLabelAssignmentResponse(BaseModel):
    id: uuid.UUID
    label: ArchiveLabelResponse
    video_id: uuid.UUID
    unit_type: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    status: str
    publish_tier: str
    confidence_score: float
    evidence_count: int
    evidence: List[Dict[str, Any]] = Field(default_factory=list)


class ArchiveLabelReviewAction(BaseModel):
    action: str = Field(..., description="approve, reject, publish, hide, merge, rename")
    label: Optional[str] = None
    target_label_id: Optional[uuid.UUID] = None
    reason: Optional[str] = None
```

- [ ] **Step 2: Add admin routes**

Add routes under `app/routes/archive.py`:

```text
GET  /admin/archive/labels
GET  /admin/archive/labels/{label_id}/assignments
POST /admin/archive/labels/{label_id}/review
POST /admin/archive/label-assignments/{assignment_id}/review
POST /admin/archive/labels/extract-video/{video_id}
```

All must use `Depends(require_role(ROLE_ADMIN))`.

- [ ] **Step 3: Review action semantics**

Implement:

```text
approve -> label.status='published', assignment.status='admin_approved'
reject -> status='rejected'
publish -> label.status='published'
hide -> label.status='hidden'
merge -> source label.status='merged', source canonical_id=target_label_id
rename -> update label and slug if slug not taken
```

Every action inserts `archive_label_feedback`.

- [ ] **Step 4: Tests**

Create route tests asserting:

- unauthenticated admin endpoints are blocked
- review action updates status
- feedback row is inserted
- extract-video endpoint creates an extraction run

- [ ] **Step 5: Commit**

```bash
rtk git add app/schemas.py app/routes/archive.py tests/test_labeling_routes.py
rtk git commit -m "Add admin label review API"
```

---

## Task 7: Admin Label Intelligence Workbench UI

**Files:**
- Create: `frontend/src/routes/admin/AdminLabelIntelligence.tsx`
- Modify: `frontend/src/routes/admin/AdminLayout.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/src/tests/AdminLabelIntelligence.test.tsx`

- [ ] **Step 1: UI behavior contract**

Admin page sections:

1. Candidate labels queue
2. Selected label detail
3. Evidence moments list
4. Actions: publish, approve, reject, hide, merge, rename
5. Trigger extraction for a VOD by ID

- [ ] **Step 2: Add frontend types**

Add `ArchiveLabelResponse`, `ArchiveLabelAssignmentResponse`, and `ArchiveLabelReviewAction` to `frontend/src/types/api.ts`.

- [ ] **Step 3: Implement page**

Use existing admin UI patterns from `AdminVideoMetadata.tsx` and `AdminArchivePeriods.tsx`. Keep native controls and simple tables.

- [ ] **Step 4: Tests**

Test:

- renders candidate labels
- selecting a label loads assignments
- publish/reject buttons call review endpoints
- extraction button calls extract-video endpoint

- [ ] **Step 5: Wire route and commit**

```bash
npm --prefix frontend test -- --run src/tests/AdminLabelIntelligence.test.tsx
npm --prefix frontend run build
rtk git add frontend/src/routes/admin/AdminLabelIntelligence.tsx frontend/src/routes/admin/AdminLayout.tsx frontend/src/main.tsx frontend/src/types/api.ts frontend/src/tests/AdminLabelIntelligence.test.tsx
rtk git commit -m "Add admin label intelligence workbench"
```

---

## Task 8: Hierarchy Rollups, Chapters, and Series Labels

**Files:**
- Create: `app/archive/labeling/rollups.py`
- Create: `app/archive/labeling/chapters.py`
- Create: `tests/test_labeling_rollups.py`
- Create: `tests/test_labeling_chapters.py`

- [ ] **Step 1: Write VOD rollup tests**

```python
def test_vod_rollup_requires_multiple_windows_or_duration_share():
    from app.archive.labeling.rollups import derive_vod_label_assignments

    window_assignments = [
        {"label_id": "topic-gaza", "video_id": "v1", "start_ms": 0, "end_ms": 120000, "confidence_score": 0.92, "status": "auto_published", "publish_tier": "gold"},
        {"label_id": "topic-gaza", "video_id": "v1", "start_ms": 120000, "end_ms": 240000, "confidence_score": 0.90, "status": "auto_published", "publish_tier": "gold"},
    ]
    rollups = derive_vod_label_assignments(window_assignments, video_duration_seconds=3600)
    assert rollups[0]["unit_type"] == "vod"
    assert rollups[0]["label_id"] == "topic-gaza"
    assert rollups[0]["evidence_count"] == 2


def test_single_fleeting_window_does_not_become_vod_label():
    from app.archive.labeling.rollups import derive_vod_label_assignments

    window_assignments = [
        {"label_id": "topic-gaza", "video_id": "v1", "start_ms": 0, "end_ms": 10000, "confidence_score": 0.92, "status": "auto_published", "publish_tier": "gold"},
    ]
    assert derive_vod_label_assignments(window_assignments, video_duration_seconds=7200) == []
```

- [ ] **Step 2: Implement VOD rollups**

Create `app/archive/labeling/rollups.py`:

```python
from __future__ import annotations

from collections import defaultdict


def derive_vod_label_assignments(window_assignments: list[dict], video_duration_seconds: int, min_windows: int = 2, min_duration_share: float = 0.04) -> list[dict]:
    by_label: dict[str, list[dict]] = defaultdict(list)
    for assignment in window_assignments:
        if assignment.get("status") not in {"auto_published", "admin_approved"}:
            continue
        by_label[str(assignment["label_id"])].append(assignment)
    rollups: list[dict] = []
    duration_ms = max(1, int(video_duration_seconds or 0) * 1000)
    for label_id, rows in by_label.items():
        covered_ms = sum(max(0, int(row.get("end_ms") or 0) - int(row.get("start_ms") or 0)) for row in rows)
        duration_share = covered_ms / duration_ms
        if len(rows) < min_windows and duration_share < min_duration_share:
            continue
        rollups.append({
            "label_id": label_id,
            "video_id": str(rows[0]["video_id"]),
            "unit_type": "vod",
            "status": "auto_published",
            "publish_tier": "gold" if all(row.get("publish_tier") == "gold" for row in rows) else "silver",
            "confidence_score": min(0.99, sum(float(row.get("confidence_score") or 0) for row in rows) / len(rows) + min(0.10, duration_share)),
            "evidence_count": len(rows),
            "evidence": rows[:5],
        })
    return rollups
```

- [ ] **Step 3: Write chapter boundary tests**

```python
def test_chapters_group_adjacent_windows_with_same_label():
    from app.archive.labeling.chapters import derive_chapters_from_window_labels

    rows = [
        {"label_id": "topic-gaza", "label": "Gaza", "start_ms": 0, "end_ms": 120000},
        {"label_id": "topic-gaza", "label": "Gaza", "start_ms": 120000, "end_ms": 240000},
        {"label_id": "topic-gaming", "label": "Gaming", "start_ms": 600000, "end_ms": 720000},
    ]
    chapters = derive_chapters_from_window_labels(rows, max_gap_ms=60_000)
    assert chapters[0]["title"] == "Gaza"
    assert chapters[0]["start_ms"] == 0
    assert chapters[0]["end_ms"] == 240000
    assert chapters[1]["title"] == "Gaming"
```

- [ ] **Step 4: Implement chapter derivation**

Create `app/archive/labeling/chapters.py`:

```python
from __future__ import annotations


def derive_chapters_from_window_labels(window_labels: list[dict], max_gap_ms: int = 60_000) -> list[dict]:
    ordered = sorted(window_labels, key=lambda row: (int(row.get("start_ms") or 0), str(row.get("label_id") or "")))
    chapters: list[dict] = []
    for row in ordered:
        label_id = str(row.get("label_id") or "")
        label = str(row.get("label") or label_id)
        start_ms = int(row.get("start_ms") or 0)
        end_ms = int(row.get("end_ms") or start_ms)
        if chapters and chapters[-1]["label_id"] == label_id and start_ms - chapters[-1]["end_ms"] <= max_gap_ms:
            chapters[-1]["end_ms"] = max(chapters[-1]["end_ms"], end_ms)
            chapters[-1]["evidence_count"] += 1
        else:
            chapters.append({"label_id": label_id, "title": label, "start_ms": start_ms, "end_ms": end_ms, "evidence_count": 1})
    return [chapter for chapter in chapters if chapter["end_ms"] > chapter["start_ms"]]
```

- [ ] **Step 5: Series/category rules**

Add tests and implementation rules in `rollups.py`:

```python
SAFE_SERIES_LABELS = {"chadvice", "okbuddy", "gaming", "guests"}


def is_safe_auto_series(slug: str, distinct_videos: int, evidence_count: int) -> bool:
    return slug in SAFE_SERIES_LABELS and distinct_videos >= 2 and evidence_count >= 3
```

- [ ] **Step 6: Person mentioned vs person present**

Add explicit rule to `rollups.py`:

```python
def person_assignment_kind(evidence: list[dict]) -> str:
    text = " ".join(str(item.get("snippet") or "").lower() for item in evidence)
    present_markers = ("joins us", "on stream", "guest", "with ", "talking to")
    return "person_present" if any(marker in text for marker in present_markers) else "person_mentioned"
```

Public auto-publish for `person_present` must require seeded/admin-known person labels until a later face/speaker-disambiguation system exists.

- [ ] **Step 7: Commit**

```bash
uv run --no-project --with pytest python -m pytest tests/test_labeling_rollups.py tests/test_labeling_chapters.py -q
rtk git add app/archive/labeling/rollups.py app/archive/labeling/chapters.py tests/test_labeling_rollups.py tests/test_labeling_chapters.py
rtk git commit -m "Add label hierarchy rollups and chapters"
```

---

## Task 9: Public Rollups and Explore Integration

**Files:**
- Modify: `app/archive/intelligence_repository.py`
- Modify: `app/archive/intelligence_facets.py`
- Modify: `app/schemas.py`
- Modify: `frontend/src/routes/ExplorePage.tsx`
- Modify: `frontend/src/tests/ExplorePage.test.tsx`

- [ ] **Step 1: Public selection rules**

Public Explore should only consume:

```sql
archive_labels.status = 'published'
archive_label_assignments.status IN ('auto_published', 'admin_approved')
archive_label_assignments.publish_tier IN ('gold', 'silver')
```

- [ ] **Step 2: Add backend helper**

Add `published_label_cards_for_period(db, date_from, date_to, limit=12)` that returns topic/category/series cards with:

- label
- kind
- video count
- assignment count
- representative evidence
- confidence average

- [ ] **Step 3: Merge with existing topic cards**

Do not remove existing `archive_topic_period_stats` immediately. Compose cards from both systems, dedupe by label slug, prefer label assignments when they have better evidence.

- [ ] **Step 4: Frontend display**

Update `/explore` copy from “Topic cards” to “Detected topics and stream labels”. Add badges:

- `Topic`
- `Series`
- `Category`
- `Person`

- [ ] **Step 5: Tests and commit**

```bash
npm --prefix frontend test -- --run src/tests/ExplorePage.test.tsx
uv run --no-project --with fastapi --with pytest --with sqlalchemy --with psycopg --with psycopg-binary python -m pytest tests/test_archive_routes.py tests/test_labeling_routes.py -q
rtk git add app/archive/intelligence_repository.py app/archive/intelligence_facets.py app/schemas.py frontend/src/routes/ExplorePage.tsx frontend/src/tests/ExplorePage.test.tsx
rtk git commit -m "Surface published label intelligence in Explore"
```

---

## Task 10: Evaluation and Quality Reports

**Files:**
- Create: `app/archive/labeling/evaluation.py`
- Create: `scripts/report_label_quality.py`
- Create: `tests/test_labeling_evaluation.py`

- [ ] **Step 1: Add evaluation metrics**

Metrics:

- auto-published count
- rejected count
- admin approval rate
- false positive proxy: rejected / reviewed
- labels without evidence
- duplicate slug/alias collision candidates
- assignment coverage by VOD
- chapter/window coverage

- [ ] **Step 2: Script output contract**

`scripts/report_label_quality.py` prints:

```text
label quality report:
labels_total=...
auto_published=...
review_candidates=...
shadow=...
assignments_total=...
assignments_without_evidence=...
admin_approval_rate=...
rejected_rate=...
```

- [ ] **Step 3: Tests and commit**

```bash
uv run --no-project --with pytest --with sqlalchemy python -m pytest tests/test_labeling_evaluation.py -q
rtk git add app/archive/labeling/evaluation.py scripts/report_label_quality.py tests/test_labeling_evaluation.py
rtk git commit -m "Add label quality reporting"
```

---

## Task 11: Deployment, Backfill, and Live QA

**Files:**
- Modify only if deployment reveals issues.

- [ ] **Step 1: Full local validation**

```bash
npm --prefix frontend test -- --run
npm --prefix frontend run build
uv run --no-project --with fastapi --with httpx --with sqlalchemy --with psycopg --with psycopg-binary --with pytest --with pydantic --with pydantic-settings --with python-multipart --with itsdangerous --with passlib --with bcrypt --with email-validator --with pyjwt --with pytest-asyncio --with redis --with alembic --with openai --with slowapi --with psutil --with reportlab --with prometheus-client python -c "import app.ytdlp_validation, pytest, sys; sys.exit(pytest.main(['tests/test_archive_routes.py','tests/test_archive_summary_repository.py','tests/test_video_metadata_repository.py','tests/test_labeling_schema.py','tests/test_labeling_windows.py','tests/test_labeling_extractors.py','tests/test_labeling_policy.py','tests/test_labeling_pipeline.py','tests/test_labeling_routes.py','tests/test_labeling_evaluation.py','-q']))"
```

- [ ] **Step 2: Deploy**

```bash
rtk docker compose -p hasanara -f docker-compose.yml -f docker-compose.gtx1080.yml -f docker-compose.hasanara.yml up -d --build api frontend archive-intelligence-refresher
```

- [ ] **Step 3: Backfill small sample first**

```bash
rtk docker exec hasanara-api python3 /app/scripts/backfill_label_extraction.py --limit 10 --extraction-tier cheap
rtk docker exec hasanara-api python3 /app/scripts/report_label_quality.py
```

Expected:

- extraction runs complete
- transcript windows created
- candidate labels created
- only gold/silver safe assignments auto-published
- no labels without evidence are public

- [ ] **Step 4: Backfill larger sample**

```bash
rtk docker exec hasanara-api python3 /app/scripts/backfill_label_extraction.py --limit 100 --extraction-tier cheap
rtk docker exec hasanara-api python3 /app/scripts/backfill_archive_intelligence.py --refresh-stats --refresh-periods --refresh-summaries --quick
```

- [ ] **Step 5: Live smoke**

Check:

- `/admin/labels` or `/admin/label-intelligence` loads for authenticated admin and blocks unauthenticated users.
- `/explore` shows detected labels only when evidence exists.
- Public topic cards still include timestamped citations.
- No obvious junk labels appear in public Explore.
- A known VOD with `okbuddy`, `chadvice`, or `gaming` text gets candidate labels.

- [ ] **Step 6: Commit deployment fixes if needed**

```bash
rtk git status --short --branch
rtk git log --oneline -10
```

Commit only intended fixes. Do not push unless explicitly requested.

---

## Public Trust Guardrails

- Public labels must have timestamp evidence.
- People-present labels require stricter policy than people-mentioned labels.
- Admin rejections must survive reruns.
- Merged labels must redirect, not disappear.
- Candidate labels must never appear in public autocomplete or Explore.
- Generic labels like `politics`, `news`, `react`, `stream` should be demoted unless they are explicitly curated categories.
- Every extraction run must be auditable by `run_id`.

---

## Future Premium Tier Extensions

Do after the deterministic pipeline is stable:

1. Embeddings for `archive_transcript_windows` using local or API models.
2. Cluster naming for high-cohesion window groups.
3. LLM chapter title/summary generation with strict JSON and evidence spans.
4. People disambiguation with aliases and known guest list.
5. Related-label graph and co-occurrence maps.
6. Topic timeline pages with “rise/fall” views.
7. Admin feedback-based threshold tuning.

---

## Execution Recommendation

Use subagent-driven implementation with review gates:

1. Schema foundation.
2. Window builder.
3. Deterministic extractors.
4. Repository/policy.
5. Pipeline/backfill.
6. Admin review API.
7. Admin UI.
8. Hierarchy rollups and chapters.
9. Explore integration.
10. Evaluation reports.
11. Deploy/backfill/live QA.

This keeps public UX changes behind a stable evidence, confidence, and admin-feedback contract.
