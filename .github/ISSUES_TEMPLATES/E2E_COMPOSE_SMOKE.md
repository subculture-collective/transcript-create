# [TEST/INFRA] E2E smoke via docker compose

Goal: Add CI job that builds images, docker compose up (db, api, worker), verifies health endpoints, enqueues a tiny sample job, observes state progression, and shuts down.

Steps:
1) Create .github/workflows/e2e-compose.yml that uses services or remote-docker to run docker compose.
2) Health checks: GET /openapi.json, DB readiness, worker logs for picked video.
3) Enqueue a job via curl (use public short audio or a mock endpoint if not stable) and poll status (timeout limit).
4) Tear down and upload minimal logs as artifacts on failure.

Acceptance criteria:
- CI job runs on PR (nightly optional) and completes within ~10 minutes.
- Verifies core stack boots and basic flow works.

Metadata:
- Milestone: M1 — Foundation & CI Ready
- Labels: type:test, area:infra, P1-high, status:ready
