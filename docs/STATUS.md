# Documentation status

**Status:** authoritative index (2026-07-23).

| Status | Meaning |
| --- | --- |
| Shipped | matches current runtime and verification |
| Experimental | present but not a compatibility promise |
| Disabled | intentionally unavailable |
| Planned | future possibility, no current contract |
| Historical | retained context, not operational guidance |
| Superseded | replaced by an identified canonical document |

Authoritative shipped documents are README, architecture, testing, API
reference/OpenAPI, access matrix, migrations, deployment matrix, design system,
accessibility, authentication, API versioning, operations runbooks, and the
[review traceability ledger](review-traceability.md). The production release
candidate is additionally governed by the [private-beta deployment
runbook](deployment/private-beta.md) and [moderated testing and beta
protocol](user-testing/private-beta.md). Their operator and human evidence gates
remain pending until explicitly recorded; documentation does not imply that a
beta or public release has been approved.

Release automation is hosted by Gitea Actions at
`.gitea/workflows/release.yaml`. GitHub/GHCR release publication is not an
authoritative HasanAra path.

Public donation support through a validated Stripe-hosted Payment Link is **shipped** without introducing product billing or card-data handling. Billing, subscriptions, payment webhooks, and PWA/offline support remain **disabled**. Review reports and implementation summaries are **historical** after their findings enter the remediation plan. Older deployment/provider guides are **superseded** by `docs/deployment/README.md` unless explicitly revalidated.
