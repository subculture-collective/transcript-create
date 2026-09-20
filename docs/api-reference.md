# API reference

**Status:** generated-contract companion (2026-07-12).

The machine-readable authority is [OpenAPI](api/openapi.json). Frontend types are generated into `frontend/src/types/generated/api.ts`, and CI fails on drift.

Primary groups are authentication, scoped API keys, search/grouped search/suggestions/mention exports, videos/transcripts/chapters/related/quoted moments, archive timelines/topics/opinions, favorites/saved searches, jobs/attempts, vocabularies, events, analytics reports, administration, exports, public support configuration, and health.

Access requirements are in [the access matrix](access-matrix.md). `GET /support` exposes only whether support is enabled and its validated public hosted link; the application has no billing, charge-creation, or card-data endpoint. `/api` changes are additive; deprecation response headers and release notes remain for two releases; breaking changes require `/api/v2`.
