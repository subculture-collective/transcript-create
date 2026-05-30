# Transcript Source Comparison Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Recommended path:
> dispatch a fresh subagent per task, review each result with `review-quality`,
> then continue. For complex multi-agent splits, use
> `parallel-feature-development`, `team-composition-patterns`, and
> `team-communication-protocols`. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Build a standalone tool that compares Whisper transcripts against YouTube captions so we can decide whether to use YouTube-first, Whisper-first, or a hybrid fallback policy for the 3k-video backlog.

**Architecture:** Add pure comparison functions in `app/transcripts/comparison.py` that normalize text, bucket segments by time window, compute coverage/similarity/missing-span metrics, and render report payloads. Add `scripts/compare_transcript_sources.py` as a DB-backed CLI that samples videos with both sources, uses existing `crud.list_segments()` and `crud.list_youtube_segments()`, and writes JSON plus Markdown reports under `reports/`.

**Tech Stack:** Python, argparse, SQLAlchemy, existing `app.settings.settings`, existing `TranscriptSegment` and YouTube row adapters, JSON/Markdown output, pytest-compatible unit tests.

---

## Confirmed Decisions

- First output should be both JSON and Markdown.
- No schema/API/frontend changes.
- Plan persisted in repo as an openspec-style plan under `docs/superpowers/plans/`.
- The tool should support sampling to quickly answer whether YouTube captions are good enough to use immediately.

## Files

- Create: `app/transcripts/comparison.py` — pure metric logic and report rendering.
- Create: `scripts/compare_transcript_sources.py` — CLI/DB sampling/report writing.
- Create: `tests/test_transcript_source_comparison.py` — deterministic tests for metrics and report shape.

## Metrics

- `coverage_ratio`: number of non-empty buckets divided by total buckets.
- `missing_bucket_count`: buckets where one source has text and the other does not.
- `token_jaccard`: set-token overlap for aligned text.
- `length_ratio`: shorter token count divided by longer token count.
- `recommendation`: one of `youtube_first`, `whisper_first`, `hybrid`, or `needs_review`.

## Task 1: Pure Comparison Logic

**Files:**
- Create: `app/transcripts/comparison.py`
- Create: `tests/test_transcript_source_comparison.py`

- [ ] **Step 1: Write tests**

Add tests covering:

```python
from app.transcripts.comparison import compare_sources
from app.transcripts.types import TranscriptSegment


def test_compare_sources_detects_youtube_gap_fill():
    whisper = [TranscriptSegment(start_ms=0, end_ms=5000, text="hello world", speaker_label=None)]
    youtube = [
        TranscriptSegment(start_ms=0, end_ms=5000, text="hello world", speaker_label=None),
        TranscriptSegment(start_ms=5000, end_ms=10000, text="extra caption text", speaker_label=None),
    ]

    result = compare_sources("video-1", whisper, youtube, bucket_ms=5000)

    assert result["video_id"] == "video-1"
    assert result["whisper"]["coverage_ratio"] == 0.5
    assert result["youtube"]["coverage_ratio"] == 1.0
    assert result["youtube_only_bucket_count"] == 1
    assert result["recommendation"] in {"youtube_first", "hybrid"}


def test_compare_sources_recommends_hybrid_for_complementary_gaps():
    whisper = [TranscriptSegment(start_ms=0, end_ms=5000, text="first part", speaker_label=None)]
    youtube = [TranscriptSegment(start_ms=5000, end_ms=10000, text="second part", speaker_label=None)]

    result = compare_sources("video-2", whisper, youtube, bucket_ms=5000)

    assert result["whisper_only_bucket_count"] == 1
    assert result["youtube_only_bucket_count"] == 1
    assert result["recommendation"] == "hybrid"
```

- [ ] **Step 2: Implement `app/transcripts/comparison.py`**

Implement:
- `normalize_text(text: str) -> str`
- `tokenize(text: str) -> list[str]`
- `bucket_segments(segments: Sequence[TranscriptSegment], bucket_ms: int) -> dict[int, str]`
- `jaccard_tokens(left: str, right: str) -> float`
- `compare_sources(video_id: str, whisper_segments, youtube_segments, bucket_ms=10000) -> dict`
- `render_markdown_report(report: dict) -> str`

Recommendation rules:
- `hybrid` if both `whisper_only_bucket_count > 0` and `youtube_only_bucket_count > 0`.
- `youtube_first` if YouTube coverage is at least 10 percentage points higher than Whisper and average similarity is at least `0.55` or Whisper coverage is below `0.6`.
- `whisper_first` if Whisper coverage is at least 10 percentage points higher than YouTube and average similarity is at least `0.55`.
- otherwise `needs_review`.

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_transcript_source_comparison.py -q
```

Expected: PASS. If local pytest wrapper fails, run syntax checks and report the exact error.

## Task 2: DB-backed CLI Report Tool

**Files:**
- Create: `scripts/compare_transcript_sources.py`
- Modify: `tests/test_transcript_source_comparison.py`

- [ ] **Step 1: Implement CLI script**

Script requirements:
- `--limit` default `100`
- `--bucket-ms` default `10000`
- `--output-dir` default `reports`
- `--json-output` optional exact path
- `--markdown-output` optional exact path
- Query candidates that have both Whisper segments and YouTube captions.
- Convert Whisper rows from `crud.list_segments()` to `TranscriptSegment`.
- Convert YouTube rows with `youtube_rows_to_segments()`.
- Write aggregate JSON and Markdown.

Candidate SQL:

```sql
SELECT v.id, v.youtube_id, v.title
FROM videos v
WHERE EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id)
  AND EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id)
ORDER BY COALESCE(v.uploaded_at, v.created_at) DESC, v.created_at DESC
LIMIT :limit
```

- [ ] **Step 2: Add tests for report rendering**

Extend tests with a report rendering test:

```python
from app.transcripts.comparison import render_markdown_report


def test_render_markdown_report_includes_recommendation_counts():
    report = {
        "summary": {"video_count": 1, "recommendations": {"hybrid": 1}},
        "videos": [{"video_id": "video-1", "title": "Example", "recommendation": "hybrid"}],
    }

    markdown = render_markdown_report(report)

    assert "# Transcript Source Comparison" in markdown
    assert "hybrid" in markdown
    assert "Example" in markdown
```

- [ ] **Step 3: Verify CLI syntax/help**

Run:

```bash
python3 -m py_compile app/transcripts/comparison.py scripts/compare_transcript_sources.py tests/test_transcript_source_comparison.py
python3 scripts/compare_transcript_sources.py --help
```

Expected: syntax passes; help prints options. If `sqlalchemy` is unavailable locally, syntax check is sufficient and Docker command should be used.

## Task 3: Docker/Usage Verification

**Files:**
- No code changes required.

- [ ] **Step 1: Run inside Docker when DB is available**

Use GTX1080 compose stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.gtx1080.yml run --rm api \
  python3 scripts/compare_transcript_sources.py --limit 100 --bucket-ms 10000
```

Expected outputs:
- `reports/transcript-source-comparison-<timestamp>.json`
- `reports/transcript-source-comparison-<timestamp>.md`

- [ ] **Step 2: Decision use**

Interpret recommendations:
- many `youtube_first`: use YouTube captions immediately for search/browse and defer Whisper.
- many `hybrid`: build a merged transcript read model with source provenance.
- many `whisper_first`: keep Whisper as primary and use YouTube captions for fast placeholders only.
- many `needs_review`: inspect sample Markdown rows before automating policy.

---

## Self-Review

- Spec coverage: compares YouTube vs Whisper, supports backlog decision, emits JSON and Markdown.
- Placeholder scan: no incomplete placeholders.
- Type consistency: all pure logic consumes existing `TranscriptSegment`; YouTube rows use existing adapter.
