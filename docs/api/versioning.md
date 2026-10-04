# API stability and versioning

Status: shipped

The existing public `/api` contract is the stable version 1 API. Responses carry
`API-Version: 1`. Version 1 changes are additive: existing fields, meanings,
status codes, and accepted values remain compatible within the version.

Deprecations are announced in release notes and return the standard
`Deprecation: true`, `Sunset`, and `Link: <replacement>; rel="successor-version"`
headers. A deprecated contract remains available for at least two published
releases before removal. Each deprecation note names the first deprecated
release, replacement, and earliest removal release.

Breaking changes require a new `/api/v2` contract. Version 1 and version 2 run
in parallel for the documented migration window; an unversioned breaking
change is not permitted.

The canonical machine-readable version 1 contract is
[`openapi.json`](openapi.json). It is a committed, versioned artifact and the
product surface of the headless core: archive frontends and the `rekolekt-web`
kit generate their clients and types from it. `make verify` regenerates the
document with `scripts/generate_openapi.py` and fails on drift; run
`make openapi` after an API change and commit the result.

Field-level deprecations are marked `deprecated: true` in the schema. The field
keeps being served with its existing meaning until a removal follows the policy
above. The `SiteConfig.theme` object (`BrandTheme.font`, `BrandTheme.dark`,
`BrandTheme.light`) is deprecated this way: existing frontends keep receiving it,
and new frontends should own their styling.
