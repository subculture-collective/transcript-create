# Testing

**Status:** shipped and authoritative (2026-10-03).

Tests are organized by the behavior they can prove:

| Suite | Location | Responsibility |
| --- | --- | --- |
| Backend unit and route tests | `tests/` | domain rules, authorization, persistence contracts, migrations and failure handling |
| Backend workflow tests | `tests/integration/` | multi-step API and worker behavior against disposable services |
| API contract | `docs/api/openapi.json` | the committed OpenAPI document must match the running application |

Core is headless, so it has no component or browser tests. Each archive frontend owns its
own UI and browser tests; the former Playwright suite is preserved on the `rekolekt-web`
`archive/reference-app-ae1cc82` branch.

Write tests around observable behavior and meaningful failure modes. A test should fail
when its contract breaks; collection checks, unconditional assertions and assertions that
accept every possible result do not belong in the suite. Prefer one table-driven test when
several cases exercise the same path. Keep separate cases when they protect different
security, migration or recovery boundaries.

Useful focused commands are:

```bash
.venv/bin/python -m pytest -q tests/test_routes_favorites.py
.venv/bin/python -m pytest -q tests/worker/test_formatter.py
make openapi-check PYTHON_BIN=.venv/bin/python
```

The canonical repository gate is:

```bash
PYTHON_BIN="$PWD/.venv/bin/python" make verify
```

It validates documentation, starts isolated PostgreSQL, Redis and OpenSearch services,
applies the complete Alembic history, then runs compile checks, Ruff, Black, isort, the
mypy baseline, pytest coverage, Bandit, pip-audit, and the OpenAPI drift check
(`scripts/check_api_contracts.sh`). Services and volumes are removed afterward. Hosted CI
(`.gitea/workflows/verify.yaml`) runs the same `make verify`.

Backend application coverage must remain at least 70%. This is a
minimum regression gate, not targets; new behavior still needs tests for its important
success and failure paths. Environment-dependent tests may skip only when the named
external capability is genuinely optional. The canonical Compose gate supplies the
database and cache services expected by the main suite.

Release validation reruns `make verify`, then verifies image digests and Cosign signatures
and attestations. Restore, ingress, moderated-testing and private-beta evidence
remain separate gates in the [private-beta runbook](../deployment/private-beta.md).
