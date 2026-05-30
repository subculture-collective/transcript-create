# YouTube Formatting and Stream Library Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Recommended path:
> dispatch a fresh subagent per task, review each result with `review-quality`,
> then continue. For complex multi-agent splits, use
> `parallel-feature-development`, `team-composition-patterns`, and
> `team-communication-protocols`. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Format YouTube/native captions with the same deterministic transcript cleanup pipeline used for Whisper output, and add a full stream library UI with search, date filters, pagination, metadata, and transcript availability.

**Architecture:** Keep Whisper as the primary video-page transcript. Add reusable formatting helpers that convert YouTube caption rows into `TranscriptSegment` inputs and return formatted blocks/text without introducing an LLM pass. Extend the existing `/videos` API into a richer library endpoint by adding filters and metadata from the existing `videos` table, then build a `/streams` frontend route that consumes it.

**Tech Stack:** Python, FastAPI, Pydantic, SQLAlchemy text queries, PostgreSQL, existing `TranscriptFormatter`/`build_transcript_blocks`, React 19, Vite, TypeScript, Tailwind v4 design-system utilities, Vitest.

---

## Confirmed Product Decisions

- Whisper remains the main transcript on `frontend/src/routes/VideoPage.tsx`.
- YouTube/native captions should be formatted for backend API/export/alternate use, not automatically replace Whisper.
- Stream library should be a full UI, not a tiny filter patch.
- Planning artifacts are persisted in the repo under `docs/superpowers/plans/`.

## Existing Code Map

- `app/routes/videos.py` — owns `/videos`, `/videos/{video_id}`, `/videos/{video_id}/transcript`, and `/videos/{video_id}/youtube-transcript`.
- `app/routes/exports.py` — owns YouTube caption exports: `.srt`, `.vtt`, `.json`.
- `app/crud.py` — has `list_videos()`, `list_completed_videos()`, `get_youtube_transcript()`, `list_youtube_segments()`, `replace_transcript_blocks()`, `list_transcript_blocks()`.
- `app/schemas.py` — has `VideoInfo`, `PaginatedVideos`, `YouTubeTranscriptResponse`, `YTSegment`, `TranscriptBlockResponse`, `FormattedTranscriptResponse`.
- `app/transcripts/blocks.py` — has `FORMATTER_VERSION = "rule-v3"`, `TranscriptBlock`, `build_transcript_blocks()`.
- `app/transcripts/types.py` — has `TranscriptSegment`.
- `worker/formatter.py` — has deterministic cleanup and hallucination filtering, including `You` and repetitive music/silence gibberish filters.
- `frontend/src/services/api.ts` — has `getTranscript()`, `getVideo()`, `listRecentVideos()`.
- `frontend/src/types/api.ts` — has `Segment`, `TranscriptBlock`, `TranscriptResponse`, `VideoInfo`.
- `frontend/src/main.tsx` — route table currently has `/`, `/v/:videoId`, `/favorites`, `/pricing`, `/upgrade`, `/admin/*`.
- `frontend/src/routes/AppLayout.tsx` — top navigation currently has Search/Favorites/Pricing.
- `sql/schema.sql` — `videos` already includes `created_at`, `updated_at`, `uploaded_at`, `channel_name`, `language`, `category`, `state`, `caption_ingest_state`, `diarization_state`, and indexes including `videos_uploaded_at_idx`.

---

### Task 1: Shared YouTube Caption Formatting Helper

**Files:**
- Create: `app/transcripts/youtube_formatting.py`
- Test: `tests/test_youtube_caption_formatting.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_youtube_caption_formatting.py`:

```python
from app.transcripts.youtube_formatting import build_youtube_caption_blocks, format_youtube_caption_text


def test_build_youtube_caption_blocks_filters_music_hallucinations():
    rows = [
        (0, 1000, "నికికికికికికికికికికికికికికికికికికికికికికికి"),
        (1000, 2000, "You"),
        (2000, 3000, "Actual spoken caption"),
        (3000, 4000, "continues here"),
    ]

    blocks = build_youtube_caption_blocks(rows)

    assert len(blocks) == 1
    assert blocks[0].block_index == 0
    assert blocks[0].start_ms == 2000
    assert blocks[0].end_ms == 4000
    assert blocks[0].speaker_label is None
    assert blocks[0].kind == "paragraph"
    assert blocks[0].segment_ids == [2, 3]
    assert "Actual spoken caption" in blocks[0].text
    assert "continues here" in blocks[0].text
    assert "నికికి" not in blocks[0].text
    assert blocks[0].text != "You."


def test_format_youtube_caption_text_returns_paragraph_text():
    rows = [
        (0, 1000, "First caption sentence"),
        (1000, 1500, "second caption sentence"),
        (4000, 5000, "New paragraph starts"),
    ]

    text = format_youtube_caption_text(rows)

    assert "First caption sentence" in text
    assert "second caption sentence" in text
    assert "\n\n" in text
    assert "New paragraph starts" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_youtube_caption_formatting.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.transcripts.youtube_formatting'`.

- [ ] **Step 3: Implement helper**

Create `app/transcripts/youtube_formatting.py`:

```python
from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.transcripts.blocks import TranscriptBlock, build_transcript_blocks
from app.transcripts.types import TranscriptSegment


YouTubeCaptionRow = tuple[int, int, str]


def youtube_rows_to_segments(rows: Iterable[YouTubeCaptionRow]) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            start_ms=int(start_ms),
            end_ms=int(end_ms),
            text=str(text or ""),
            speaker_label=None,
        )
        for start_ms, end_ms, text in rows
    ]


def build_youtube_caption_blocks(rows: Sequence[YouTubeCaptionRow]) -> list[TranscriptBlock]:
    return build_transcript_blocks(youtube_rows_to_segments(rows))


def format_youtube_caption_text(rows: Sequence[YouTubeCaptionRow]) -> str:
    blocks = build_youtube_caption_blocks(rows)
    return "\n\n".join(block.text for block in blocks if block.text.strip())
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_youtube_caption_formatting.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Only commit if explicitly authorized by the user. If authorized:

```bash
git add app/transcripts/youtube_formatting.py tests/test_youtube_caption_formatting.py
git commit -m "feat: format youtube captions with transcript pipeline"
```

---

### Task 2: Formatted YouTube Caption API Response

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/routes/videos.py`
- Test: `tests/test_routes_videos.py`

- [ ] **Step 1: Write the failing route test**

Append to `tests/test_routes_videos.py`:

```python
from unittest.mock import Mock
import uuid

from app.routes.videos import get_youtube_transcript


def test_youtube_transcript_formatted_mode_returns_blocks(monkeypatch):
    video_id = uuid.uuid4()
    db = Mock()

    monkeypatch.setattr("app.routes.videos.crud.get_video", lambda db_arg, video_id_arg: {"id": video_id})
    monkeypatch.setattr(
        "app.routes.videos.crud.get_youtube_transcript",
        lambda db_arg, video_id_arg: {"id": uuid.uuid4(), "language": "en", "kind": "asr", "full_text": "raw full text"},
    )
    monkeypatch.setattr(
        "app.routes.videos.crud.list_youtube_segments",
        lambda db_arg, transcript_id: [
            (0, 1000, "You"),
            (1000, 2000, "Actual caption"),
            (2000, 3000, "continues"),
        ],
    )

    response = get_youtube_transcript(video_id=video_id, mode="formatted", db=db)

    assert response.video_id == video_id
    assert response.language == "en"
    assert response.kind == "asr"
    assert len(response.segments) == 3
    assert response.full_text == "Actual caption continues."
    assert len(response.blocks) == 1
    assert response.blocks[0].segment_ids == [1, 2]
    assert response.blocks[0].text == "Actual caption continues."
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_routes_videos.py::test_youtube_transcript_formatted_mode_returns_blocks -q
```

Expected: FAIL because `get_youtube_transcript()` does not accept `mode` and `YouTubeTranscriptResponse` has no `blocks`.

- [ ] **Step 3: Extend schema**

Modify `app/schemas.py` `YouTubeTranscriptResponse` so it includes optional formatted blocks:

```python
class YouTubeTranscriptResponse(BaseModel):
    """YouTube native captions for a video."""

    video_id: uuid.UUID = Field(..., description="Unique identifier for the video")
    language: Optional[str] = Field(None, description="Caption language")
    kind: Optional[str] = Field(None, description="Caption kind, e.g. asr for auto-generated captions")
    full_text: Optional[str] = Field(None, description="Full caption text, formatted when mode=formatted")
    segments: List[YTSegment] = Field(..., description="YouTube caption segments")
    blocks: List[TranscriptBlockResponse] = Field(default_factory=list, description="Formatted caption blocks")
```

- [ ] **Step 4: Extend route**

Modify `app/routes/videos.py` imports:

```python
from ..transcripts.youtube_formatting import build_youtube_caption_blocks, format_youtube_caption_text
```

Change route signature:

```python
def get_youtube_transcript(
    video_id: uuid.UUID,
    mode: Literal["raw", "formatted"] = Query("raw", description="Caption mode: raw or formatted"),
    db=Depends(get_db),
):
```

Replace return body with:

```python
    segs = crud.list_youtube_segments(db, yt["id"])
    segments = [YTSegment(start_ms=r[0], end_ms=r[1], text=r[2]) for r in segs]
    blocks = []
    full_text = yt.get("full_text")

    if mode == "formatted":
        caption_blocks = build_youtube_caption_blocks([(r[0], r[1], r[2]) for r in segs])
        blocks = [
            TranscriptBlockResponse(
                block_index=b.block_index,
                start_ms=b.start_ms,
                end_ms=b.end_ms,
                speaker_label=b.speaker_label,
                text=b.text,
                segment_ids=b.segment_ids,
                kind=b.kind,
                formatter_version=b.formatter_version,
            )
            for b in caption_blocks
        ]
        full_text = format_youtube_caption_text([(r[0], r[1], r[2]) for r in segs])

    return YouTubeTranscriptResponse(
        video_id=video_id,
        language=yt.get("language"),
        kind=yt.get("kind"),
        full_text=full_text,
        segments=segments,
        blocks=blocks,
    )
```

- [ ] **Step 5: Run route test**

Run:

```bash
pytest tests/test_routes_videos.py::test_youtube_transcript_formatted_mode_returns_blocks -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Only commit if explicitly authorized by the user. If authorized:

```bash
git add app/schemas.py app/routes/videos.py tests/test_routes_videos.py
git commit -m "feat: expose formatted youtube captions"
```

---

### Task 3: Format YouTube Caption Exports

**Files:**
- Modify: `app/routes/exports.py`
- Test: `tests/test_exports.py` or existing export route test file if one exists

- [ ] **Step 1: Locate export tests**

Run:

```bash
python - <<'PY'
from pathlib import Path
for path in Path('tests').rglob('test_*.py'):
    text = path.read_text(errors='ignore')
    if 'youtube-transcript.srt' in text or 'get_youtube_transcript_srt' in text:
        print(path)
PY
```

Expected: print an existing export test path or no output.

- [ ] **Step 2: Write failing tests**

If no export test file exists, create `tests/test_youtube_caption_exports.py`:

```python
import uuid
from unittest.mock import Mock

from app.routes.exports import get_youtube_transcript_json


class RequestStub:
    cookies = {}
    headers = {}
    client = None


def test_youtube_json_export_uses_formatted_caption_text(monkeypatch):
    video_id = uuid.uuid4()
    transcript_id = uuid.uuid4()
    db = Mock()

    monkeypatch.setattr(
        "app.routes.exports.get_user_from_session",
        lambda db_arg, token: {"id": uuid.uuid4(), "plan": "pro"},
    )
    monkeypatch.setattr("app.routes.exports.get_session_token", lambda request: "session")
    monkeypatch.setattr("app.routes.exports._export_allowed_or_402", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.routes.exports._log_export", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.routes.exports.crud.get_youtube_transcript",
        lambda db_arg, video_id_arg: {"id": transcript_id, "language": "en", "kind": "asr"},
    )
    monkeypatch.setattr(
        "app.routes.exports.crud.list_youtube_segments",
        lambda db_arg, transcript_id_arg: [
            (0, 1000, "You"),
            (1000, 2000, "Actual caption"),
            (2000, 3000, "continues"),
        ],
    )

    response = get_youtube_transcript_json(video_id, RequestStub(), db)
    body = response.body.decode("utf-8")

    assert "Actual caption continues." in body
    assert "You" not in body
```

- [ ] **Step 3: Run test to verify it fails**

Run the chosen test file:

```bash
pytest tests/test_youtube_caption_exports.py -q
```

Expected: FAIL because current JSON export returns raw YouTube segments.

- [ ] **Step 4: Implement formatted export helpers in route**

Modify `app/routes/exports.py` imports:

```python
from ..transcripts.youtube_formatting import build_youtube_caption_blocks, format_youtube_caption_text
```

In `get_youtube_transcript_json()`, replace raw payload creation:

```python
    rows = [(r[0], r[1], r[2]) for r in segs]
    blocks = build_youtube_caption_blocks(rows)
    payload = {
        "video_id": str(video_id),
        "language": yt.get("language"),
        "kind": yt.get("kind"),
        "full_text": format_youtube_caption_text(rows),
        "blocks": [
            {
                "block_index": block.block_index,
                "start_ms": block.start_ms,
                "end_ms": block.end_ms,
                "speaker_label": block.speaker_label,
                "text": block.text,
                "segment_ids": block.segment_ids,
                "kind": block.kind,
                "formatter_version": block.formatter_version,
            }
            for block in blocks
        ],
        "segments": [{"start_ms": r[0], "end_ms": r[1], "text": r[2]} for r in segs],
    }
```

For `.srt` and `.vtt`, keep valid subtitle timing but format each caption text through existing deterministic cleanup by deriving blocks and writing each block as a subtitle cue:

```python
    blocks = build_youtube_caption_blocks([(r[0], r[1], r[2]) for r in segs])
```

Then iterate `blocks` instead of `segs` for SRT/VTT body generation. Use `block.start_ms`, `block.end_ms`, `block.text`.

- [ ] **Step 5: Run export test**

Run:

```bash
pytest tests/test_youtube_caption_exports.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Only commit if explicitly authorized by the user. If authorized:

```bash
git add app/routes/exports.py tests/test_youtube_caption_exports.py
git commit -m "feat: format youtube caption exports"
```

---

### Task 4: Rich Video Library API

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/crud.py`
- Modify: `app/routes/videos.py`
- Test: `tests/test_routes_videos.py`

- [ ] **Step 1: Write route tests for filters and metadata**

Append to `tests/test_routes_videos.py`:

```python
from datetime import datetime, timezone


def test_list_videos_accepts_library_filters(monkeypatch):
    captured = {}

    def fake_list_stream_library(db, **kwargs):
        captured.update(kwargs)
        return [
            {
                "id": uuid.uuid4(),
                "youtube_id": "abc123",
                "title": "Stream title",
                "duration_seconds": 3600,
                "state": "completed",
                "caption_ingest_state": "completed",
                "diarization_state": "completed",
                "uploaded_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
                "created_at": datetime(2026, 5, 2, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 5, 3, tzinfo=timezone.utc),
                "channel_name": "Channel",
                "language": "en",
                "category": "stream",
                "has_whisper_transcript": True,
                "has_youtube_transcript": True,
            }
        ]

    monkeypatch.setattr("app.routes.videos.crud.list_stream_library", fake_list_stream_library)
    monkeypatch.setattr("app.routes.videos.crud.count_stream_library", lambda db, **kwargs: 1)

    response = list_videos(
        limit=25,
        offset=50,
        completed_only=True,
        q="hasan",
        date_field="uploaded_at",
        date_from="2026-05-01",
        date_to="2026-05-31",
        db=object(),
    )

    assert captured["limit"] == 25
    assert captured["offset"] == 50
    assert captured["completed_only"] is True
    assert captured["q"] == "hasan"
    assert captured["date_field"] == "uploaded_at"
    assert captured["date_from"] == "2026-05-01"
    assert captured["date_to"] == "2026-05-31"
    assert response.items[0].youtube_id == "abc123"
    assert response.items[0].has_whisper_transcript is True
    assert response.page_info.total_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_routes_videos.py::test_list_videos_accepts_library_filters -q
```

Expected: FAIL because filters and `list_stream_library()` do not exist.

- [ ] **Step 3: Extend schemas**

Modify `app/schemas.py` `VideoInfo`:

```python
class VideoInfo(BaseModel):
    """Basic information about a video."""

    id: uuid.UUID = Field(..., description="Unique identifier for the video")
    youtube_id: str = Field(..., description="YouTube video ID")
    title: Optional[str] = Field(None, description="Video title")
    duration_seconds: Optional[int] = Field(None, description="Video duration in seconds", ge=0)
    state: Optional[str] = Field(None, description="Processing state")
    caption_ingest_state: Optional[str] = Field(None, description="YouTube caption ingest state")
    diarization_state: Optional[str] = Field(None, description="Diarization state")
    uploaded_at: Optional[datetime] = Field(None, description="YouTube upload or stream publish time")
    created_at: Optional[datetime] = Field(None, description="Local row creation time")
    updated_at: Optional[datetime] = Field(None, description="Local row update time")
    channel_name: Optional[str] = Field(None, description="YouTube channel name")
    language: Optional[str] = Field(None, description="Detected or declared language")
    category: Optional[str] = Field(None, description="Video category")
    has_whisper_transcript: bool = Field(False, description="Whether Whisper transcript segments exist")
    has_youtube_transcript: bool = Field(False, description="Whether YouTube captions exist")
```

- [ ] **Step 4: Add CRUD helpers**

Add to `app/crud.py`:

```python
def _stream_library_where(completed_only: bool, q: str | None, date_field: str, date_from: str | None, date_to: str | None):
    clauses = []
    params = {}
    if completed_only:
        clauses.append("v.state = 'completed'")
    if q:
        clauses.append("v.title ILIKE :q")
        params["q"] = f"%{q}%"
    if date_field not in {"uploaded_at", "created_at", "updated_at"}:
        date_field = "uploaded_at"
    if date_from:
        clauses.append(f"v.{date_field} >= CAST(:date_from AS timestamptz)")
        params["date_from"] = date_from
    if date_to:
        clauses.append(f"v.{date_field} < CAST(:date_to AS timestamptz) + INTERVAL '1 day'")
        params["date_to"] = date_to
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where_sql, params


@_retry_on_transient_error
def list_stream_library(
    db,
    limit: int = 50,
    offset: int = 0,
    completed_only: bool = False,
    q: str | None = None,
    date_field: str = "uploaded_at",
    date_from: str | None = None,
    date_to: str | None = None,
):
    where_sql, params = _stream_library_where(completed_only, q, date_field, date_from, date_to)
    params.update({"limit": limit, "offset": offset})
    return (
        db.execute(
            text(
                f"""
                SELECT v.id, v.youtube_id, v.title, v.duration_seconds, v.state,
                       v.caption_ingest_state, v.diarization_state, v.uploaded_at,
                       v.created_at, v.updated_at, v.channel_name, v.language, v.category,
                       EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id) AS has_whisper_transcript,
                       EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id) AS has_youtube_transcript
                FROM videos v
                {where_sql}
                ORDER BY COALESCE(v.uploaded_at, v.created_at) DESC, v.created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
        .mappings()
        .all()
    )


@_retry_on_transient_error
def count_stream_library(
    db,
    completed_only: bool = False,
    q: str | None = None,
    date_field: str = "uploaded_at",
    date_from: str | None = None,
    date_to: str | None = None,
):
    where_sql, params = _stream_library_where(completed_only, q, date_field, date_from, date_to)
    return db.execute(text(f"SELECT COUNT(*) FROM videos v {where_sql}"), params).scalar_one()
```

- [ ] **Step 5: Update route to return `PaginatedVideos`**

Modify `app/routes/videos.py` imports to include `PaginatedVideos` and `PageInfo`.

Change route decorator response model:

```python
response_model=PaginatedVideos
```

Change signature:

```python
def list_videos(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of videos to return"),
    offset: int = Query(0, ge=0, description="Number of videos to skip for pagination"),
    completed_only: bool = Query(False, description="Only include completed videos"),
    q: str | None = Query(None, min_length=1, max_length=200, description="Filter by title"),
    date_field: Literal["uploaded_at", "created_at", "updated_at"] = Query("uploaded_at"),
    date_from: str | None = Query(None, description="Inclusive YYYY-MM-DD date lower bound"),
    date_to: str | None = Query(None, description="Inclusive YYYY-MM-DD date upper bound"),
    db=Depends(get_db),
):
```

Return:

```python
    rows = crud.list_stream_library(
        db,
        limit=limit,
        offset=offset,
        completed_only=completed_only,
        q=q,
        date_field=date_field,
        date_from=date_from,
        date_to=date_to,
    )
    total = crud.count_stream_library(
        db,
        completed_only=completed_only,
        q=q,
        date_field=date_field,
        date_from=date_from,
        date_to=date_to,
    )
    items = [VideoInfo(**dict(r)) for r in rows]
    return PaginatedVideos(
        items=items,
        page_info=PageInfo(
            has_next_page=offset + limit < total,
            has_previous_page=offset > 0,
            next_cursor=str(offset + limit) if offset + limit < total else None,
            previous_cursor=str(max(0, offset - limit)) if offset > 0 else None,
            total_count=total,
        ),
    )
```

- [ ] **Step 6: Run route test**

Run:

```bash
pytest tests/test_routes_videos.py::test_list_videos_accepts_library_filters -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Only commit if explicitly authorized by the user. If authorized:

```bash
git add app/schemas.py app/crud.py app/routes/videos.py tests/test_routes_videos.py
git commit -m "feat: add stream library API filters"
```

---

### Task 5: Frontend API Types and Client for Stream Library

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/services/api.ts`
- Test: `frontend/src/tests/api.test.ts`

- [ ] **Step 1: Write failing API client test**

Add to `frontend/src/tests/api.test.ts`:

```ts
it('lists stream library with filters', async () => {
  getMock.mockReturnValueOnce({
    json: vi.fn().mockResolvedValue({
      items: [],
      page_info: {
        has_next_page: false,
        has_previous_page: false,
        next_cursor: null,
        previous_cursor: null,
        total_count: 0,
      },
    }),
  })

  await api.listStreamLibrary({
    limit: 24,
    offset: 48,
    completed_only: true,
    q: 'hasan',
    date_field: 'uploaded_at',
    date_from: '2026-05-01',
    date_to: '2026-05-31',
  })

  expect(getMock).toHaveBeenCalledWith('videos', {
    searchParams: {
      limit: '24',
      offset: '48',
      completed_only: 'true',
      q: 'hasan',
      date_field: 'uploaded_at',
      date_from: '2026-05-01',
      date_to: '2026-05-31',
    },
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
npm test -- --run src/tests/api.test.ts
```

Expected: FAIL because `listStreamLibrary` does not exist.

- [ ] **Step 3: Extend frontend types**

Modify `frontend/src/types/api.ts`:

```ts
export interface VideoInfo {
  id: UUID;
  youtube_id: string;
  title?: string | null;
  duration_seconds?: number | null;
  state?: string | null;
  caption_ingest_state?: string | null;
  diarization_state?: string | null;
  uploaded_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  channel_name?: string | null;
  language?: string | null;
  category?: string | null;
  has_whisper_transcript?: boolean;
  has_youtube_transcript?: boolean;
}

export interface PageInfo {
  has_next_page: boolean;
  has_previous_page: boolean;
  next_cursor?: string | null;
  previous_cursor?: string | null;
  total_count?: number | null;
}

export interface PaginatedVideos {
  items: VideoInfo[];
  page_info: PageInfo;
}

export type StreamLibraryFilters = {
  limit?: number;
  offset?: number;
  completed_only?: boolean;
  q?: string;
  date_field?: 'uploaded_at' | 'created_at' | 'updated_at';
  date_from?: string;
  date_to?: string;
};
```

- [ ] **Step 4: Extend frontend API client**

Modify imports in `frontend/src/services/api.ts`:

```ts
import type { PaginatedVideos, SearchResponse, StreamLibraryFilters, TranscriptResponse, VideoInfo } from '../types/api';
```

Add method:

```ts
  async listStreamLibrary(filters: StreamLibraryFilters = {}) {
    const searchParams: Record<string, string> = {
      limit: String(filters.limit ?? 24),
      offset: String(filters.offset ?? 0),
    };
    if (filters.completed_only !== undefined) searchParams.completed_only = String(filters.completed_only);
    if (filters.q) searchParams.q = filters.q;
    if (filters.date_field) searchParams.date_field = filters.date_field;
    if (filters.date_from) searchParams.date_from = filters.date_from;
    if (filters.date_to) searchParams.date_to = filters.date_to;
    return http.get('videos', { searchParams }).json<PaginatedVideos>();
  },
```

Update `listRecentVideos()` to consume paginated response:

```ts
  async listRecentVideos(limit = 12) {
    const page = await api.listStreamLibrary({ completed_only: true, limit });
    return page.items;
  },
```

- [ ] **Step 5: Run API tests**

Run:

```bash
npm test -- --run src/tests/api.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

Only commit if explicitly authorized by the user. If authorized:

```bash
git add frontend/src/types/api.ts frontend/src/services/api.ts frontend/src/tests/api.test.ts
git commit -m "feat: add stream library frontend client"
```

---

### Task 6: Stream Library Route and Navigation

**Files:**
- Create: `frontend/src/routes/StreamsPage.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/routes/AppLayout.tsx`
- Test: `frontend/src/tests/StreamsPage.test.tsx`

- [ ] **Step 1: Write page test**

Create `frontend/src/tests/StreamsPage.test.tsx`:

```tsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import StreamsPage from '../routes/StreamsPage';

vi.mock('../services', async () => {
  const actual = await vi.importActual<typeof import('../services')>('../services');
  return {
    ...actual,
    api: {
      listStreamLibrary: vi.fn().mockResolvedValue({
        items: [
          {
            id: 'video-1',
            youtube_id: 'yt1',
            title: 'May Day Stream',
            duration_seconds: 7200,
            state: 'completed',
            caption_ingest_state: 'completed',
            diarization_state: 'completed',
            uploaded_at: '2026-05-01T12:00:00Z',
            created_at: '2026-05-02T12:00:00Z',
            updated_at: '2026-05-02T12:30:00Z',
            channel_name: 'HasanAbi',
            language: 'en',
            has_whisper_transcript: true,
            has_youtube_transcript: true,
          },
        ],
        page_info: {
          has_next_page: false,
          has_previous_page: false,
          next_cursor: null,
          previous_cursor: null,
          total_count: 1,
        },
      }),
    },
  };
});

describe('StreamsPage', () => {
  it('renders stream cards and filters', async () => {
    render(
      <MemoryRouter>
        <StreamsPage />
      </MemoryRouter>
    );

    expect(screen.getByRole('heading', { name: /streams/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/search streams/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/from date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/to date/i)).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText('May Day Stream')).toBeInTheDocument());
    expect(screen.getByText('HasanAbi')).toBeInTheDocument();
    expect(screen.getByText('Whisper')).toBeInTheDocument();
    expect(screen.getByText('YouTube captions')).toBeInTheDocument();
  });

  it('submits filter controls', async () => {
    const { api } = await import('../services');
    render(
      <MemoryRouter>
        <StreamsPage />
      </MemoryRouter>
    );

    await userEvent.type(screen.getByLabelText(/search streams/i), 'union');
    await userEvent.type(screen.getByLabelText(/from date/i), '2026-05-01');
    await userEvent.click(screen.getByRole('button', { name: /apply filters/i }));

    await waitFor(() => {
      expect(api.listStreamLibrary).toHaveBeenLastCalledWith(
        expect.objectContaining({ q: 'union', date_from: '2026-05-01' })
      );
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
npm test -- --run src/tests/StreamsPage.test.tsx
```

Expected: FAIL because `StreamsPage` does not exist.

- [ ] **Step 3: Create stream library page**

Create `frontend/src/routes/StreamsPage.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../services';
import type { PaginatedVideos, StreamLibraryFilters, VideoInfo } from '../types/api';

function formatDuration(seconds?: number | null) {
  if (!seconds) return 'Unknown duration';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function formatDate(value?: string | null) {
  if (!value) return 'Unknown date';
  return new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric' }).format(new Date(value));
}

function thumbnailUrl(video: VideoInfo) {
  return `https://i.ytimg.com/vi/${video.youtube_id}/hqdefault.jpg`;
}

export default function StreamsPage() {
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState<PaginatedVideos | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const offset = Number(params.get('offset') ?? '0');
  const limit = 24;

  const filters = useMemo<StreamLibraryFilters>(() => ({
    limit,
    offset: Number.isFinite(offset) ? offset : 0,
    completed_only: params.get('completed_only') !== 'false',
    q: params.get('q') || undefined,
    date_field: (params.get('date_field') as StreamLibraryFilters['date_field']) || 'uploaded_at',
    date_from: params.get('date_from') || undefined,
    date_to: params.get('date_to') || undefined,
  }), [limit, offset, params]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.listStreamLibrary(filters)
      .then(setPage)
      .catch(() => setError('Could not load streams.'))
      .finally(() => setLoading(false));
  }, [filters]);

  function applyFilters(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const next = new URLSearchParams();
    const q = String(data.get('q') ?? '').trim();
    const dateFrom = String(data.get('date_from') ?? '').trim();
    const dateTo = String(data.get('date_to') ?? '').trim();
    const dateField = String(data.get('date_field') ?? 'uploaded_at');
    if (q) next.set('q', q);
    if (dateFrom) next.set('date_from', dateFrom);
    if (dateTo) next.set('date_to', dateTo);
    next.set('date_field', dateField);
    next.set('completed_only', data.get('completed_only') === 'on' ? 'true' : 'false');
    setParams(next);
  }

  function goToOffset(nextOffset: number) {
    const next = new URLSearchParams(params);
    next.set('offset', String(Math.max(0, nextOffset)));
    setParams(next);
  }

  return (
    <div className="space-y-6">
      <header className="surface-card space-y-4">
        <div>
          <p className="mb-1 text-sm font-medium uppercase tracking-wide text-subtle">Library</p>
          <h1 className="page-title">Streams</h1>
          <p className="mt-2 max-w-3xl text-muted">Browse processed streams by title and date range.</p>
        </div>
        <form className="grid gap-3 lg:grid-cols-[1fr_auto_auto_auto_auto]" onSubmit={applyFilters}>
          <label className="sr-only" htmlFor="streams-q">Search streams</label>
          <input id="streams-q" name="q" className="form-control" type="search" placeholder="Search streams" defaultValue={params.get('q') ?? ''} aria-label="Search streams" />
          <label className="sr-only" htmlFor="streams-from">From date</label>
          <input id="streams-from" name="date_from" className="form-control" type="date" defaultValue={params.get('date_from') ?? ''} aria-label="From date" />
          <label className="sr-only" htmlFor="streams-to">To date</label>
          <input id="streams-to" name="date_to" className="form-control" type="date" defaultValue={params.get('date_to') ?? ''} aria-label="To date" />
          <select name="date_field" className="form-control" defaultValue={params.get('date_field') ?? 'uploaded_at'} aria-label="Date field">
            <option value="uploaded_at">Published date</option>
            <option value="created_at">Imported date</option>
            <option value="updated_at">Updated date</option>
          </select>
          <label className="flex min-h-[44px] items-center gap-2 text-sm text-muted">
            <input name="completed_only" type="checkbox" defaultChecked={params.get('completed_only') !== 'false'} />
            Completed
          </label>
          <button className="btn-primary" type="submit">Apply filters</button>
        </form>
      </header>

      {loading && <div className="surface-card text-muted" role="status">Loading streams…</div>}
      {error && <div className="alert-warning" role="alert">{error}</div>}

      {!loading && !error && (
        <section className="space-y-4">
          <div className="flex items-center justify-between text-sm text-muted">
            <span>{page?.page_info.total_count ?? 0} streams</span>
            <span>Showing {page?.items.length ?? 0}</span>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {(page?.items ?? []).map((video) => (
              <Link key={video.id} to={`/v/${video.id}`} className="surface-card-compact block overflow-hidden transition hover:border-accent hover:shadow-sm">
                <img src={thumbnailUrl(video)} alt="" className="mb-4 aspect-video w-full rounded-md object-cover" loading="lazy" />
                <div className="space-y-3">
                  <div>
                    <h2 className="line-clamp-2 font-semibold text-ink">{video.title ?? 'Untitled stream'}</h2>
                    <p className="mt-1 text-sm text-muted">{video.channel_name ?? 'Unknown channel'} · {formatDate(video.uploaded_at ?? video.created_at)}</p>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className="rounded-full bg-surface-muted px-2 py-1 text-muted">{formatDuration(video.duration_seconds)}</span>
                    {video.has_whisper_transcript && <span className="badge-success">Whisper</span>}
                    {video.has_youtube_transcript && <span className="badge-warning">YouTube captions</span>}
                    {video.state && <span className="rounded-full bg-surface-muted px-2 py-1 text-muted">{video.state}</span>}
                  </div>
                </div>
              </Link>
            ))}
          </div>
          <div className="flex items-center justify-between">
            <button className="btn-secondary" disabled={!page?.page_info.has_previous_page} onClick={() => goToOffset((filters.offset ?? 0) - limit)}>Previous</button>
            <button className="btn-secondary" disabled={!page?.page_info.has_next_page} onClick={() => goToOffset((filters.offset ?? 0) + limit)}>Next</button>
          </div>
        </section>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Add route and nav**

Modify `frontend/src/main.tsx`:

```tsx
import StreamsPage from './routes/StreamsPage';
```

Add child route:

```tsx
{ path: 'streams', element: <StreamsPage /> },
```

Modify `frontend/src/routes/AppLayout.tsx` desktop nav after Search:

```tsx
<Link to="/streams" className="nav-link">
  Streams
</Link>
```

Modify mobile nav after Search:

```tsx
<Link
  to="/streams"
  className="nav-link block py-2"
  onClick={() => setMobileMenuOpen(false)}
>
  Streams
</Link>
```

- [ ] **Step 5: Run page test**

Run:

```bash
npm test -- --run src/tests/StreamsPage.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Run frontend build**

Run:

```bash
npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit**

Only commit if explicitly authorized by the user. If authorized:

```bash
git add frontend/src/routes/StreamsPage.tsx frontend/src/main.tsx frontend/src/routes/AppLayout.tsx frontend/src/tests/StreamsPage.test.tsx
git commit -m "feat: add stream library page"
```

---

### Task 7: Final Verification and Docker Smoke Test

**Files:**
- No required file edits.

- [ ] **Step 1: Run backend syntax checks**

Run:

```bash
python3 -m py_compile \
  app/transcripts/youtube_formatting.py \
  app/schemas.py \
  app/crud.py \
  app/routes/videos.py \
  app/routes/exports.py \
  tests/test_youtube_caption_formatting.py \
  tests/test_routes_videos.py
```

Expected: no output.

- [ ] **Step 2: Run focused backend tests**

Run:

```bash
pytest tests/test_youtube_caption_formatting.py tests/test_routes_videos.py tests/test_youtube_caption_exports.py -q
```

Expected: PASS. If local dependencies are unavailable, run this inside the Docker API image after build.

- [ ] **Step 3: Run frontend tests**

Run:

```bash
cd frontend && npm test -- --run src/tests/api.test.ts src/tests/StreamsPage.test.tsx src/tests/YouTubePlayer.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 5: Rebuild app image for Docker usage**

For GTX 1080 environment, run:

```bash
docker compose -f docker-compose.yml -f docker-compose.gtx1080.yml build api
docker compose -f docker-compose.yml -f docker-compose.gtx1080.yml up -d api worker
```

Expected: API starts healthy.

- [ ] **Step 6: Smoke test API endpoints**

Use a real completed video ID from `/videos`:

```bash
curl -s 'http://localhost:41177/videos?completed_only=true&limit=1' | python3 -m json.tool
curl -s 'http://localhost:41177/videos/<VIDEO_ID>/youtube-transcript?mode=formatted' | python3 -m json.tool
```

Expected:
- `/videos` returns `items` and `page_info`.
- YouTube formatted response returns `segments`, formatted `full_text`, and `blocks`.

- [ ] **Step 7: Manual UI check**

Open the app and verify:
- `/streams` appears in navigation.
- Search, date range, completed-only, previous/next work.
- Stream cards show thumbnail, title, channel/date, duration, state, Whisper/YouTube badges.
- Clicking a card opens `/v/:videoId`.
- Whisper remains primary on video page.
- YouTube caption exports no longer include filtered music/silence junk.

---

## Self-Review

- Spec coverage: YouTube caption formatting is covered by Tasks 1-3. Full stream library UI and filterable list are covered by Tasks 4-6. Final checks are covered by Task 7.
- Placeholder scan: No `TBD`, `TODO`, `implement later`, `fill in details`, `appropriate error handling`, `Write tests for the above`, or `Similar to Task` placeholders are present.
- Type consistency: Backend uses `TranscriptBlockResponse` for formatted caption blocks; frontend uses `PaginatedVideos`, `VideoInfo`, and `StreamLibraryFilters`; route filters map consistently to CRUD filters.
