# Deployment matrix

**Status:** shipped operational guidance (2026-10-03).

| Environment | Data/services | Verification | Exposure |
| --- | --- | --- | --- |
| Local | Compose PostgreSQL/Redis/OpenSearch | focused tests or `make verify` | localhost |
| Test | isolated Compose project and volumes | full `make verify` | none |
| Staging | production-shaped API/worker images | smoke, migration, restore, lag and lease checks | restricted HTTPS |
| Production | independent API/worker images; persistent Almaz mounts | release checklist and monitoring | public HTTPS |

Private-beta deployment is governed by the fail-closed [private-beta runbook](private-beta.md) and its evidence packet. It requires external invite-only ingress proof, a separate staging restore rehearsal, immutable image digests, and explicit operator decisions.

Deploy in order: backup and restore-test; additive migrations; analytics scrub/session rotation when applicable; API/worker images; then the archive frontend if its API use changed; search outbox backfill/count comparison; enable OpenSearch primary; verify CSP, cache headers, health, lag, leases, rejected events, and errors.

Application images may roll back independently while additive migrations remain compatible. Never roll back across the analytics credential-scrub boundary to token-writing code.

Core is headless: the release publishes backend role images only (`api`, `ingest-cuda`, `ml-cuda`, `postgres-walg`, plus the pinned third-party `redis`). Each archive builds, hosts and deploys its own frontend outside the core Compose project and points `FRONTEND_ORIGIN` at it. The former bundled frontend's `/sw.js` retirement worker now lives with the reference app on the `rekolekt-web` `archive/reference-app-ae1cc82` branch; an archive replacing that frontend should keep serving it for one release if its users had the old PWA worker installed.

## Client branding

See [client branding and shared core updates](client-branding.md) for independent deployments using the same core release.
