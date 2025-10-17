# [CI] Python lint, typecheck, tests with coverage gate

Goal: Ensure PRs run ruff/black check, mypy, and pytest with coverage. Cache dependencies. Fail when coverage < 70% initially.

Context:
- Python backend/worker (FastAPI + SQLAlchemy Core + worker pipeline)
- requirements.txt present; using pytest
- No code changes required for this issue, only CI configuration and minimal test skeletons if missing.

Steps:
1) Create GitHub Actions workflow .github/workflows/ci-python.yml that runs on PR and push to main.
2) Jobs:
   - Setup Python 3.11; cache pip.
   - Install dependencies with pip using requirements.txt; install dev tools: ruff, black, mypy, pytest, pytest-cov.
   - Run ruff and black (check mode) across app/, worker/, scripts/.
   - Run mypy across app/ and worker/ with strictness level appropriate (start with basic typing; do not block on third-party stubs missing — use ignore-missing-imports).
   - Run pytest with coverage and generate XML.
   - Enforce minimum coverage 70% (config in pytest.ini or via coverage thresholds). Output a summary artifact.
3) Add status checks requirement: document in repo settings.
4) Add badges to README (will be separate issue).

Acceptance criteria:
- Workflow green on main; red on coverage < 70%.
- Caching effective across runs.
- mypy runs without failing due to third-party missing stubs (use ignore-missing-imports initially).
- Lint and formatting checks run and enforce style.

Deliverables:
- .github/workflows/ci-python.yml with the above steps.
- Optional: pytest.ini to set coverage fail-under.

Links:
- Project: Transcript Create Roadmap
- Milestone: M1 — Foundation & CI Ready
- Labels: type:ci, type:test, area:ci-cd, P0-blocker, status:ready
