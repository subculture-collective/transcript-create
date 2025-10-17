# [TEST/API/DB] Integration tests with ephemeral Postgres

Goal: Add integration tests for /jobs → /videos → /transcript flow using ephemeral Postgres (Docker or testcontainers) in CI.

Steps:
1) Create tests/integration/test_api_flow.py that spins an app TestClient and points to a test DATABASE_URL.
2) Apply schema.sql to test DB; seed minimal data if needed.
3) Simulate a job creation, poll status, and fetch transcript (mock worker or simulate success path).
4) Ensure cleanup between test runs.

Acceptance criteria:
- Integration tests run in CI; isolated DB; no interference with local dev DB.
- Validates core flow end-to-end at API level.

Metadata:
- Milestone: M1 — Foundation & CI Ready
- Labels: type:test, area:api, area:db, P1-high, status:ready
