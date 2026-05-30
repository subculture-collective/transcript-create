# Architecture Deepening Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Recommended path:
> dispatch a fresh subagent per task, review each result with `review-quality`,
> then continue. For complex multi-agent splits, use
> `parallel-feature-development`, `team-composition-patterns`, and
> `team-communication-protocols`. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Turn the transcript platform from route/worker scripts with scattered policy into deep, testable modules with small interfaces around the core product workflow.

**Architecture:** Execute this as eight sequential refactor tracks. Start with the worker/state foundations because staged channel ingestion, captions-first batching, native Whisper, and diarization depend on those contracts. Then extract YouTube, search, transcript presentation, frontend product kernels, schema contracts, and finally auth/billing policy.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy Core, PostgreSQL/Alembic, yt-dlp, faster-whisper, pyannote.audio, React/Vite/TypeScript, Vitest/Testing Library, Docker Compose.

---

## Current Constraints and Safety Notes

- The worker may be intentionally stopped after YouTube rate limiting. Do not resume long-running ingestion unless the task explicitly says to.
- Active staged batch: `channels-20260529-core`. Native Whisper must stay locked until all batch videos have terminal `caption_ingest_state` values.
- Existing command checks that should keep passing:
  - `rtk mypy app worker`
  - `python3 -m compileall -q app worker alembic`
  - `rtk npm run build` from `frontend/`
  - `rtk lint` from `frontend/`
- Avoid changing SaaS billing/auth behavior except in the final auth/billing track.
- Prefer compatibility wrappers during extraction so running jobs and APIs keep working.

---

## File Structure Target

### Worker/Core Workflow

- Create: `worker/state_model.py` — explicit job/video/caption/diarization state policy and legal transitions.
- Create: `worker/repositories.py` — SQL access for jobs, videos, segments, YouTube captions, and diarization queue.
- Create: `worker/video_pipeline.py` — deep module for “advance one video through native transcription.”
- Create: `worker/caption_ingest.py` — deep module for captions-first batch ingestion.
- Modify: `worker/loop.py` — thin orchestration loop using state/repository/services.
- Modify: `worker/pipeline.py` — compatibility wrappers; gradually move logic out.
- Modify tests under `tests/worker/`.

### YouTube Adapter

- Create: `worker/youtube/errors.py` — normalized YouTube error/result types.
- Create: `worker/youtube/yt_dlp_executor.py` — one subprocess boundary for yt-dlp.
- Create: `worker/youtube/service.py` — high-level metadata/caption/audio methods.
- Modify: `worker/audio.py`, `worker/youtube_captions.py`, `worker/youtube_resilience.py` to delegate.
- Test: `tests/worker/test_youtube_service.py`.

### Backend Search and Transcript Presentation

- Create: `app/search/service.py`, `app/search/repositories.py`, `app/search/types.py`.
- Create: `app/transcripts/service.py`, `app/transcripts/types.py`.
- Modify: `app/routes/search.py`, `app/routes/videos.py`, `app/crud.py`.
- Test: `tests/test_search_service.py`, `tests/test_transcript_presentation.py`.

### Schema and Migrations

- Create: `tests/test_schema_contract.py`.
- Modify: `sql/schema.sql`, `alembic/versions/*` only when contract tests expose drift.
- Modify: `.github/workflows/*` later if needed, after local contract tests are stable.

### Frontend Product Kernels

- Create: `frontend/src/features/searchTranscript/`.
- Create: `frontend/src/features/favorites/`.
- Create: `frontend/src/features/entitlements/`.
- Modify: `SearchPage.tsx`, `VideoPage.tsx`, `FavoritesPage.tsx`, `ExportMenu.tsx`.
- Test: feature-level hook/service tests under `frontend/src/tests/`.

### Auth/Billing Policy

- Create: `app/identity/`, `app/billing/` modules.
- Modify: `app/routes/auth.py`, `app/routes/billing.py`, `app/security.py` only behind compatibility wrappers.
- Test: focused policy tests before route rewrites.

---

## Phase 0: Baseline and Guardrails

### Task 0.1: Capture Baseline Health

**Files:**
- Read: existing code only
- Create: `docs/superpowers/plans/2026-05-29-architecture-baseline.md`

- [ ] **Step 1: Record current git and runtime status**

Run:

```bash
git status --short
docker compose -f docker-compose.yml -f docker-compose.gtx1080.yml ps api worker diarization-worker
```

Expected: capture whether worker is stopped/running before refactors.

- [ ] **Step 2: Run baseline checks**

Run:

```bash
rtk mypy app worker
python3 -m compileall -q app worker alembic
cd frontend && rtk npm run build && rtk lint
```

Expected: all pass. If any fail, stop and write the failure into the baseline doc before refactoring.

- [ ] **Step 3: Save baseline note**

Create `docs/superpowers/plans/2026-05-29-architecture-baseline.md`:

```markdown
# Architecture Refactor Baseline

Date: 2026-05-29

## Git Status

Paste `git status --short` here.

## Runtime Status

Paste `docker compose ... ps` here.

## Checks

- `rtk mypy app worker`: PASS/FAIL
- `python3 -m compileall -q app worker alembic`: PASS/FAIL
- `cd frontend && rtk npm run build`: PASS/FAIL
- `cd frontend && rtk lint`: PASS/FAIL

## Notes

- Worker may be stopped because of YouTube cooldown.
- Staged batch `channels-20260529-core` must remain caption-first.
```

- [ ] **Step 4: Commit baseline**

```bash
git add docs/superpowers/plans/2026-05-29-architecture-baseline.md
git commit -m "docs: record architecture refactor baseline"
```

---

## Phase 1: Job/Video/Captions/Diarization State Model

### Task 1.1: Define State Model Boundary Tests

**Files:**
- Create: `tests/worker/test_state_model.py`
- Create later: `worker/state_model.py`

- [ ] **Step 1: Write failing state tests**

Create `tests/worker/test_state_model.py`:

```python
import pytest

from worker.state_model import (
    CaptionIngestState,
    DiarizationState,
    JobState,
    VideoState,
    can_start_native_transcription,
    job_state_from_video_states,
)


def test_job_completes_when_all_videos_completed():
    result = job_state_from_video_states([VideoState.COMPLETED, VideoState.COMPLETED])
    assert result == JobState.COMPLETED


def test_job_fails_when_no_active_videos_and_any_failed():
    result = job_state_from_video_states([VideoState.COMPLETED, VideoState.FAILED])
    assert result == JobState.FAILED


def test_job_keeps_running_with_pending_video():
    result = job_state_from_video_states([VideoState.COMPLETED, VideoState.PENDING])
    assert result == JobState.DOWNLOADING


def test_staged_video_cannot_start_native_until_caption_terminal():
    assert not can_start_native_transcription(
        staged=True,
        own_caption_state=CaptionIngestState.PENDING,
        batch_job_count=3,
        expected_batch_jobs=3,
        batch_has_open_caption_work=True,
    )


def test_staged_video_can_start_native_after_all_captions_terminal():
    assert can_start_native_transcription(
        staged=True,
        own_caption_state=CaptionIngestState.COMPLETED,
        batch_job_count=3,
        expected_batch_jobs=3,
        batch_has_open_caption_work=False,
    )


def test_staged_batch_waits_for_all_expected_jobs():
    assert not can_start_native_transcription(
        staged=True,
        own_caption_state=CaptionIngestState.COMPLETED,
        batch_job_count=2,
        expected_batch_jobs=3,
        batch_has_open_caption_work=False,
    )


def test_diarization_states_include_failed_and_skipped():
    assert DiarizationState.FAILED.value == "failed"
    assert DiarizationState.SKIPPED.value == "skipped"
```

- [ ] **Step 2: Run failing test**

```bash
rtk pytest tests/worker/test_state_model.py -q
```

Expected: fail because `worker.state_model` does not exist.

### Task 1.2: Implement State Model

**Files:**
- Create: `worker/state_model.py`
- Test: `tests/worker/test_state_model.py`

- [ ] **Step 1: Add implementation**

Create `worker/state_model.py`:

```python
from enum import Enum


class JobState(str, Enum):
    PENDING = "pending"
    EXPANDED = "expanded"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoState(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    TRANSCODING = "transcoding"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"


class CaptionIngestState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    SKIPPED = "skipped"


class DiarizationState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


ACTIVE_VIDEO_STATES = {
    VideoState.PENDING,
    VideoState.DOWNLOADING,
    VideoState.TRANSCODING,
    VideoState.TRANSCRIBING,
}

TERMINAL_CAPTION_STATES = {
    CaptionIngestState.COMPLETED,
    CaptionIngestState.UNAVAILABLE,
    CaptionIngestState.FAILED,
    CaptionIngestState.SKIPPED,
}


def job_state_from_video_states(video_states: list[VideoState]) -> JobState:
    if not video_states:
        return JobState.PENDING
    if all(state == VideoState.COMPLETED for state in video_states):
        return JobState.COMPLETED
    if not any(state in ACTIVE_VIDEO_STATES for state in video_states) and any(
        state == VideoState.FAILED for state in video_states
    ):
        return JobState.FAILED
    return JobState.DOWNLOADING


def can_start_native_transcription(
    *,
    staged: bool,
    own_caption_state: CaptionIngestState,
    batch_job_count: int,
    expected_batch_jobs: int,
    batch_has_open_caption_work: bool,
) -> bool:
    if not staged:
        return True
    if own_caption_state not in TERMINAL_CAPTION_STATES:
        return False
    if batch_job_count < expected_batch_jobs:
        return False
    if batch_has_open_caption_work:
        return False
    return True
```

- [ ] **Step 2: Run tests**

```bash
rtk pytest tests/worker/test_state_model.py -q
```

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add worker/state_model.py tests/worker/test_state_model.py
git commit -m "refactor(worker): define workflow state model"
```

### Task 1.3: Use State Model in Worker SQL Boundaries

**Files:**
- Modify: `worker/pipeline.py`
- Modify: `worker/loop.py`
- Test: `tests/worker/test_state_model.py`

- [ ] **Step 1: Replace duplicated active/terminal literals**

In `worker/pipeline.py`, import state constants:

```python
from worker.state_model import ACTIVE_VIDEO_STATES, TERMINAL_CAPTION_STATES, VideoState
```

Where SQL requires string lists, derive them once near the top:

```python
ACTIVE_VIDEO_STATE_VALUES = tuple(state.value for state in ACTIVE_VIDEO_STATES)
TERMINAL_CAPTION_STATE_VALUES = tuple(state.value for state in TERMINAL_CAPTION_STATES)
```

Keep existing SQL behavior, but replace hardcoded Python tuples like:

```python
ACTIVE_VIDEO_STATES = ("pending", "downloading", "transcoding", "transcribing")
```

with the enum-derived values.

- [ ] **Step 2: Keep SQL readable**

Do not over-abstract PostgreSQL queries in this task. Only replace duplicate state literals in Python and pass values into SQL parameters where practical:

```python
conn.execute(
    text("""
        SELECT COUNT(*)
        FROM videos
        WHERE job_id = :j AND state = ANY(:active_states)
    """),
    {"j": job_id, "active_states": list(ACTIVE_VIDEO_STATE_VALUES)},
)
```

- [ ] **Step 3: Run checks**

```bash
rtk mypy app worker
python3 -m compileall -q app worker alembic
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add worker/pipeline.py worker/loop.py
git commit -m "refactor(worker): reuse workflow state constants"
```

---

## Phase 2: Worker Repository Boundary

### Task 2.1: Introduce Video Repository Tests

**Files:**
- Create: `tests/worker/test_repositories.py`
- Create later: `worker/repositories.py`

- [ ] **Step 1: Write repository API test with fake connection**

Create `tests/worker/test_repositories.py`:

```python
from worker.repositories import VideoRepository


class FakeResult:
    def __init__(self, rows=None):
        self.rows = rows or []

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        return FakeResult()


def test_mark_video_completed_updates_diarization_state():
    conn = FakeConn()
    repo = VideoRepository(conn)
    repo.mark_completed("video-1", diarization_state="pending")
    sql, params = conn.calls[-1]
    assert "UPDATE videos" in sql
    assert "state='completed'" in sql
    assert params == {"video_id": "video-1", "diarization_state": "pending"}


def test_mark_caption_running_records_state():
    conn = FakeConn()
    repo = VideoRepository(conn)
    repo.mark_caption_running("video-2")
    sql, params = conn.calls[-1]
    assert "caption_ingest_state='running'" in sql
    assert params == {"video_id": "video-2"}
```

- [ ] **Step 2: Run failing test**

```bash
rtk pytest tests/worker/test_repositories.py -q
```

Expected: fail because `worker.repositories` does not exist.

### Task 2.2: Implement Repository Shell

**Files:**
- Create: `worker/repositories.py`
- Test: `tests/worker/test_repositories.py`

- [ ] **Step 1: Create repository class**

Create `worker/repositories.py`:

```python
from sqlalchemy import text


class VideoRepository:
    def __init__(self, conn):
        self.conn = conn

    def mark_completed(self, video_id: str, *, diarization_state: str) -> None:
        self.conn.execute(
            text(
                """
                UPDATE videos
                SET state='completed',
                    error=NULL,
                    diarization_state=:diarization_state,
                    updated_at=now()
                WHERE id=:video_id
                """
            ),
            {"video_id": video_id, "diarization_state": diarization_state},
        )

    def mark_caption_running(self, video_id: str) -> None:
        self.conn.execute(
            text(
                """
                UPDATE videos
                SET caption_ingest_state='running',
                    caption_ingest_error=NULL,
                    updated_at=now()
                WHERE id=:video_id
                """
            ),
            {"video_id": video_id},
        )

    def mark_caption_pending_with_error(self, video_id: str, error: str) -> None:
        self.conn.execute(
            text(
                """
                UPDATE videos
                SET caption_ingest_state='pending',
                    caption_ingest_error=:error,
                    updated_at=now()
                WHERE id=:video_id
                """
            ),
            {"video_id": video_id, "error": error[:5000]},
        )

    def mark_caption_failed(self, video_id: str, error: str) -> None:
        self.conn.execute(
            text(
                """
                UPDATE videos
                SET caption_ingest_state='failed',
                    caption_ingest_error=:error,
                    updated_at=now()
                WHERE id=:video_id
                """
            ),
            {"video_id": video_id, "error": error[:5000]},
        )

    def mark_caption_unavailable(self, video_id: str) -> None:
        self.conn.execute(
            text(
                """
                UPDATE videos
                SET caption_ingest_state='unavailable',
                    updated_at=now()
                WHERE id=:video_id
                """
            ),
            {"video_id": video_id},
        )

    def mark_caption_completed(self, video_id: str) -> None:
        self.conn.execute(
            text(
                """
                UPDATE videos
                SET caption_ingest_state='completed',
                    caption_ingest_error=NULL,
                    updated_at=now()
                WHERE id=:video_id
                """
            ),
            {"video_id": video_id},
        )
```

- [ ] **Step 2: Run repository tests**

```bash
rtk pytest tests/worker/test_repositories.py -q
```

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add worker/repositories.py tests/worker/test_repositories.py
git commit -m "refactor(worker): add video repository boundary"
```

### Task 2.3: Adopt Repository in Caption Ingest Path

**Files:**
- Modify: `worker/pipeline.py`
- Modify: `worker/repositories.py`
- Test: `tests/worker/test_repositories.py`

- [ ] **Step 1: Replace caption state SQL calls**

In `worker/pipeline.py`, import:

```python
from worker.repositories import VideoRepository
```

Inside `capture_youtube_captions_for_unprocessed`, instantiate once:

```python
video_repo = VideoRepository(conn)
```

Replace direct updates:

```python
conn.execute(text("UPDATE videos SET caption_ingest_state='running'..."), ...)
```

with:

```python
video_repo.mark_caption_running(str(vid))
```

Use corresponding methods for `completed`, `unavailable`, `failed`, and rate-limit `pending`.

- [ ] **Step 2: Run checks**

```bash
rtk mypy app worker
python3 -m compileall -q app worker alembic
```

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add worker/pipeline.py worker/repositories.py tests/worker/test_repositories.py
git commit -m "refactor(worker): route caption state writes through repository"
```

---

## Phase 3: YouTube Ingestion Adapter

### Task 3.1: Define YouTube Service Result Types

**Files:**
- Create: `worker/youtube/errors.py`
- Create: `worker/youtube/__init__.py`
- Test: `tests/worker/test_youtube_errors.py`

- [ ] **Step 1: Write tests**

Create `tests/worker/test_youtube_errors.py`:

```python
from worker.youtube.errors import YoutubeErrorKind, classify_youtube_stderr


def test_rate_limit_wins_over_unavailable_text():
    stderr = "Video unavailable. The current session has been rate-limited by YouTube for up to an hour."
    assert classify_youtube_stderr(stderr) == YoutubeErrorKind.RATE_LIMITED


def test_auth_required_is_auth_error():
    stderr = "Sign in to confirm you're not a bot. Use --cookies"
    assert classify_youtube_stderr(stderr) == YoutubeErrorKind.AUTH_REQUIRED


def test_missing_video_is_unavailable():
    stderr = "Video unavailable. This video is private"
    assert classify_youtube_stderr(stderr) == YoutubeErrorKind.UNAVAILABLE
```

- [ ] **Step 2: Implement errors module**

Create `worker/youtube/__init__.py`:

```python
"""YouTube ingestion adapter package."""
```

Create `worker/youtube/errors.py`:

```python
from enum import Enum


class YoutubeErrorKind(str, Enum):
    RATE_LIMITED = "rate_limited"
    AUTH_REQUIRED = "auth_required"
    TOKEN_REQUIRED = "token_required"
    UNAVAILABLE = "unavailable"
    NETWORK = "network"
    UNKNOWN = "unknown"


def classify_youtube_stderr(stderr: str) -> YoutubeErrorKind:
    text = stderr.lower()
    if "rate-limited" in text or "rate limited" in text or "current session has been rate" in text:
        return YoutubeErrorKind.RATE_LIMITED
    if "up to an hour" in text and "youtube" in text:
        return YoutubeErrorKind.RATE_LIMITED
    if "sign in" in text or "not a bot" in text or "cookies" in text and "authentication" in text:
        return YoutubeErrorKind.AUTH_REQUIRED
    if "po_token" in text or "po token" in text:
        return YoutubeErrorKind.TOKEN_REQUIRED
    if "unavailable" in text or "private" in text or "not found" in text or "404" in text:
        return YoutubeErrorKind.UNAVAILABLE
    if "timeout" in text or "connection" in text or "network" in text:
        return YoutubeErrorKind.NETWORK
    return YoutubeErrorKind.UNKNOWN
```

- [ ] **Step 3: Run tests**

```bash
rtk pytest tests/worker/test_youtube_errors.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add worker/youtube tests/worker/test_youtube_errors.py
git commit -m "refactor(worker): add youtube error taxonomy"
```

### Task 3.2: Extract YtDlpExecutor

**Files:**
- Create: `worker/youtube/yt_dlp_executor.py`
- Test: `tests/worker/test_yt_dlp_executor.py`

- [ ] **Step 1: Write executor tests**

Create `tests/worker/test_yt_dlp_executor.py`:

```python
import subprocess

import pytest

from worker.youtube.errors import YoutubeErrorKind
from worker.youtube.yt_dlp_executor import YtDlpError, YtDlpExecutor


def test_executor_returns_stdout(monkeypatch):
    def fake_run(cmd, capture_output, text, check, timeout):
        assert cmd[:2] == ["yt-dlp", "-J"]
        return subprocess.CompletedProcess(cmd, 0, stdout='{"id":"abc"}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    executor = YtDlpExecutor(timeout=30)
    assert executor.run_json(["-J", "https://example.test"]) == {"id": "abc"}


def test_executor_raises_classified_error(monkeypatch):
    def fake_run(cmd, capture_output, text, check, timeout):
        raise subprocess.CalledProcessError(
            1,
            cmd,
            stderr="The current session has been rate-limited by YouTube for up to an hour.",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    executor = YtDlpExecutor(timeout=30)
    with pytest.raises(YtDlpError) as exc:
        executor.run_json(["-J", "https://example.test"])
    assert exc.value.kind == YoutubeErrorKind.RATE_LIMITED
```

- [ ] **Step 2: Implement executor**

Create `worker/youtube/yt_dlp_executor.py`:

```python
import json
import subprocess
from dataclasses import dataclass
from typing import Any

from worker.youtube.errors import YoutubeErrorKind, classify_youtube_stderr


@dataclass
class YtDlpError(RuntimeError):
    kind: YoutubeErrorKind
    stderr: str
    command: list[str]

    def __str__(self) -> str:
        return f"yt-dlp failed with {self.kind.value}: {self.stderr[:300]}"


class YtDlpExecutor:
    def __init__(self, *, timeout: float):
        self.timeout = timeout

    def run_json(self, args: list[str]) -> dict[str, Any]:
        cmd = ["yt-dlp", *args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=self.timeout,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            raise YtDlpError(classify_youtube_stderr(stderr), stderr, cmd) from exc
        return json.loads(result.stdout)
```

- [ ] **Step 3: Run tests**

```bash
rtk pytest tests/worker/test_yt_dlp_executor.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add worker/youtube/yt_dlp_executor.py tests/worker/test_yt_dlp_executor.py
git commit -m "refactor(worker): extract yt-dlp executor"
```

### Task 3.3: Route Caption Metadata Through Executor

**Files:**
- Modify: `worker/youtube_captions.py`
- Modify: `worker/youtube_resilience.py`
- Test: `tests/worker/test_youtube_captions.py`, `tests/worker/test_youtube_errors.py`

- [ ] **Step 1: Add compatibility mapping**

In `worker/youtube_resilience.py`, add a helper:

```python
from worker.youtube.errors import YoutubeErrorKind


def error_class_from_youtube_kind(kind: YoutubeErrorKind) -> ErrorClass:
    if kind == YoutubeErrorKind.RATE_LIMITED:
        return ErrorClass.THROTTLE
    if kind == YoutubeErrorKind.AUTH_REQUIRED:
        return ErrorClass.AUTH
    if kind == YoutubeErrorKind.TOKEN_REQUIRED:
        return ErrorClass.TOKEN
    if kind == YoutubeErrorKind.UNAVAILABLE:
        return ErrorClass.NOT_FOUND
    if kind == YoutubeErrorKind.NETWORK:
        return ErrorClass.NETWORK
    return ErrorClass.UNKNOWN
```

- [ ] **Step 2: Use executor for JSON metadata**

In `worker/youtube_captions.py::_yt_dlp_json`, create:

```python
from worker.youtube.yt_dlp_executor import YtDlpError, YtDlpExecutor
from worker.youtube_resilience import error_class_from_youtube_kind

executor = YtDlpExecutor(timeout=settings.YTDLP_REQUEST_TIMEOUT)
```

Replace the raw `subprocess.run(...); json.loads(result.stdout)` block inside `fetch_metadata` with:

```python
try:
    metadata = executor.run_json(cmd[1:])
except YtDlpError as exc:
    raise subprocess.CalledProcessError(1, exc.command, stderr=exc.stderr) from exc
return metadata
```

Keep the existing retry/circuit/logging behavior for this task. This is only moving the subprocess/json boundary.

- [ ] **Step 3: Run checks**

```bash
rtk mypy app worker
rtk pytest tests/worker/test_youtube_errors.py tests/worker/test_yt_dlp_executor.py -q
python3 -m compileall -q app worker alembic
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add worker/youtube_captions.py worker/youtube_resilience.py worker/youtube tests/worker
git commit -m "refactor(worker): use yt-dlp executor for caption metadata"
```

---

## Phase 4: Video Processing Pipeline Boundary

### Task 4.1: Define Pipeline Interface

**Files:**
- Create: `worker/video_pipeline.py`
- Create: `tests/worker/test_video_pipeline_interface.py`

- [ ] **Step 1: Write interface tests**

Create `tests/worker/test_video_pipeline_interface.py`:

```python
from dataclasses import dataclass

from worker.video_pipeline import ProcessVideoCommand, ProcessVideoResult, VideoProcessingPipeline


class FakeDeps:
    def __init__(self):
        self.processed = []

    def process(self, video_id):
        self.processed.append(video_id)
        return ProcessVideoResult(video_id=video_id, segment_count=3, diarization_state="pending")


def test_pipeline_has_single_process_entrypoint():
    deps = FakeDeps()
    pipeline = VideoProcessingPipeline(process_func=deps.process)
    result = pipeline.process(ProcessVideoCommand(video_id="video-1"))
    assert result == ProcessVideoResult(video_id="video-1", segment_count=3, diarization_state="pending")
    assert deps.processed == ["video-1"]
```

- [ ] **Step 2: Implement thin wrapper**

Create `worker/video_pipeline.py`:

```python
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessVideoCommand:
    video_id: str


@dataclass(frozen=True)
class ProcessVideoResult:
    video_id: str
    segment_count: int
    diarization_state: str


class VideoProcessingPipeline:
    def __init__(self, process_func: Callable[[str], ProcessVideoResult]):
        self._process_func = process_func

    def process(self, command: ProcessVideoCommand) -> ProcessVideoResult:
        return self._process_func(command.video_id)
```

- [ ] **Step 3: Run tests**

```bash
rtk pytest tests/worker/test_video_pipeline_interface.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add worker/video_pipeline.py tests/worker/test_video_pipeline_interface.py
git commit -m "refactor(worker): define video processing pipeline interface"
```

### Task 4.2: Adapt Existing `process_video` Behind Interface

**Files:**
- Modify: `worker/video_pipeline.py`
- Modify: `worker/loop.py`
- Modify: `worker/pipeline.py`

- [ ] **Step 1: Add factory around current implementation**

In `worker/video_pipeline.py`, add:

```python
def default_video_processing_pipeline():
    from worker.pipeline import process_video

    def run(video_id: str) -> ProcessVideoResult:
        segment_count = process_video(video_id)
        return ProcessVideoResult(video_id=video_id, segment_count=segment_count or 0, diarization_state="pending")

    return VideoProcessingPipeline(process_func=run)
```

If `process_video` currently returns `None`, first update `worker/pipeline.py::process_video` to return `len(diar_segments)` after persistence.

- [ ] **Step 2: Update worker loop dispatch**

In `worker/loop.py`, import:

```python
from worker.video_pipeline import ProcessVideoCommand, default_video_processing_pipeline
```

Create the pipeline near module setup:

```python
video_pipeline = default_video_processing_pipeline()
```

Replace:

```python
process_video(video_id)
```

with:

```python
video_pipeline.process(ProcessVideoCommand(video_id=str(video_id)))
```

- [ ] **Step 3: Run checks**

```bash
rtk mypy app worker
python3 -m compileall -q app worker alembic
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add worker/video_pipeline.py worker/loop.py worker/pipeline.py
git commit -m "refactor(worker): dispatch videos through pipeline interface"
```

---

## Phase 5: Search Service

### Task 5.1: Extract Search Types and Service Boundary

**Files:**
- Create: `app/search/__init__.py`
- Create: `app/search/types.py`
- Create: `app/search/service.py`
- Test: `tests/test_search_service.py`

- [ ] **Step 1: Write tests**

Create `tests/test_search_service.py`:

```python
from app.search.service import SearchService
from app.search.types import SearchRequest, SearchResult


class FakeSearchBackend:
    def __init__(self):
        self.requests = []

    def search(self, request: SearchRequest):
        self.requests.append(request)
        return [SearchResult(video_id="v1", segment_id="s1", start_ms=1000, end_ms=2000, snippet="hello", rank=0.9)]


def test_search_service_delegates_to_backend():
    backend = FakeSearchBackend()
    service = SearchService(backend=backend)
    results = service.search(SearchRequest(q="hello", source="native", limit=10, offset=0))
    assert results[0].video_id == "v1"
    assert backend.requests[0].q == "hello"
```

- [ ] **Step 2: Implement types**

Create `app/search/__init__.py`:

```python
"""Search domain services."""
```

Create `app/search/types.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchRequest:
    q: str
    source: str
    limit: int
    offset: int


@dataclass(frozen=True)
class SearchResult:
    video_id: str
    segment_id: str
    start_ms: int
    end_ms: int
    snippet: str
    rank: float
```

Create `app/search/service.py`:

```python
from typing import Protocol

from app.search.types import SearchRequest, SearchResult


class SearchBackend(Protocol):
    def search(self, request: SearchRequest) -> list[SearchResult]:
        ...


class SearchService:
    def __init__(self, *, backend: SearchBackend):
        self.backend = backend

    def search(self, request: SearchRequest) -> list[SearchResult]:
        if not request.q.strip():
            return []
        return self.backend.search(request)
```

- [ ] **Step 3: Run tests**

```bash
rtk pytest tests/test_search_service.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add app/search tests/test_search_service.py
git commit -m "refactor(api): introduce search service boundary"
```

### Task 5.2: Move Postgres Native Search Behind Backend

**Files:**
- Create: `app/search/repositories.py`
- Modify: `app/routes/search.py`
- Modify: `app/crud.py`

- [ ] **Step 1: Add repository wrapper**

Create `app/search/repositories.py`:

```python
from app import crud
from app.search.types import SearchRequest, SearchResult


class PostgresSearchBackend:
    def __init__(self, db):
        self.db = db

    def search(self, request: SearchRequest) -> list[SearchResult]:
        rows = crud.search_segments_advanced(
            self.db,
            request.q,
            limit=request.limit,
            offset=request.offset,
        )
        return [
            SearchResult(
                video_id=str(row["video_id"]),
                segment_id=str(row["id"]),
                start_ms=int(row["start_ms"]),
                end_ms=int(row["end_ms"]),
                snippet=row["snippet"],
                rank=float(row.get("rank") or 0),
            )
            for row in rows
        ]
```

- [ ] **Step 2: Use service in native branch only**

In `app/routes/search.py`, for the native/Postgres branch, create:

```python
from app.search.repositories import PostgresSearchBackend
from app.search.service import SearchService
from app.search.types import SearchRequest

service = SearchService(backend=PostgresSearchBackend(db))
results = service.search(SearchRequest(q=q, source=source, limit=limit, offset=offset))
```

Map `SearchResult` back to existing response schema without changing the public API.

- [ ] **Step 3: Run checks**

```bash
rtk mypy app worker
python3 -m compileall -q app worker alembic
```

Expected: pass.

- [ ] **Step 4: Smoke test API**

Run only if API is running:

```bash
rtk curl -fsS 'http://localhost:41177/search?q=Gonzales&source=native&limit=5'
```

Expected: JSON search response includes the Hasan video if the local DB still has it.

- [ ] **Step 5: Commit**

```bash
git add app/search app/routes/search.py app/crud.py
git commit -m "refactor(api): route native search through search service"
```

---

## Phase 6: Transcript Presentation Service

### Task 6.1: Define Transcript View Modes

**Files:**
- Create: `app/transcripts/__init__.py`
- Create: `app/transcripts/types.py`
- Create: `app/transcripts/service.py`
- Test: `tests/test_transcript_presentation.py`

- [ ] **Step 1: Write tests**

Create `tests/test_transcript_presentation.py`:

```python
from app.transcripts.service import TranscriptPresentationService
from app.transcripts.types import TranscriptSegment, TranscriptViewMode


def test_raw_mode_preserves_text_and_speaker():
    service = TranscriptPresentationService()
    segments = [TranscriptSegment(start_ms=0, end_ms=1000, text=" Hello ", speaker_label="Speaker 1")]
    result = service.present(segments, mode=TranscriptViewMode.RAW)
    assert result[0].text == " Hello "
    assert result[0].speaker_label == "Speaker 1"


def test_cleaned_mode_strips_segment_text():
    service = TranscriptPresentationService()
    segments = [TranscriptSegment(start_ms=0, end_ms=1000, text=" Hello ", speaker_label=None)]
    result = service.present(segments, mode=TranscriptViewMode.CLEANED)
    assert result[0].text == "Hello"
```

- [ ] **Step 2: Implement service**

Create `app/transcripts/__init__.py`:

```python
"""Transcript presentation services."""
```

Create `app/transcripts/types.py`:

```python
from dataclasses import dataclass
from enum import Enum


class TranscriptViewMode(str, Enum):
    RAW = "raw"
    CLEANED = "cleaned"
    FORMATTED = "formatted"


@dataclass(frozen=True)
class TranscriptSegment:
    start_ms: int
    end_ms: int
    text: str
    speaker_label: str | None
```

Create `app/transcripts/service.py`:

```python
from app.transcripts.types import TranscriptSegment, TranscriptViewMode


class TranscriptPresentationService:
    def present(
        self,
        segments: list[TranscriptSegment],
        *,
        mode: TranscriptViewMode,
    ) -> list[TranscriptSegment]:
        if mode == TranscriptViewMode.RAW:
            return segments
        if mode == TranscriptViewMode.CLEANED:
            return [
                TranscriptSegment(
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    text=segment.text.strip(),
                    speaker_label=segment.speaker_label,
                )
                for segment in segments
            ]
        return segments
```

- [ ] **Step 3: Run tests**

```bash
rtk pytest tests/test_transcript_presentation.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add app/transcripts tests/test_transcript_presentation.py
git commit -m "refactor(api): introduce transcript presentation service"
```

### Task 6.2: Use Presentation Service in Video Route

**Files:**
- Modify: `app/routes/videos.py`
- Modify: `app/transcripts/service.py`

- [ ] **Step 1: Convert DB rows to transcript segments**

In `app/routes/videos.py`, add a small local mapper near transcript endpoint code:

```python
from app.transcripts.service import TranscriptPresentationService
from app.transcripts.types import TranscriptSegment, TranscriptViewMode


def _to_transcript_segment(row) -> TranscriptSegment:
    return TranscriptSegment(
        start_ms=int(row["start_ms"]),
        end_ms=int(row["end_ms"]),
        text=row["text"],
        speaker_label=row.get("speaker_label"),
    )
```

- [ ] **Step 2: Use service for raw/cleaned modes**

Where the route branches on raw/cleaned transcript modes, call:

```python
presentation = TranscriptPresentationService()
segments = presentation.present(
    [_to_transcript_segment(row) for row in rows],
    mode=TranscriptViewMode.CLEANED if cleaned else TranscriptViewMode.RAW,
)
```

Then map `segments` back to the existing response schema. Do not change response JSON.

- [ ] **Step 3: Run checks**

```bash
rtk mypy app worker
python3 -m compileall -q app worker alembic
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add app/routes/videos.py app/transcripts
git commit -m "refactor(api): present transcripts through service"
```

---

## Phase 7: Schema Contract Tests

### Task 7.1: Assert Required State Columns and Constraints

**Files:**
- Create: `tests/test_schema_contract.py`

- [ ] **Step 1: Write schema contract tests**

Create `tests/test_schema_contract.py`:

```python
import pytest
from sqlalchemy import text


@pytest.mark.integration
def test_videos_has_caption_and_diarization_state_columns(db_session):
    rows = db_session.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'videos'
              AND column_name IN ('caption_ingest_state', 'caption_ingest_error', 'diarization_state', 'diarization_error')
            ORDER BY column_name
            """
        )
    ).scalars().all()
    assert rows == [
        "caption_ingest_error",
        "caption_ingest_state",
        "diarization_error",
        "diarization_state",
    ]


@pytest.mark.integration
def test_video_state_constraints_exist(db_session):
    names = db_session.execute(
        text(
            """
            SELECT conname
            FROM pg_constraint
            WHERE conname IN ('videos_caption_ingest_state_check', 'videos_diarization_state_check')
            ORDER BY conname
            """
        )
    ).scalars().all()
    assert names == ["videos_caption_ingest_state_check", "videos_diarization_state_check"]
```

- [ ] **Step 2: Run migration/schema tests in the project’s current test environment**

```bash
rtk pytest tests/test_schema_contract.py -q
```

Expected: pass if integration DB fixture is available; otherwise document skip reason in the test output.

- [ ] **Step 3: Commit**

```bash
git add tests/test_schema_contract.py
git commit -m "test(schema): assert workflow state columns"
```

### Task 7.2: Add Fresh-vs-Migrated Schema Comparison Script

**Files:**
- Create: `scripts/compare_schema_contract.py`
- Modify: `.github/workflows/migrations-ci.yml` later only after local script is reliable

- [ ] **Step 1: Create comparison script**

Create `scripts/compare_schema_contract.py`:

```python
#!/usr/bin/env python3
"""Compare essential schema contract between two PostgreSQL databases."""

import os
import sys

import psycopg


QUERY = """
SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('jobs', 'videos', 'transcripts', 'segments', 'youtube_transcripts', 'youtube_segments')
ORDER BY table_name, ordinal_position
"""


def fetch(url: str):
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(QUERY)
            return cur.fetchall()


def main() -> int:
    left_url = os.environ["SCHEMA_LEFT_DATABASE_URL"]
    right_url = os.environ["SCHEMA_RIGHT_DATABASE_URL"]
    left = fetch(left_url)
    right = fetch(right_url)
    if left != right:
        print("Schema contract mismatch", file=sys.stderr)
        print("Left only:", sorted(set(left) - set(right)), file=sys.stderr)
        print("Right only:", sorted(set(right) - set(left)), file=sys.stderr)
        return 1
    print("Schema contract matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Compile script**

```bash
python3 -m py_compile scripts/compare_schema_contract.py
```

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add scripts/compare_schema_contract.py
git commit -m "test(schema): add schema contract comparison script"
```

---

## Phase 8: Frontend Product Kernels

### Task 8.1: Extract Search Transcript Feature Helpers

**Files:**
- Create: `frontend/src/features/searchTranscript/matches.ts`
- Test: `frontend/src/tests/searchTranscript.matches.test.ts`
- Modify later: `SearchPage.tsx`, `VideoPage.tsx`

- [ ] **Step 1: Write tests**

Create `frontend/src/tests/searchTranscript.matches.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { groupHitsByVideo, segmentIdsFromHits } from '../features/searchTranscript/matches';

describe('search transcript matches', () => {
  it('groups hits by video id', () => {
    const hits = [
      { video_id: 'v1', segment_id: 's1' },
      { video_id: 'v2', segment_id: 's2' },
      { video_id: 'v1', segment_id: 's3' },
    ];
    expect(groupHitsByVideo(hits)).toEqual({
      v1: [hits[0], hits[2]],
      v2: [hits[1]],
    });
  });

  it('extracts segment ids in order', () => {
    const hits = [{ segment_id: 'a' }, { segment_id: 'b' }];
    expect(segmentIdsFromHits(hits)).toEqual(['a', 'b']);
  });
});
```

- [ ] **Step 2: Implement helpers**

Create `frontend/src/features/searchTranscript/matches.ts`:

```typescript
type HitLike = {
  video_id?: string;
  segment_id?: string;
};

export function groupHitsByVideo<T extends HitLike>(hits: T[]): Record<string, T[]> {
  return hits.reduce<Record<string, T[]>>((groups, hit) => {
    if (!hit.video_id) return groups;
    groups[hit.video_id] = groups[hit.video_id] ?? [];
    groups[hit.video_id].push(hit);
    return groups;
  }, {});
}

export function segmentIdsFromHits<T extends HitLike>(hits: T[]): string[] {
  return hits.map((hit) => hit.segment_id).filter((id): id is string => Boolean(id));
}
```

- [ ] **Step 3: Run frontend tests/build**

```bash
cd frontend && rtk npm run build && rtk lint
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/searchTranscript frontend/src/tests/searchTranscript.matches.test.ts
git commit -m "refactor(frontend): extract search transcript helpers"
```

### Task 8.2: Extract Entitlement Policy

**Files:**
- Create: `frontend/src/features/entitlements/policy.ts`
- Test: `frontend/src/tests/entitlements.policy.test.ts`
- Modify: `frontend/src/components/ExportMenu.tsx`

- [ ] **Step 1: Write tests**

Create `frontend/src/tests/entitlements.policy.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { canExportFormat } from '../features/entitlements/policy';

describe('entitlement policy', () => {
  it('allows txt export for anonymous users', () => {
    expect(canExportFormat({ plan: null, format: 'txt' })).toBe(true);
  });

  it('requires pro for pdf export', () => {
    expect(canExportFormat({ plan: 'free', format: 'pdf' })).toBe(false);
    expect(canExportFormat({ plan: 'pro', format: 'pdf' })).toBe(true);
  });
});
```

- [ ] **Step 2: Implement policy**

Create `frontend/src/features/entitlements/policy.ts`:

```typescript
export type Plan = 'free' | 'pro' | 'admin' | null | undefined;
export type ExportFormat = 'txt' | 'srt' | 'vtt' | 'pdf' | 'docx';

const PRO_EXPORT_FORMATS = new Set<ExportFormat>(['pdf', 'docx']);

export function canExportFormat({ plan, format }: { plan: Plan; format: ExportFormat }): boolean {
  if (!PRO_EXPORT_FORMATS.has(format)) return true;
  return plan === 'pro' || plan === 'admin';
}
```

- [ ] **Step 3: Use policy in `ExportMenu`**

In `frontend/src/components/ExportMenu.tsx`, replace inline Pro checks with:

```typescript
import { canExportFormat, type ExportFormat } from '../features/entitlements/policy';

const allowed = canExportFormat({ plan: user?.plan, format: format as ExportFormat });
```

Keep existing UI copy.

- [ ] **Step 4: Run frontend checks**

```bash
cd frontend && rtk npm run build && rtk lint
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/entitlements frontend/src/tests/entitlements.policy.test.ts frontend/src/components/ExportMenu.tsx
git commit -m "refactor(frontend): centralize entitlement policy"
```

---

## Phase 9: Auth/Billing Policy Modules

### Task 9.1: Extract Backend Entitlement Policy

**Files:**
- Create: `app/billing/policy.py`
- Create: `tests/test_billing_policy.py`
- Modify later: `app/routes/exports.py`, `app/routes/billing.py`

- [ ] **Step 1: Write tests**

Create `tests/test_billing_policy.py`:

```python
from app.billing.policy import can_export_format


def test_txt_export_allowed_for_anonymous():
    assert can_export_format(user_plan=None, export_format="txt")


def test_pdf_export_requires_paid_plan():
    assert not can_export_format(user_plan="free", export_format="pdf")
    assert can_export_format(user_plan="pro", export_format="pdf")
    assert can_export_format(user_plan="admin", export_format="pdf")
```

- [ ] **Step 2: Implement policy**

Create `app/billing/policy.py`:

```python
PRO_EXPORT_FORMATS = {"pdf", "docx"}
PAID_PLANS = {"pro", "admin"}


def can_export_format(*, user_plan: str | None, export_format: str) -> bool:
    if export_format not in PRO_EXPORT_FORMATS:
        return True
    return user_plan in PAID_PLANS
```

- [ ] **Step 3: Run tests**

```bash
rtk pytest tests/test_billing_policy.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add app/billing/policy.py tests/test_billing_policy.py
git commit -m "refactor(api): centralize billing entitlement policy"
```

### Task 9.2: Use Entitlement Policy in Export Route

**Files:**
- Modify: `app/routes/exports.py`
- Test: `tests/test_billing_policy.py`

- [ ] **Step 1: Replace inline export gating**

In `app/routes/exports.py`, import:

```python
from app.billing.policy import can_export_format
```

Where export formats are gated, use:

```python
if not can_export_format(user_plan=user.get("plan") if user else None, export_format=format):
    raise HTTPException(status_code=402, detail="Upgrade required for this export format")
```

Keep existing status codes/copy if the route already has exact response wording.

- [ ] **Step 2: Run checks**

```bash
rtk mypy app worker
python3 -m compileall -q app worker alembic
```

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add app/routes/exports.py app/billing/policy.py
git commit -m "refactor(api): use entitlement policy for exports"
```

---

## Phase 10: Final Integration Review

### Task 10.1: Full Local Verification

**Files:**
- No code files unless failures require fixes.

- [ ] **Step 1: Run backend checks**

```bash
rtk mypy app worker
python3 -m compileall -q app worker alembic
```

Expected: pass.

- [ ] **Step 2: Run frontend checks**

```bash
cd frontend && rtk npm run build && rtk lint
```

Expected: pass.

- [ ] **Step 3: Validate compose**

```bash
docker compose -f docker-compose.yml -f docker-compose.gtx1080.yml config --quiet
```

Expected: no output and zero exit code.

- [ ] **Step 4: Verify staged batch lock without starting worker**

```bash
docker compose -f docker-compose.yml -f docker-compose.gtx1080.yml exec db psql -U postgres -d transcripts -c "SELECT v.state::text AS state, v.caption_ingest_state, count(*) FROM videos v JOIN jobs j ON j.id=v.job_id WHERE j.meta->>'batch_id'='channels-20260529-core' GROUP BY v.state::text, v.caption_ingest_state ORDER BY state, v.caption_ingest_state;"
```

Expected: pending/completed/unavailable/failed caption states; native Whisper should not have started until all caption states terminal.

- [ ] **Step 5: Commit verification note**

Create or update `docs/superpowers/plans/2026-05-29-architecture-baseline.md` with final verification results.

```bash
git add docs/superpowers/plans/2026-05-29-architecture-baseline.md
git commit -m "docs: record architecture refactor verification"
```

---

## Recommended Execution Order

1. Phase 0 baseline.
2. Phase 1 state model.
3. Phase 2 repositories.
4. Phase 3 YouTube adapter.
5. Phase 4 video pipeline interface.
6. Phase 7 schema contract tests.
7. Phase 5 search service.
8. Phase 6 transcript presentation.
9. Phase 8 frontend product kernels.
10. Phase 9 auth/billing policy.
11. Phase 10 final verification.

This order keeps the running ingestion system safest: stabilize state and YouTube boundaries before touching search/frontend/policy surfaces.

---

## Self-Review

- Spec coverage: all eight findings are represented as implementation phases.
- No placeholders: tasks include exact files, commands, and concrete code sketches.
- Type consistency: shared names are consistent across tasks: `CaptionIngestState`, `DiarizationState`, `VideoRepository`, `YtDlpExecutor`, `SearchService`, `TranscriptPresentationService`.
- Scope risk: this is intentionally a master plan. Execute one phase at a time and review after each phase; do not batch all phases into one PR.
