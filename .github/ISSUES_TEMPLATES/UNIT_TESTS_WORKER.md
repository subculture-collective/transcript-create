# [TEST/WORKER] Unit tests for pipeline stages

Goal: Add unit tests for worker pipeline stages with mocks for yt-dlp, ffmpeg, whisper, diarization.

Steps:
1) Create tests/worker/test_pipeline.py covering:
   - happy path through download -> ensure_wav_16k -> chunk -> transcribe_chunk -> persist.
   - failure handling in each stage raises/propagates and marks video failed.
2) Use monkeypatch/mocks to avoid external binaries and GPU.
3) Provide fixtures for a tiny audio sample (1-2s) embedded in repo or generated in test.
4) Ensure DB ops are mocked or use in-memory sqlite with similar schema for unit scope.

Acceptance criteria:
- Tests run in CI fast (<2 minutes).
- Coverage for worker/ rises to > 60%.

Metadata:
- Milestone: M1 — Foundation & CI Ready
- Labels: type:test, area:worker, P1-high, status:ready
