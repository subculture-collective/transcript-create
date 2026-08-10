# Deployment matrix

**Status:** shipped operational guidance (2026-07-12).

| Environment | Data/services | Verification | Exposure |
| --- | --- | --- | --- |
| Local | Compose PostgreSQL/Redis/OpenSearch | focused tests or `make verify` | localhost |
| Test | isolated Compose project and volumes | full `make verify` | none |
| Staging | production-shaped API/frontend/worker images | smoke, migration, restore, lag and lease checks | restricted HTTPS |
| Production | independent API/frontend/worker images; persistent Almaz mounts | release checklist and monitoring | public HTTPS |

Private-beta deployment is governed by the fail-closed [private-beta runbook](private-beta.md) and its evidence packet. It requires external invite-only ingress proof, a separate staging restore rehearsal, immutable image digests, and explicit operator decisions.

Deploy in order: backup and restore-test; additive migrations; analytics scrub/session rotation when applicable; API/frontend/worker images; search outbox backfill/count comparison; enable OpenSearch primary; verify CSP, cache headers, health, lag, leases, rejected events, and errors.

Application images may roll back independently while additive migrations remain compatible. Never roll back across the analytics credential-scrub boundary to token-writing code.

The frontend currently ships a one-release `/sw.js` retirement worker. It deletes legacy cache-first PWA storage, unregisters itself, and reloads controlled windows; the application does not register a new worker. Keep the retirement asset available for one release, then remove it after previously controlled clients have upgraded.
