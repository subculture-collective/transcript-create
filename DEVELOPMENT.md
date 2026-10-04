> For the product overview, see the [README](README.md).

# Transcript Archive

Transcript Archive is a configurable, citation-first application for long-form
recordings. It ingests videos, stores timestamped transcripts, supports full-text search
and archive browsing, and lets people save and share passages with their source context.

This repository is the headless core: backend services and the HTTP API, with no web
pages. The API contract, committed at [`docs/api/openapi.json`](docs/api/openapi.json),
is the product surface. Each archive builds and owns its whole frontend on another origin
and supplies a versioned public profile while running the same backend images.

Frontends live with the archives. The
[`rekolekt-web`](https://git.subcult.tv/subculture-collective/rekolekt-web) kit
(`@subcult/rekolekt-web`) provides the API client, generated OpenAPI types, hooks and
stylable default components, with no pages. The designed application and Playwright
suite that used to live under `frontend/` and `e2e/` are preserved on its
`archive/reference-app-ae1cc82` branch.

## Application stack

- FastAPI application and worker services
- PostgreSQL as the source of truth
- Redis for caches and coordination
- Optional OpenSearch acceleration with PostgreSQL fallback
- Docker Compose, Kubernetes, Helm, Ansible and Terraform deployment assets

The core includes durable ingestion jobs, scoped API keys, OAuth accounts, saved searches
and moments, pseudonymous analytics, archive intelligence, passage sharing, and an
optional creator community. Client-facing features remain controlled by server settings;
the public branding profile does not grant entitlements or contain secrets.

## Local development

Supported versions are Python 3.11 and Docker with Compose.

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION=true docker compose up --build db redis migrations api
```

The API defaults to `http://localhost:8000`, with interactive API documentation at
`/docs`. `FRONTEND_ORIGIN` names the origin of the frontend you develop against (for
example a `rekolekt-web` app on `http://localhost:5173`); the API uses it for CORS,
CSRF and cookies. The migration
opt-in above is for a fresh controlled bootstrap. Follow the migration runbook for an
existing deployment.

The main source areas are:

| Path | Purpose |
| --- | --- |
| `app/` | FastAPI routes, domain services, persistence and schemas |
| `worker/` | ingestion, transcription, formatting and background processing |
| `docs/api/openapi.json` | committed OpenAPI contract; regenerate with `make openapi` |
| `landing/` | static Rekolekt product page, deployed separately |
| `alembic/` | ordered database migrations |
| `config/branding/` | profile schema and safe example client configuration |
| `clients/` | client release-profile validation and planning code |
| `scripts/` | maintained verification, migration and operator utilities |

## Branding and client updates

Start with the [Northstar example profile](config/branding/northstar.json), validate its
fields against the [profile schema](config/branding/schema.json), and supply it through
`SITE_PROFILE_PATH`. The API serves it at `/site`. Store client secrets, infrastructure
and release history outside the public profile.

The [client branding guide](docs/deployment/client-branding.md) describes the profile
fields, the deprecated theme tokens, profile precedence, and the fleet update planner. The planner combines a
verified digest-pinned release manifest with a client inventory and produces reviewable
Compose overrides. It never edits client profiles, databases or secrets and does not
perform a deployment.

## Verification

Run focused tests while developing, then run the canonical gate before delivery:

```bash
PYTHON_BIN="$PWD/.venv/bin/python" make verify
```

The gate starts disposable PostgreSQL, Redis and OpenSearch services; applies every
migration; checks Python quality, the mypy baseline and backend coverage; validates
documentation; audits Python dependencies; and regenerates the OpenAPI document to fail
on drift from `docs/api/openapi.json`. After an API change, run `make openapi` and commit
the regenerated file. See the
[testing guide](docs/development/testing.md) for focused commands, suite ownership and
coverage expectations.

## Documentation

- [Architecture](docs/development/architecture.md) and [transcript processing](docs/development/transcript-processing.md)
- [API reference](docs/api-reference.md), generated [OpenAPI](docs/api/openapi.json), and [access matrix](docs/access-matrix.md)
- [Client branding and shared updates](docs/deployment/client-branding.md)
- [Passage-sharing contract](docs/product/passage-sharing.md)
- [Deployment matrix](docs/deployment/README.md) and [production readiness](docs/operations/production-readiness.md)
- [Database migrations](docs/MIGRATIONS.md)
- [Documentation index](docs/STATUS.md)

`/api` is v1-stable: changes are additive, deprecations remain for at least two releases,
and breaking changes require `/api/v2`.

[Apache-2.0 license](LICENSE) · [third-party notices](docs/THIRD_PARTY_NOTICES.md)
