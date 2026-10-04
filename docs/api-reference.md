# API reference

**Status:** generated-contract companion (2026-07-12).

The machine-readable authority is [OpenAPI](api/openapi.json), a committed artifact. Rekolekt core is headless, so this contract is the product surface: archive frontends and the [`rekolekt-web`](https://git.subcult.tv/subculture-collective/rekolekt-web) kit generate their clients and types from it. `make verify` regenerates the document and fails on drift; `make openapi` writes it after an API change.

`GET /site` returns the public site profile: name, description, creator and operator names, tagline, notices, logo, favicon and social image URLs, and feature flags. Its `theme` object (`font`, `dark` and `light` colour tokens) is deprecated in the schema. It is still served so existing frontends work; new frontends should own their styling.

Primary groups are authentication, scoped API keys, search/grouped search/suggestions/mention exports, videos/transcripts/chapters/related/quoted moments, archive timelines/topics/opinions, favorites/saved searches, jobs/attempts, vocabularies, events, analytics reports, administration, exports, public support configuration, and health.

Access requirements are in [the access matrix](access-matrix.md). `GET /support` exposes only whether support is enabled and its validated public hosted link; the application has no billing, charge-creation, or card-data endpoint. `/api` changes are additive; deprecation response headers and release notes remain for two releases; breaking changes require `/api/v2`.
