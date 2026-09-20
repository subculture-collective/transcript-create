# Documentation index

**Status:** authoritative index (2026-09-19).

Use this index to distinguish maintained contracts from optional deployment guides. Dated
audit exports, implementation plans, screenshots and completion reports are intentionally
excluded from the repository; Git history retains them when historical context is needed.

| Area | Maintained entry points |
| --- | --- |
| Product overview | [README](../README.md) |
| Architecture and development | [architecture](development/architecture.md), [setup](development/setup.md), [testing](development/testing.md), [transcript processing](development/transcript-processing.md) |
| API and authorization | [API reference](api-reference.md), [generated OpenAPI](api/openapi.json), [versioning](api/versioning.md), [access matrix](access-matrix.md), [authentication](authentication.md) |
| Branding and releases | [client branding](deployment/client-branding.md), [deployment matrix](deployment/README.md), [release process](development/release-process.md) |
| Database and operations | [migrations](MIGRATIONS.md), [operations](operations/README.md), [production readiness](operations/production-readiness.md), [backup operations](operations/backup-operations.md) |
| Product contracts | [passage sharing](product/passage-sharing.md), [creator community](product/creator-community.md), [authorized clips](product/authorized-original-clips.md) |
| Interface | [design system](DESIGN_SYSTEM.md), [accessibility](ACCESSIBILITY.md) |

The [private-beta runbook](deployment/private-beta.md) and [moderated testing
protocol](user-testing/private-beta.md) describe evidence required for an actual release.
Their presence does not indicate that a client deployment has passed those gates.

Release automation is hosted by Gitea Actions in `.gitea/workflows/release.yaml`. Product
billing, subscriptions, payment webhooks and offline/PWA installation remain disabled.
