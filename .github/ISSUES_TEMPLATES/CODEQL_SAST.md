# [SEC/CI] Enable CodeQL (Python & JS)

Goal: Add GitHub CodeQL workflow for Python and JavaScript (frontend) scanning on pushes and PRs.

Steps:
1) Create .github/workflows/codeql.yml using GitHub's starter for languages: python, javascript.
2) Schedule weekly run with cron.
3) Configure minimal build steps for each language if needed; frontend may require setup-node and npm ci.
4) Upload SARIF results automatically (default in CodeQL action).
5) Document where to review alerts in repository Security tab.

Acceptance criteria:
- CodeQL workflow green and scanning both ecosystems.
- Alerts visible in Security tab; any baseline triaged.
- Runs on PRs to main and scheduled weekly.

Metadata:
- Milestone: M1 — Foundation & CI Ready
- Labels: type:security, type:ci, area:security, P0-blocker, status:ready
