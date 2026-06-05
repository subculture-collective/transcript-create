# Title Entity Curation CSV Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Recommended path:
> dispatch a fresh subagent per task, review each result with `review-quality`,
> then continue. For complex multi-agent splits, use
> `parallel-feature-development`, `team-composition-patterns`, and
> `team-communication-protocols`. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Build a safe CSV round-trip for cleaning title-derived entity candidates, combining duplicates, splitting composites, adding aliases/nicknames, and importing approved people/tags into HasanAra metadata and label aliases.

**Architecture:** Keep curation review outside the app UI for now. Export a CSV with source candidates and blank review columns; the human edits canonical/type/aliases/status rows; an import command validates and upserts `archive_people` or `archive_video_tags`, then upserts matching `archive_labels` and `archive_label_aliases` so future title/transcript extraction can match aliases. Do not auto-import noisy suggestions without an explicit approved row.

**Tech Stack:** Python CLI scripts, SQLAlchemy sessions, PostgreSQL metadata tables, pytest.

---

## Curated CSV contract

Export columns:

```csv
candidate,guess_type,count,example_title,example_video_id,decision,entity_type,person_role,canonical,aliases,notes
Austin,person,3,HasanAbi talks to Austin,video-id,,,,,
Johnny Depp Amber Heard,person,1,Johnny Depp Amber Heard trial,video-id,,,,,
```

Human-editable import columns:

- `decision`: `approve`, `skip`, or empty. Only `approve` imports.
- `entity_type`: `person`, `game`, `event`, `topic`, `place`, `org`, `meme`, `category`, `series`, or `thing`.
- `person_role`: optional for `person` rows only: `guest`, `host`, `caller`, `subject`, or `mentioned`.
- `canonical`: canonical display label, e.g. `AustinShow`, `Will Neff`, `Johnny Depp`.
- `aliases`: pipe-separated aliases, e.g. `Austin|AustinShow|austinshow`.
- `notes`: free text stored as metadata description only when no existing description exists.

Composite splits are represented by duplicate candidate rows with different canonicals:

```csv
Johnny Depp Amber Heard,person,1,Johnny Depp Amber Heard trial,video-id,approve,person,subject,Johnny Depp,Johnny Depp,
Johnny Depp Amber Heard,person,1,Johnny Depp Amber Heard trial,video-id,approve,person,subject,Amber Heard,Amber Heard,
```

Duplicate merges are represented by several candidates pointing at the same canonical:

```csv
Austin,person,2,...,video-a,approve,person,guest,AustinShow,Austin|AustinShow,
AustinShow,person,4,...,video-b,approve,person,guest,AustinShow,Austin|AustinShow,
```

---

### Task 1: Export reviewable title entity CSV

**Files:**
- Modify: `scripts/suggest_people_from_titles.py`
- Test: `tests/test_labeling_extractors.py`

- [ ] **Step 1: Extend CSV output columns**

Change `scripts/suggest_people_from_titles.py` so CSV output writes these fields exactly:

```python
fieldnames = [
    "candidate",
    "guess_type",
    "count",
    "example_title",
    "example_video_id",
    "decision",
    "entity_type",
    "person_role",
    "canonical",
    "aliases",
    "notes",
]
```

Each suggestion row should map existing `name` to `candidate`, set `guess_type` to `person`, and leave `decision`, `entity_type`, `canonical`, `aliases`, and `notes` empty for manual curation.

- [ ] **Step 2: Run export manually**

Run:

```bash
python scripts/suggest_people_from_titles.py --limit 50 --format csv > /tmp/title-entity-candidates.csv
```

Expected: the CSV header contains curation columns and no database writes happen.

---

### Task 2: Add curation import module

**Files:**
- Create: `app/archive/title_entity_curation.py`
- Test: `tests/test_title_entity_curation.py`

- [ ] **Step 1: Write failing tests for row parsing**

Create tests that assert:

```python
from app.archive.title_entity_curation import parse_aliases, normalize_curation_row


def test_parse_aliases_splits_pipe_and_dedupes():
    assert parse_aliases("Austin|AustinShow| Austin ") == ["Austin", "AustinShow"]


def test_normalize_curation_row_requires_approved_canonical_and_type():
    row = normalize_curation_row({
        "candidate": "Austin",
        "decision": "approve",
        "entity_type": "person",
        "canonical": "AustinShow",
        "aliases": "Austin|AustinShow",
    })
    assert row["entity_type"] == "person"
    assert row["canonical"] == "AustinShow"
    assert row["aliases"] == ["Austin", "AustinShow"]
```

- [ ] **Step 2: Implement parser helpers**

Implement:

```python
def parse_aliases(value: str | None) -> list[str]: ...
def normalize_curation_row(row: dict[str, str]) -> dict[str, object] | None: ...
```

Rules:
- return `None` for empty/skip rows;
- approved rows require non-empty `entity_type` and `canonical`;
- valid entity types are `person`, `game`, `event`, `topic`, `place`, `org`, `meme`, `category`, `series`, `thing`;
- valid person roles are `guest`, `host`, `caller`, `subject`, `mentioned`; roles are allowed only for `person` rows;
- always include the original `candidate` as an alias if present.

---

### Task 3: Import approved people/tags and seed label aliases

**Files:**
- Modify: `app/archive/title_entity_curation.py`
- Test: `tests/test_title_entity_curation.py`

- [ ] **Step 1: Write import tests with fake DB or test DB**

Add tests that prove:
- `person` rows upsert `archive_people` with merged aliases.
- non-person rows upsert `archive_video_tags` using `kind = entity_type` except `thing` becomes `topic`.
- importing `Austin` and `AustinShow` as `AustinShow` results in one canonical row with both aliases.
- importing `Johnny Depp Amber Heard` twice can create `Johnny Depp` and `Amber Heard` separately.

- [ ] **Step 2: Implement importer**

Implement:

```python
def import_title_entity_curation_rows(db, rows: list[dict[str, str]], *, seed_aliases: bool = True) -> dict[str, int]: ...
```

Use existing helpers from `app.archive.video_metadata_repository`:
- `slugify`

Also upsert matching `archive_labels` and `archive_label_aliases` directly for every approved curated row, including non-allowlisted games/events/topics.

Counts returned:

```python
{"rows": approved_count, "people": people_count, "tags": tag_count, "aliases": seeded_alias_count}
```

---

### Task 4: Add import CLI

**Files:**
- Create: `scripts/import_title_entity_curation.py`
- Test: `tests/test_title_entity_curation.py`

- [ ] **Step 1: Create CLI**

Add a script with:

```bash
python scripts/import_title_entity_curation.py path/to/curated.csv --dry-run
python scripts/import_title_entity_curation.py path/to/curated.csv
```

Behavior:
- `--dry-run` validates and prints counts without committing.
- normal run imports rows, seeds label aliases, and prints counts.

- [ ] **Step 2: Add usage examples to script help**

Help text should show:

```bash
python scripts/suggest_people_from_titles.py --limit 2000 --format csv > title-entity-candidates.csv
python scripts/import_title_entity_curation.py title-entity-candidates.curated.csv --dry-run
python scripts/import_title_entity_curation.py title-entity-candidates.curated.csv
```

---

### Task 5: Verify and deploy-safe usage

**Files:**
- Test: `tests/test_title_entity_curation.py`

- [ ] **Step 1: Run tests**

```bash
pytest tests/test_title_entity_curation.py tests/test_labeling_extractors.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run sample export**

```bash
python scripts/suggest_people_from_titles.py --limit 50 --format csv > /tmp/title-entity-candidates.csv
```

Expected: CSV is reviewable and import columns are blank.

- [ ] **Step 3: Document live commands in final response**

Use Docker commands only after local verification:

```bash
rtk docker exec hasanara-api python3 /app/scripts/suggest_people_from_titles.py --limit 2000 --format csv > title-entity-candidates.csv
rtk docker cp title-entity-candidates.curated.csv hasanara-api:/tmp/title-entity-candidates.curated.csv
rtk docker exec hasanara-api python3 /app/scripts/import_title_entity_curation.py /tmp/title-entity-candidates.curated.csv --dry-run
rtk docker exec hasanara-api python3 /app/scripts/import_title_entity_curation.py /tmp/title-entity-candidates.curated.csv
rtk docker exec hasanara-api python3 /app/scripts/materialize_label_metadata.py --limit 2000
```

---

## Self-review

- Spec coverage: duplicate merges, composite splits, aliases/nicknames, people/events/games/topics are covered by CSV row contract and import behavior.
- Placeholder scan: no TBD/TODO placeholders; import rules and valid entity types are explicit.
- Type consistency: `entity_type`, `canonical`, and `aliases` are used consistently across export, parser, importer, and CLI.
