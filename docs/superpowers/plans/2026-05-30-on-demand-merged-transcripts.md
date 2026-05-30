# On-Demand Merged Transcripts Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Recommended path:
> dispatch a fresh subagent per task, review each result with `review-quality`,
> then continue. For complex multi-agent splits, use
> `parallel-feature-development`, `team-composition-patterns`, and
> `team-communication-protocols`. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Build an on-demand deterministic merged transcript source that combines Whisper and YouTube captions into one best transcript without adding a migration yet.

**Architecture:** Keep raw Whisper segments and YouTube captions immutable. Add `app/transcripts/merged.py` to align both sources by time windows, select the best text per span, keep Whisper speaker labels when available, and flag high-disagreement blocks as `needs_review`. Wire `source=best` to prefer merged when both sources exist, then fall back to Whisper, then YouTube.

**Tech Stack:** Python, FastAPI, SQLAlchemy text queries, existing transcript block formatter, React/Vite/TypeScript frontend, Vitest.

---

## Scope decisions

- Do not add a migration or persisted merged table in this first pass.
- Build merged transcripts on demand at API/export time.
- Use deterministic rules only; no LLM merge pass.
- Heavy disagreement policy: prefer Whisper text and preserve speaker labels, but mark the merged block metadata with `needs_review`.
- Search indexing of merged text is a later phase; this pass updates API/frontend labels and keeps existing `best` search fallback behavior unless a safe lightweight label change is needed.

## File structure

- Create `app/transcripts/merged.py`: deterministic merge dataclasses and algorithm.
- Create `tests/test_transcript_merge.py`: unit tests for source selection and review flags.
- Modify `app/schemas.py`: allow `source="merged"`; add optional merge metadata fields on transcript block responses.
- Modify `app/routes/videos.py`: build merged formatted/raw transcript when both sources exist and `source=best` or `source=merged`.
- Modify `app/routes/exports.py`: best exports use merged blocks when both sources exist.
- Modify `frontend/src/types/api.ts`: allow `source="merged"`; add optional merge metadata to blocks.
- Modify `frontend/src/routes/VideoPage.tsx`: existing source label should render `Merged transcript` automatically.
- Modify `frontend/src/routes/SearchPage.tsx`: label support for `merged` if the backend returns it later.

---

### Task 1: Deterministic merge module

**Files:**
- Create: `app/transcripts/merged.py`
- Test: `tests/test_transcript_merge.py`

- [ ] **Step 1: Write unit tests for gap fill and disagreement**

```python
from app.transcripts.merged import build_merged_transcript
from app.transcripts.types import TranscriptSegment


def seg(start, end, text, speaker=None):
    return TranscriptSegment(start_ms=start, end_ms=end, text=text, speaker_label=speaker)


def test_merge_uses_youtube_when_whisper_gap_exists():
    result = build_merged_transcript(
        video_id="video-1",
        whisper_segments=[seg(0, 5000, "hello from whisper", "Speaker 1")],
        youtube_segments=[seg(0, 5000, "hello from youtube"), seg(5000, 10000, "youtube-only second span")],
        bucket_ms=5000,
    )

    assert [s.text for s in result.segments] == ["hello from whisper", "youtube-only second span"]
    assert result.blocks[0].primary_source == "whisper"
    assert result.blocks[1].primary_source == "youtube"


def test_merge_prefers_whisper_and_flags_heavy_disagreement():
    result = build_merged_transcript(
        video_id="video-1",
        whisper_segments=[seg(0, 5000, "the policy discussion continues", "Speaker 1")],
        youtube_segments=[seg(0, 5000, "rick astley never gonna give you up")],
        bucket_ms=5000,
    )

    assert result.segments[0].text == "the policy discussion continues"
    assert result.segments[0].speaker_label == "Speaker 1"
    assert result.blocks[0].primary_source == "whisper"
    assert result.blocks[0].needs_review is True
```

- [ ] **Step 2: Implement merge dataclasses and source scoring**

Create `MergedSegment`, `MergedBlock`, and `MergedTranscript` dataclasses. Implement helpers:

```python
def normalize_for_merge(text: str) -> str: ...
def token_similarity(left: str, right: str) -> float: ...
def bucket_by_time(segments: Sequence[TranscriptSegment], bucket_ms: int) -> dict[int, list[TranscriptSegment]]: ...
def build_merged_transcript(video_id, whisper_segments, youtube_segments, bucket_ms=10000) -> MergedTranscript: ...
```

Rules:
- Whisper-only bucket: choose Whisper.
- YouTube-only bucket: choose YouTube.
- Both available and similarity >= `0.35`: choose Whisper, keep speaker labels, reason `whisper_with_youtube_support`.
- Both available and similarity < `0.35`: choose Whisper, keep speaker labels, reason `heavy_disagreement_prefer_whisper`, `needs_review=True`.
- Empty/gibberish output should be filtered by feeding the chosen segments through existing `build_transcript_blocks()`.

- [ ] **Step 3: Run syntax checks**

Run: `python3 -m py_compile app/transcripts/merged.py tests/test_transcript_merge.py`

Expected: no output.

---

### Task 2: API schema and transcript route wiring

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/routes/videos.py`
- Test: `tests/test_routes_videos.py`

- [ ] **Step 1: Extend response types**

Update source literals to allow `merged`. Add optional fields to `TranscriptBlockResponse`:

```python
primary_source: Optional[Literal["whisper", "youtube", "merged"]] = None
supporting_sources: List[Literal["whisper", "youtube"]] = Field(default_factory=list)
needs_review: bool = False
merge_reason: Optional[str] = None
similarity: Optional[float] = None
```

- [ ] **Step 2: Wire `source=merged|best` in `get_transcript()`**

In `app/routes/videos.py`, support `source: Literal["best", "merged", "whisper", "youtube"]`.

Policy:
- `source=merged`: require both sources; if one missing, fall back to existing best policy instead of failing.
- `source=best`: if both sources exist, return merged; if only Whisper, return Whisper; if only YouTube, return YouTube.
- Existing `source=whisper` and `source=youtube` remain explicit.

- [ ] **Step 3: Return merged formatted response**

Convert `MergedTranscript.blocks` into `TranscriptBlockResponse` and return:

```python
FormattedTranscriptResponse(
    video_id=video_id,
    segments=[Segment(...) for merged_segment in merged.segments],
    text="\n\n".join(block.text for block in blocks),
    format="structured",
    cleanup_config=cleanup_config,
    blocks=blocks,
    source="merged",
    source_label="Merged transcript",
)
```

- [ ] **Step 4: Run syntax checks**

Run: `python3 -m py_compile app/schemas.py app/routes/videos.py tests/test_routes_videos.py`

Expected: no output.

---

### Task 3: Best exports use merged output

**Files:**
- Modify: `app/routes/exports.py`
- Test: `tests/test_youtube_caption_exports.py` or add `tests/test_merged_transcript_exports.py`

- [ ] **Step 1: Add export-source loader support**

Update `_load_best_export_source()` so when both Whisper and YouTube exist it builds a merged transcript and returns `source="merged"`, merged cue rows, and merged blocks.

- [ ] **Step 2: Preserve explicit source exports**

Do not change `/youtube-transcript.*`; it remains YouTube-only.
`/transcript.srt`, `/transcript.vtt`, and `/transcript.json` become best/merged exports.
`/transcript.pdf` can remain Whisper-only for this pass because PDF currently depends on speaker/timestamp rendering and paid entitlement.

- [ ] **Step 3: Include provenance in JSON export**

Best JSON export should include:

```json
{
  "video_id": "...",
  "source": "merged",
  "source_label": "Merged transcript",
  "segments": [...],
  "blocks": [...]
}
```

- [ ] **Step 4: Run syntax checks**

Run: `python3 -m py_compile app/routes/exports.py tests/test_merged_transcript_exports.py`

Expected: no output.

---

### Task 4: Frontend contract labels

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/routes/SearchPage.tsx`
- Modify: `frontend/src/routes/VideoPage.tsx`
- Test: `frontend/src/tests/SearchPage.test.tsx`

- [ ] **Step 1: Extend frontend source types**

Allow `source?: 'whisper' | 'youtube' | 'merged'` on transcript responses and search hits.
Add optional block merge metadata fields matching backend schema.

- [ ] **Step 2: Label merged source**

In `SearchPage.tsx`, map hit source to labels:
- `merged` -> `Merged transcript`
- `youtube` -> `YouTube captions`
- default -> `Whisper transcript`

`VideoPage.tsx` already renders `transcript.source_label`; keep that behavior.

- [ ] **Step 3: Run frontend tests/build**

Run: `npm test -- --run src/tests/api.test.ts src/tests/SearchPage.test.tsx && npm run build`

Expected: tests pass and Vite build completes.

---

### Task 5: Verification and smoke checks

**Files:**
- No new files required.

- [ ] **Step 1: Python syntax verification**

Run:

```bash
python3 -m py_compile \
  app/transcripts/merged.py \
  app/schemas.py \
  app/routes/videos.py \
  app/routes/exports.py \
  tests/test_transcript_merge.py
```

Expected: no output.

- [ ] **Step 2: Frontend verification**

Run:

```bash
cd frontend && npm test -- --run src/tests/api.test.ts src/tests/SearchPage.test.tsx && npm run build
```

Expected: tests pass and build succeeds.

- [ ] **Step 3: Docker smoke check when API is available**

After rebuilding/restarting API or mounting source, request a known video with both sources:

```bash
curl -sS "http://localhost:41177/videos/<video_id>/transcript?mode=formatted&source=best" | jq '{source, source_label, block_count: (.blocks | length)}'
```

Expected: `source` is `merged` for a video with both sources, `whisper` for Whisper-only, and `youtube` for YouTube-only.

---

## Acceptance criteria

- `source=best` returns `Merged transcript` when both Whisper and YouTube captions exist.
- The merge is deterministic and does not call an LLM.
- Whisper speaker labels are preserved whenever Whisper text is selected.
- YouTube fills Whisper gaps.
- Heavy disagreement prefers Whisper and marks `needs_review` metadata.
- Explicit YouTube endpoints remain YouTube-only.
- Frontend builds and displays merged source labels without changing the transcript layout.

## Notes

- No commit should be made unless explicitly requested.
- Local pytest may still report `Pytest: No tests collected`; use `python3 -m py_compile` plus frontend Vitest/build as the reliable local checks.
