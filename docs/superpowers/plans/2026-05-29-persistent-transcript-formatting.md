# Persistent Transcript Formatting Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Recommended path:
> dispatch a fresh subagent per task, review each result with `review-quality`,
> then continue. For complex multi-agent splits, use
> `parallel-feature-development`, `team-composition-patterns`, and
> `team-communication-protocols`. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Add a deterministic non-LLM transcript formatting pass that persists clean paragraphs/speaker turns with timestamp mappings for the transcript page.

**Architecture:** Keep raw `segments` immutable and add a separate `transcript_blocks` read model. The worker builds formatted blocks after diarization/vocabulary correction and segment persistence; the API exposes blocks in formatted mode; the frontend renders blocks when available and falls back to client-side grouping only for legacy videos.

**Tech Stack:** Python, FastAPI, SQLAlchemy text queries, PostgreSQL, Alembic, existing `worker.formatter.TranscriptFormatter`, React/Vite/TypeScript.

---

## File structure

- Create `alembic/versions/20260529_0600_add_transcript_blocks.py` — migration for persisted transcript paragraph/speaker-turn blocks.
- Modify `sql/schema.sql` — base schema for fresh installs.
- Create `app/transcripts/blocks.py` — pure block-building logic that reuses `TranscriptFormatter` and keeps segment timestamp mappings.
- Modify `app/schemas.py` — add block response schemas and extend formatted transcript response.
- Modify `app/crud.py` — add CRUD helpers for inserting and listing blocks.
- Modify `worker/pipeline.py` — call block builder and persist blocks after raw segments are inserted.
- Modify `app/routes/videos.py` — return persisted blocks in `mode=formatted`, falling back to on-demand building for old videos.
- Modify `frontend/src/types/api.ts` — add formatted block types.
- Modify `frontend/src/services/api.ts` — request `mode=formatted` for transcript page.
- Modify `frontend/src/routes/VideoPage.tsx` — render formatted blocks when present.
- Test `tests/test_transcript_blocks.py` — pure formatting/block grouping behavior.
- Test `tests/test_transcript_presentation.py` — API presentation with persisted blocks and fallback behavior.
- Test `tests/worker/test_pipeline.py` or a focused repository test — worker persistence uses block insert helper.

---

### Task 1: Add transcript block schema

**Files:**
- Create: `alembic/versions/20260529_0600_add_transcript_blocks.py`
- Modify: `sql/schema.sql`

- [ ] **Step 1: Write migration**

Create `alembic/versions/20260529_0600_add_transcript_blocks.py`:

```python
"""add transcript blocks

Revision ID: 20260529_0600
Revises: 20260529_0425
Create Date: 2026-05-29 06:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260529_0600"
down_revision = "20260529_0425"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transcript_blocks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("speaker_label", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("segment_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("kind", sa.Text(), nullable=False, server_default="paragraph"),
        sa.Column("formatter_version", sa.Text(), nullable=False, server_default="rule-v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.CheckConstraint("kind IN ('paragraph', 'speaker_turn')", name="transcript_blocks_kind_check"),
        sa.UniqueConstraint("video_id", "block_index", name="transcript_blocks_video_index_unique"),
    )
    op.create_index("transcript_blocks_video_idx", "transcript_blocks", ["video_id"])
    op.create_index("transcript_blocks_video_time_idx", "transcript_blocks", ["video_id", "start_ms"])


def downgrade() -> None:
    op.drop_index("transcript_blocks_video_time_idx", table_name="transcript_blocks")
    op.drop_index("transcript_blocks_video_idx", table_name="transcript_blocks")
    op.drop_table("transcript_blocks")
```

- [ ] **Step 2: Update fresh-install schema**

Add after the `segments` table/index in `sql/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS transcript_blocks (
    id BIGSERIAL PRIMARY KEY,
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    block_index INT NOT NULL,
    start_ms INT NOT NULL,
    end_ms INT NOT NULL,
    speaker_label TEXT,
    text TEXT NOT NULL,
    segment_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    kind TEXT NOT NULL DEFAULT 'paragraph' CHECK (kind IN ('paragraph', 'speaker_turn')),
    formatter_version TEXT NOT NULL DEFAULT 'rule-v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (video_id, block_index)
);
CREATE INDEX IF NOT EXISTS transcript_blocks_video_idx ON transcript_blocks(video_id);
CREATE INDEX IF NOT EXISTS transcript_blocks_video_time_idx ON transcript_blocks(video_id, start_ms);
```

- [ ] **Step 3: Verify migration syntax**

Run: `python -m py_compile alembic/versions/20260529_0600_add_transcript_blocks.py`

Expected: exits 0.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/20260529_0600_add_transcript_blocks.py sql/schema.sql
git commit -m "Add transcript block storage schema"
```

---

### Task 2: Build deterministic transcript blocks

**Files:**
- Create: `app/transcripts/blocks.py`
- Test: `tests/test_transcript_blocks.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_transcript_blocks.py`:

```python
from app.transcripts.blocks import build_transcript_blocks
from app.transcripts.types import TranscriptSegment


def test_unlabeled_segments_are_grouped_into_readable_paragraphs():
    segments = [
        TranscriptSegment(start_ms=0, end_ms=900, text="hello everyone\n", speaker_label=None),
        TranscriptSegment(start_ms=950, end_ms=1800, text="this is a test", speaker_label=None),
        TranscriptSegment(start_ms=3400, end_ms=4300, text="new thought starts here", speaker_label=None),
    ]

    blocks = build_transcript_blocks(segments)

    assert len(blocks) == 2
    assert blocks[0].kind == "paragraph"
    assert blocks[0].speaker_label is None
    assert blocks[0].start_ms == 0
    assert blocks[0].end_ms == 1800
    assert blocks[0].segment_ids == [0, 1]
    assert "\n" not in blocks[0].text
    assert blocks[0].text == "Hello everyone. This is a test."
    assert blocks[1].text == "New thought starts here."


def test_speaker_changes_create_speaker_turn_blocks():
    segments = [
        TranscriptSegment(start_ms=0, end_ms=900, text="hello there", speaker_label="Hasan"),
        TranscriptSegment(start_ms=950, end_ms=1800, text="i keep talking", speaker_label="Hasan"),
        TranscriptSegment(start_ms=2000, end_ms=2600, text="short reply", speaker_label="Speaker 2"),
    ]

    blocks = build_transcript_blocks(segments)

    assert len(blocks) == 2
    assert blocks[0].kind == "speaker_turn"
    assert blocks[0].speaker_label == "Hasan"
    assert blocks[0].text == "Hello there. I keep talking."
    assert blocks[0].segment_ids == [0, 1]
    assert blocks[1].speaker_label == "Speaker 2"
    assert blocks[1].text == "Short reply."
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_transcript_blocks.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.transcripts.blocks'`.

- [ ] **Step 3: Implement block builder**

Create `app/transcripts/blocks.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from worker.formatter import TranscriptFormatter

from .types import TranscriptSegment


FORMATTER_VERSION = "rule-v1"


@dataclass(frozen=True)
class TranscriptBlock:
    block_index: int
    start_ms: int
    end_ms: int
    speaker_label: str | None
    text: str
    segment_ids: list[int]
    kind: Literal["paragraph", "speaker_turn"]
    formatter_version: str = FORMATTER_VERSION


def _formatter() -> TranscriptFormatter:
    return TranscriptFormatter(
        config={
            "enabled": True,
            "normalize_unicode": True,
            "normalize_whitespace": True,
            "remove_special_tokens": True,
            "remove_fillers": True,
            "filler_level": 1,
            "add_sentence_punctuation": True,
            "punctuation_mode": "rule-based",
            "add_internal_punctuation": True,
            "capitalize_sentences": True,
            "fix_all_caps": True,
            "detect_hallucinations": True,
            "segment_by_sentences": False,
            "merge_short_segments": False,
            "speaker_format": "structured",
            "language_specific_rules": True,
        }
    )


def _clean_segments(segments: Sequence[TranscriptSegment]) -> list[dict]:
    formatted = _formatter().format_segments(
        [
            {
                "start": segment.start_ms,
                "end": segment.end_ms,
                "text": segment.text,
                "speaker": segment.speaker_label,
                "speaker_label": segment.speaker_label,
            }
            for segment in segments
        ]
    )
    return [segment for segment in formatted if segment.get("text", "").strip()]


def _ends_sentence(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?"))


def _should_break_unlabeled(previous: dict | None, current: dict, current_text: str) -> bool:
    if previous is None:
        return True
    gap_ms = int(current["start"]) - int(previous["end"])
    previous_text = previous.get("text", "")
    previous_words = previous_text.split()
    return gap_ms >= 1200 or (_ends_sentence(previous_text) and len(previous_words) >= 14 and len(current_text.split()) >= 3)


def _join_text(parts: Sequence[str]) -> str:
    return " ".join(part.strip() for part in parts if part.strip()).strip()


def build_transcript_blocks(segments: Sequence[TranscriptSegment]) -> list[TranscriptBlock]:
    cleaned_segments = _clean_segments(segments)
    blocks: list[TranscriptBlock] = []
    current: list[dict] = []
    current_speaker: str | None = None

    def flush() -> None:
        nonlocal current
        if not current:
            return
        speaker = current_speaker
        blocks.append(
            TranscriptBlock(
                block_index=len(blocks),
                start_ms=int(current[0]["start"]),
                end_ms=int(current[-1]["end"]),
                speaker_label=speaker,
                text=_join_text([str(segment["text"]) for segment in current]),
                segment_ids=[int(segment["source_index"]) for segment in current],
                kind="speaker_turn" if speaker else "paragraph",
            )
        )
        current = []

    for idx, segment in enumerate(cleaned_segments):
        segment = dict(segment)
        segment["source_index"] = idx
        speaker = (segment.get("speaker_label") or segment.get("speaker") or None)
        text = str(segment.get("text", "")).strip()

        if speaker:
            if current and current_speaker != speaker:
                flush()
            current_speaker = str(speaker)
            current.append(segment)
            continue

        if current_speaker is not None:
            flush()
            current_speaker = None

        previous = current[-1] if current else None
        if current and _should_break_unlabeled(previous, segment, text):
            flush()
        current_speaker = None
        current.append(segment)

    flush()
    return blocks
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_transcript_blocks.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/transcripts/blocks.py tests/test_transcript_blocks.py
git commit -m "Build deterministic transcript formatting blocks"
```

---

### Task 3: Persist blocks from worker pipeline

**Files:**
- Modify: `app/crud.py`
- Modify: `worker/pipeline.py:609-665`
- Test: `tests/worker/test_pipeline.py` or `tests/worker/test_repositories.py`

- [ ] **Step 1: Add CRUD helpers**

Append to `app/crud.py`:

```python
def replace_transcript_blocks(conn, video_id, blocks):
    import json

    conn.execute(text("DELETE FROM transcript_blocks WHERE video_id = :v"), {"v": str(video_id)})
    for block in blocks:
        conn.execute(
            text(
                """
                INSERT INTO transcript_blocks (
                    video_id, block_index, start_ms, end_ms, speaker_label,
                    text, segment_ids, kind, formatter_version
                )
                VALUES (
                    :video_id, :block_index, :start_ms, :end_ms, :speaker_label,
                    :text, :segment_ids, :kind, :formatter_version
                )
                """
            ),
            {
                "video_id": str(video_id),
                "block_index": block.block_index,
                "start_ms": block.start_ms,
                "end_ms": block.end_ms,
                "speaker_label": block.speaker_label,
                "text": block.text,
                "segment_ids": json.dumps(block.segment_ids),
                "kind": block.kind,
                "formatter_version": block.formatter_version,
            },
        )


def list_transcript_blocks(db, video_id):
    return (
        db.execute(
            text(
                """
                SELECT block_index, start_ms, end_ms, speaker_label, text,
                       segment_ids, kind, formatter_version
                FROM transcript_blocks
                WHERE video_id = :v
                ORDER BY block_index
                """
            ),
            {"v": str(video_id)},
        )
        .mappings()
        .all()
    )
```

- [ ] **Step 2: Wire pipeline persistence**

Modify `worker/pipeline.py` imports:

```python
from app.transcripts.blocks import build_transcript_blocks
from app.transcripts.types import TranscriptSegment
```

After the segment insert loop at `worker/pipeline.py:636-664`, add:

```python
        transcript_segments = [
            TranscriptSegment(
                start_ms=int(s["start"] * 1000),
                end_ms=int(s["end"] * 1000),
                text=s["text"],
                speaker_label=s.get("speaker"),
            )
            for s in diar_segments
        ]
        formatted_blocks = build_transcript_blocks(transcript_segments)
        crud.replace_transcript_blocks(conn, video_id, formatted_blocks)
        logger.info("Inserted transcript formatting blocks", extra={"block_count": len(formatted_blocks)})
```

- [ ] **Step 3: Add focused persistence test**

If `tests/worker/test_repositories.py` has DB helper coverage, add this test there; otherwise add to `tests/test_transcript_blocks.py` with a lightweight fake connection:

```python
from app import crud
from app.transcripts.blocks import TranscriptBlock


class RecordingConn:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))


def test_replace_transcript_blocks_deletes_then_inserts_blocks():
    conn = RecordingConn()
    blocks = [
        TranscriptBlock(
            block_index=0,
            start_ms=0,
            end_ms=1000,
            speaker_label=None,
            text="Hello world.",
            segment_ids=[0],
            kind="paragraph",
        )
    ]

    crud.replace_transcript_blocks(conn, "00000000-0000-0000-0000-000000000001", blocks)

    assert "DELETE FROM transcript_blocks" in conn.calls[0][0]
    assert "INSERT INTO transcript_blocks" in conn.calls[1][0]
    assert conn.calls[1][1]["text"] == "Hello world."
    assert conn.calls[1][1]["segment_ids"] == "[0]"
```

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_transcript_blocks.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/crud.py worker/pipeline.py tests/test_transcript_blocks.py
git commit -m "Persist formatted transcript blocks in pipeline"
```

---

### Task 4: Expose blocks through formatted transcript API

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/routes/videos.py`
- Test: `tests/test_transcript_presentation.py`

- [ ] **Step 1: Add response schemas**

Add before `FormattedTranscriptResponse` in `app/schemas.py`:

```python
class TranscriptBlockResponse(BaseModel):
    """Formatted transcript paragraph or speaker turn with timestamp mapping."""

    block_index: int = Field(..., ge=0)
    start_ms: int = Field(..., ge=0)
    end_ms: int = Field(..., ge=0)
    speaker_label: Optional[str] = None
    text: str
    segment_ids: List[int] = Field(default_factory=list)
    kind: Literal["paragraph", "speaker_turn"] = "paragraph"
```

Update `FormattedTranscriptResponse`:

```python
class FormattedTranscriptResponse(BaseModel):
    """Response containing formatted transcript text and blocks."""

    video_id: uuid.UUID = Field(..., description="Unique identifier for the video")
    text: str = Field(..., description="Formatted transcript text")
    blocks: List[TranscriptBlockResponse] = Field(default_factory=list)
    format: Literal["inline", "dialogue", "structured"] = Field(..., description="Formatting style used")
    cleanup_config: CleanupConfig = Field(..., description="Cleanup configuration used")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of formatting"
    )
```

- [ ] **Step 2: Route uses persisted blocks first**

Modify `app/routes/videos.py` imports:

```python
from ..schemas import TranscriptBlockResponse
from ..transcripts.blocks import build_transcript_blocks
```

In the `mode == "formatted"` branch, before on-demand formatter code, add:

```python
        persisted_blocks = crud.list_transcript_blocks(db, video_id)
        if persisted_blocks:
            blocks = [
                TranscriptBlockResponse(
                    block_index=row["block_index"],
                    start_ms=row["start_ms"],
                    end_ms=row["end_ms"],
                    speaker_label=row["speaker_label"],
                    text=row["text"],
                    segment_ids=row["segment_ids"] or [],
                    kind=row["kind"],
                )
                for row in persisted_blocks
            ]
            formatted_text = "\n\n".join(
                f"{block.speaker_label}: {block.text}" if block.speaker_label else block.text
                for block in blocks
            )
            return FormattedTranscriptResponse(
                video_id=video_id,
                text=formatted_text,
                blocks=blocks,
                format="structured",
                cleanup_config=CleanupConfig(),
            )
```

Replace the existing on-demand formatted text creation with block fallback:

```python
        fallback_blocks = build_transcript_blocks(segments)
        blocks = [
            TranscriptBlockResponse(
                block_index=block.block_index,
                start_ms=block.start_ms,
                end_ms=block.end_ms,
                speaker_label=block.speaker_label,
                text=block.text,
                segment_ids=block.segment_ids,
                kind=block.kind,
            )
            for block in fallback_blocks
        ]
        formatted_text = "\n\n".join(
            f"{block.speaker_label}: {block.text}" if block.speaker_label else block.text
            for block in blocks
        )
```

Return `FormattedTranscriptResponse(..., text=formatted_text, blocks=blocks, ...)`.

- [ ] **Step 3: Add API tests**

Append to `tests/test_transcript_presentation.py`:

```python
from app.schemas import TranscriptBlockResponse, FormattedTranscriptResponse, CleanupConfig


def test_formatted_transcript_response_includes_blocks():
    response = FormattedTranscriptResponse(
        video_id="00000000-0000-0000-0000-000000000001",
        text="Hello world.",
        blocks=[
            TranscriptBlockResponse(
                block_index=0,
                start_ms=0,
                end_ms=1000,
                speaker_label=None,
                text="Hello world.",
                segment_ids=[0],
                kind="paragraph",
            )
        ],
        format="structured",
        cleanup_config=CleanupConfig(),
    )

    assert response.blocks[0].text == "Hello world."
    assert response.blocks[0].segment_ids == [0]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_transcript_presentation.py tests/test_transcript_blocks.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/schemas.py app/routes/videos.py tests/test_transcript_presentation.py
git commit -m "Expose formatted transcript blocks via API"
```

---

### Task 5: Render formatted blocks in frontend

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/routes/VideoPage.tsx`

- [ ] **Step 1: Add frontend types**

Update `frontend/src/types/api.ts`:

```ts
export interface TranscriptBlock {
  block_index: number;
  start_ms: number;
  end_ms: number;
  speaker_label?: string | null;
  text: string;
  segment_ids: number[];
  kind: 'paragraph' | 'speaker_turn';
}

export interface TranscriptResponse {
  video_id: UUID;
  segments: Segment[];
  blocks?: TranscriptBlock[];
  text?: string;
  format?: 'inline' | 'dialogue' | 'structured';
}
```

- [ ] **Step 2: Request formatted transcript**

Update `frontend/src/services/api.ts` `getTranscript` to request formatted mode:

```ts
getTranscript(videoId: string) {
  return http.get(`videos/${videoId}/transcript`, { searchParams: { mode: 'formatted' } }).json<TranscriptResponse>();
}
```

- [ ] **Step 3: Render blocks before fallback turns**

In `frontend/src/routes/VideoPage.tsx`, derive:

```ts
const formattedBlocks = transcript?.blocks ?? [];
const hasFormattedBlocks = formattedBlocks.length > 0;
```

Render blocks with click-to-seek:

```tsx
{hasFormattedBlocks ? (
  <div className="surface-card space-y-6" role="list" aria-label="Formatted transcript paragraphs">
    {formattedBlocks.map((block) => (
      <div
        key={block.block_index}
        id={`block-${block.block_index}`}
        className={block.speaker_label ? 'grid gap-3 sm:grid-cols-[8rem_1fr]' : 'block'}
        role="listitem"
      >
        {block.speaker_label && <div className="font-semibold text-ink">{block.speaker_label}:</div>}
        <button
          type="button"
          onClick={() => jumpTo(block.start_ms)}
          className="w-full cursor-pointer rounded px-1 text-left text-lg leading-8 text-ink transition-colors hover:bg-surface-muted focus:bg-surface-muted"
          aria-label={`Play paragraph from ${msToHms(block.start_ms)}`}
        >
          {block.text}
        </button>
      </div>
    ))}
  </div>
) : (
  /* keep existing transcriptTurns fallback */
)}
```

- [ ] **Step 4: Preserve search match navigation**

When `gotoMatch()` finds a segment id, keep scrolling to `seg-${segId}` for fallback. For formatted blocks, find the first block containing `segId - 1`:

```ts
const block = formattedBlocks.find((candidate) => candidate.segment_ids.includes(segId - 1));
const el = block ? document.getElementById(`block-${block.block_index}`) : document.getElementById(`seg-${segId}`);
```

- [ ] **Step 5: Build frontend**

Run: `npm run build` from `frontend/`.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/services/api.ts frontend/src/routes/VideoPage.tsx
git commit -m "Render persisted transcript formatting blocks"
```

---

### Task 6: Backfill and verification

**Files:**
- Create: `scripts/backfill_transcript_blocks.py`
- Test manually against local DB.

- [ ] **Step 1: Add backfill script**

Create `scripts/backfill_transcript_blocks.py`:

```python
from __future__ import annotations

from sqlalchemy import create_engine, text

from app import crud
from app.settings import settings
from app.transcripts.blocks import build_transcript_blocks
from app.transcripts.service import TranscriptPresentationService


def main() -> None:
    engine = create_engine(settings.DATABASE_URL)
    service = TranscriptPresentationService()
    with engine.begin() as conn:
        videos = conn.execute(
            text(
                """
                SELECT DISTINCT video_id
                FROM segments
                WHERE video_id IS NOT NULL
                ORDER BY video_id
                """
            )
        ).all()
        for (video_id,) in videos:
            rows = conn.execute(
                text(
                    """
                    SELECT start_ms, end_ms, text, speaker_label
                    FROM segments
                    WHERE video_id = :video_id
                    ORDER BY start_ms
                    """
                ),
                {"video_id": str(video_id)},
            ).all()
            segments = [service.from_db_row(row) for row in rows]
            blocks = build_transcript_blocks(segments)
            crud.replace_transcript_blocks(conn, video_id, blocks)
            print(f"{video_id}: wrote {len(blocks)} blocks")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run checks**

Run:

```bash
pytest tests/test_transcript_blocks.py tests/test_transcript_presentation.py -q
cd frontend && npm run build
```

Expected: all pass.

- [ ] **Step 3: Run backfill in development**

Run: `python scripts/backfill_transcript_blocks.py`

Expected: prints one line per video, no exceptions.

- [ ] **Step 4: Manually verify transcript page**

Open a completed video transcript page and verify:

- Search/export controls are at the top.
- Video remains sticky on large screens.
- Transcript shows paragraphs or speaker turns without timestamps.
- Paragraph text has normalized whitespace and punctuation.
- Clicking a paragraph starts the video at that paragraph’s `start_ms`.
- Search result navigation scrolls to the related block.

- [ ] **Step 5: Commit**

```bash
git add scripts/backfill_transcript_blocks.py
git commit -m "Add transcript block backfill script"
```

---

## Self-review

- Spec coverage: This plan adds a deterministic, non-LLM formatting stage with punctuation, whitespace cleanup, paragraph/speaker-turn blocks, persistent storage, API exposure, frontend rendering, and backfill.
- No LLM pass is included.
- Raw segments stay immutable.
- Timestamp mapping is preserved through `segment_ids`, `start_ms`, and `end_ms`.
- No placeholder steps remain; every code-changing task includes concrete code and verification commands.
