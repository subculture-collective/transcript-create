# Testing

**Status:** shipped and authoritative (2026-09-19).

Tests are organized by the behavior they can prove:

| Suite | Location | Responsibility |
| --- | --- | --- |
| Backend unit and route tests | `tests/` | domain rules, authorization, persistence contracts, migrations and failure handling |
| Backend workflow tests | `tests/integration/` | multi-step API and worker behavior against disposable services |
| Frontend component tests | `frontend/src/tests/` | rendering, state, accessibility and API interaction |
| Browser journeys | `e2e/tests/` | critical user flows through the built application and seeded database |

Write tests around observable behavior and meaningful failure modes. A test should fail
when its contract breaks; collection checks, unconditional assertions and assertions that
accept every possible result do not belong in the suite. Prefer one table-driven test when
several cases exercise the same path. Keep separate cases when they protect different
security, migration, recovery or accessibility boundaries.

Useful focused commands are:

```bash
.venv/bin/python -m pytest -q tests/test_routes_favorites.py
.venv/bin/python -m pytest -q tests/worker/test_formatter.py
npm --prefix frontend test -- --run src/tests/YouTubePlayer.test.tsx
PLAYWRIGHT_PORT=55173 npm --prefix e2e run test:critical -- --workers=4
```

The canonical repository gate is:

```bash
TEST_POSTGRES_PORT=55433 mise exec node@20 -- \
  env PYTHON_BIN="$PWD/.venv/bin/python" make verify
```

It starts isolated PostgreSQL, Redis and OpenSearch services, applies the complete Alembic
history, then runs compile checks, Ruff, Black, isort, the mypy baseline, pytest coverage,
Bandit, dependency audits, generated API drift checks, ESLint, Prettier, TypeScript,
Vitest coverage, the production build, bundle budgets, documentation validation and the
seeded Chromium journey. Services and volumes are removed afterward.

Backend application coverage must remain at least 70%. Frontend line, function and
statement coverage must remain at least 65%, with branch coverage at least 50%. These are
minimum regression gates, not targets; new behavior still needs tests for its important
success and failure paths. Environment-dependent tests may skip only when the named
external capability is genuinely optional. The canonical Compose gate supplies the
database and cache services expected by the main suite.

Chromium runs on each change. Firefox, WebKit, Mobile Chrome and Mobile Safari form the
nightly and pre-release matrix. Release validation also verifies image digests and Cosign
signatures and attestations. Restore, ingress, moderated-testing and private-beta evidence
remain separate gates in the [private-beta runbook](../deployment/private-beta.md).
