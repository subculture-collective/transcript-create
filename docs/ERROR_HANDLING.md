# Error handling

**Status:** shipped baseline (2026-07-12).

FastAPI domain exceptions map authentication, authorization, validation, not-found, conflict, rate-limit, and infrastructure failures to stable responses. Database retries always roll back first. Search falls back only for classified OpenSearch outage/timeout failures; authentication, validation, and quota failures are never masked. Archive database failures return explicit unavailable states rather than empty results.

Explicit unavailable and degraded responses let archive frontends show loading, empty, unavailable and error states; the frontend behavior itself belongs to each archive. Logs must not contain credentials, session tokens, card-like values, or raw analytics identity.
