# Automated Label Metadata Materialization Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Recommended path:
> dispatch a fresh subagent per task, review each result with `review-quality`,
> then continue. For complex multi-agent splits, use
> `parallel-feature-development`, `team-composition-patterns`, and
> `team-communication-protocols`. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Automatically populate Explore people and tag facets from reviewed or safe label assignments.

**Architecture:** Label extraction remains the detection layer; durable video metadata tables remain the public facet layer. A conservative materializer reads accepted `archive_labels` + `archive_label_assignments`, creates missing metadata rows, and additively inserts join rows without deleting admin metadata.

**Tech Stack:** Python, SQLAlchemy textual SQL, PostgreSQL JSONB, pytest, existing HasanAra archive metadata repository patterns.

---

## Files

- Modify: `app/archive/video_metadata_repository.py`
  - Add `materialize_label_assignments_to_metadata(db, limit=500)`.
  - Add safe tag kind mapping and allowlist.
  - Use additive `ON CONFLICT DO NOTHING` writes for `archive_video_people` and `archive_video_taggings`.
- Create: `scripts/materialize_label_metadata.py`
  - CLI wrapper for production/live runs.
- Modify: `tests/test_video_metadata_repository.py`
  - Add unit-style fake DB tests for materialization SQL contract.
- Optionally modify: `app/archive/labeling/pipeline.py`
  - Only if auto-materializing immediately after each extraction is safe. Default plan does not wire this automatically.

---

## Safety Rules

- Only read labels where `archive_labels.status = 'published'`.
- Only read assignments where `archive_label_assignments.status IN ('auto_published', 'admin_approved')`.
- Only read assignments where `publish_tier IN ('gold', 'silver')`.
- People:
  - Require `kind = 'person'`.
  - Require evidence to contain a presence marker such as `guest`, `joins us`, `on stream`, `interview`, `talking to`, or `with`.
  - Insert `archive_video_people.role = 'guest'`, `confidence = 'auto'`.
- Tags:
  - Allow `kind IN ('category', 'series', 'game', 'meme')`.
  - Auto-create only allowlisted slugs: `gaming`, `chadvice`, `okbuddy`, `guests`, `news`, `politics`, `react`, `debate`, `interview`, `irl`.
  - Insert `archive_video_taggings.confidence = 'auto'`.
- Never call `set_video_metadata()` from materialization because it deletes existing joins.
- Use additive `ON CONFLICT DO NOTHING` for joins so admin metadata is preserved.

---

### Task 1: Repository Materializer

**Files:**
- Modify: `app/archive/video_metadata_repository.py`
- Test: `tests/test_video_metadata_repository.py`

- [ ] **Step 1: Write failing tests**

Add tests that create fake published label assignment rows and assert:

```python
from app.archive.video_metadata_repository import materialize_label_assignments_to_metadata


def test_materialize_label_assignments_creates_safe_tags_additively():
    db = _FakeMetadataDb()
    video_id = uuid.uuid4()
    db.add_video(video_id=video_id, title="Gaming VOD")
    db.label_assignment_rows = [
        {
            "label_id": uuid.uuid4(),
            "video_id": video_id,
            "slug": "gaming",
            "label": "Gaming",
            "kind": "category",
            "evidence": [{"snippet": "gaming segment"}],
        },
        {
            "label_id": uuid.uuid4(),
            "video_id": video_id,
            "slug": "random-drama",
            "label": "Random Drama",
            "kind": "category",
            "evidence": [{"snippet": "not allowlisted"}],
        },
    ]

    result = materialize_label_assignments_to_metadata(db)

    assert result == {"people": 0, "tags": 1, "assignments": 2}
    assert "gaming" in db.tags
    assert len(db.video_taggings) == 1
    assert db.video_taggings[0]["confidence"] == "auto"
```

```python
def test_materialize_label_assignments_requires_person_presence_evidence():
    db = _FakeMetadataDb()
    video_id = uuid.uuid4()
    db.add_video(video_id=video_id, title="Guest VOD")
    db.label_assignment_rows = [
        {
            "label_id": uuid.uuid4(),
            "video_id": video_id,
            "slug": "guest-one",
            "label": "Guest One",
            "kind": "person",
            "evidence": [{"snippet": "Guest One joins us on stream."}],
        },
        {
            "label_id": uuid.uuid4(),
            "video_id": video_id,
            "slug": "mentioned-person",
            "label": "Mentioned Person",
            "kind": "person",
            "evidence": [{"snippet": "chat mentioned Mentioned Person."}],
        },
    ]

    result = materialize_label_assignments_to_metadata(db)

    assert result == {"people": 1, "tags": 0, "assignments": 2}
    assert "guest-one" in db.people
    assert "mentioned-person" not in db.people
    assert len(db.video_people) == 1
    assert db.video_people[0]["role"] == "guest"
    assert db.video_people[0]["confidence"] == "auto"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run --no-project --with pytest --with sqlalchemy python -m pytest tests/test_video_metadata_repository.py -q
```

Expected: import error or missing `materialize_label_assignments_to_metadata`.

- [ ] **Step 3: Implement materializer**

Add constants and helpers in `app/archive/video_metadata_repository.py`:

```python
AUTO_TAG_SLUG_ALLOWLIST = {"gaming", "chadvice", "okbuddy", "guests", "news", "politics", "react", "debate", "interview", "irl"}
AUTO_TAG_KINDS = {"category", "series", "game", "meme"}
PERSON_PRESENT_MARKERS = ("joins us", "on stream", "guest", "interview", "talking to", "with ")


def _evidence_text(evidence: Any) -> str:
    parts: list[str] = []
    for item in _as_list(evidence):
        if isinstance(item, dict):
            parts.append(str(item.get("snippet") or item.get("text") or item.get("quote") or ""))
        else:
            parts.append(str(item))
    return " ".join(parts).lower()


def _person_is_present(evidence: Any) -> bool:
    text_value = _evidence_text(evidence)
    return any(marker in text_value for marker in PERSON_PRESENT_MARKERS)
```

Add `materialize_label_assignments_to_metadata(db, limit=500)` that:
- selects published accepted assignments,
- creates metadata rows with `ON CONFLICT (slug) DO UPDATE`,
- inserts joins with `ON CONFLICT DO NOTHING`,
- returns `{"people": people_count, "tags": tag_count, "assignments": row_count}`.

- [ ] **Step 4: Run tests to verify pass**

Run the same pytest command. Expected: pass.

---

### Task 2: CLI Script

**Files:**
- Create: `scripts/materialize_label_metadata.py`
- Test: import/CLI smoke via Python execution.

- [ ] **Step 1: Add script**

Create:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.video_metadata_repository import materialize_label_assignments_to_metadata
from app.db import session_scope


def main(limit: int) -> None:
    with session_scope() as db:
        result = materialize_label_assignments_to_metadata(db, limit=limit)
    print("label metadata materialization complete: " + " ".join(f"{key}={value}" for key, value in sorted(result.items())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Materialize accepted label assignments into Explore people/tags metadata.")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    main(args.limit)
```

- [ ] **Step 2: Run import smoke**

Run:

```bash
uv run --no-project --with sqlalchemy python scripts/materialize_label_metadata.py --help
```

Expected: help output and exit code 0.

---

### Task 3: Live Run and Explore Refresh

**Files:** none unless a defect is found.

- [ ] **Step 1: Run targeted tests**

```bash
uv run --no-project --with fastapi --with httpx --with sqlalchemy --with psycopg --with psycopg-binary --with pytest --with pydantic --with pydantic-settings --with python-multipart --with itsdangerous --with passlib --with bcrypt --with email-validator --with pyjwt --with pytest-asyncio --with redis --with alembic --with openai --with slowapi --with psutil --with reportlab --with prometheus-client --with jinja2 python -m pytest tests/test_video_metadata_repository.py tests/test_archive_routes.py -q
npm --prefix frontend test -- --run src/tests/ExplorePage.test.tsx
```

- [ ] **Step 2: Deploy API**

```bash
rtk docker compose -p hasanara -f docker-compose.yml -f docker-compose.gtx1080.yml -f docker-compose.hasanara.yml up -d --build api archive-intelligence-refresher
```

- [ ] **Step 3: Run materialization**

```bash
rtk docker exec hasanara-api python3 /app/scripts/materialize_label_metadata.py --limit 500
```

- [ ] **Step 4: Refresh intelligence**

```bash
rtk docker exec hasanara-api python3 /app/scripts/backfill_archive_intelligence.py --refresh-stats --refresh-periods --refresh-summaries --quick
```

- [ ] **Step 5: Smoke check Explore facets**

```bash
rtk docker exec hasanara-api python3 -c "from fastapi.testclient import TestClient; from app.main import app; c=TestClient(app); d=c.get('/archive/intelligence?topic_limit=8&period_limit=3').json(); print('people', len(d.get('people', [])), 'tags', len(d.get('tags', [])), d.get('tags', [])[:5])"
```

Expected: `tags` is greater than 0 if any accepted safe tag assignments exist; `people` may remain 0 until published person labels with presence evidence exist.

---

## Commit

After tests and smoke pass:

```bash
rtk git status --short --branch
rtk git diff --stat
rtk git add app/archive/video_metadata_repository.py scripts/materialize_label_metadata.py tests/test_video_metadata_repository.py docs/superpowers/plans/2026-06-04-automated-label-metadata-materialization.md
rtk git diff --cached --check
rtk git commit -m "Materialize label metadata facets"
```

---

## Self-Review

- Spec coverage: automated people and tag population is covered by a repository materializer, CLI, tests, deploy, and smoke checks.
- Placeholder scan: no TBD/TODO placeholders are required for execution.
- Type consistency: result contract is consistently `people`, `tags`, `assignments`; join confidence uses existing text values `auto`/`admin`.
