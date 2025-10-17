# [DEVX] Pre-commit hooks (ruff, black, isort, mypy)

Goal: Add pre-commit to standardize linting/formatting and type checks locally and in CI.

Steps:
1) Add .pre-commit-config.yaml including ruff, black, isort, mypy (using local hooks where needed).
2) Update README Contributing with install steps: pip install pre-commit && pre-commit install.
3) Add CI job to run pre-commit on PRs (or reuse CI Python job to invoke pre-commit).
4) Configure mypy with ignore-missing-imports initially.

Acceptance criteria:
- pre-commit runs locally and in CI; CI fails on violations.
- Docs updated with quickstart.

Metadata:
- Milestone: M1 — Foundation & CI Ready
- Labels: type:chore, area:devx, type:test, P1-high, status:ready
