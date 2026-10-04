# Architecture

**Status:** shipped and authoritative (2026-10-03).

Rekolekt core is headless: it ships backend services and the HTTP API, and no web pages. The committed OpenAPI document is the contract with frontends. Each archive builds its own frontend on its own origin; the `rekolekt-web` kit supplies an API client, generated types, hooks and stylable default components. Search snippets are plain text with Unicode code-point highlight ranges, so a frontend can render highlights without trusting HTML.

FastAPI exposes the stable `/api` contract. PostgreSQL is the source of truth. Redis stores versioned JSON DTOs only. OpenSearch is an optional read accelerator maintained by a transactional PostgreSQL outbox; classified outages fall back to PostgreSQL and expose degraded/freshness metadata.

API and worker dependencies/images are separate. Workers claim durable leases, renew heartbeats, record attempts, and use compare-and-set finalization. Network and GPU work occurs outside database transactions.

Authentication uses server-side sessions. Authorization policy centralizes roles, capabilities, entitlements, vocabulary ownership, and API-key scopes. Analytics uses a separate random cookie and stores only an HMAC-derived subject.
