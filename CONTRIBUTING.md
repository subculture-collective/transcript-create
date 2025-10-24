# Contributing to Transcript Create

Thank you for considering contributing to Transcript Create! This document provides guidelines and information about our development process.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Code Quality](#code-quality)
- [CI/CD Pipeline](#cicd-pipeline)
- [Pull Request Process](#pull-request-process)
- [Branch Protection Rules](#branch-protection-rules)

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Create a new branch for your feature or bug fix
4. Make your changes following our code quality guidelines
5. Run tests and linting locally
6. Push to your fork and submit a pull request

## Development Setup

### Backend Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development tools
pip install ruff black isort mypy pytest pre-commit

# Set up pre-commit hooks
pre-commit install
```

### Running Tests

#### Backend Tests

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Set up test database (PostgreSQL required)
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/postgres"
psql $DATABASE_URL -f sql/schema.sql

# Run all tests
pytest tests/

# Run tests with coverage
pytest tests/ --cov=app --cov-report=html --cov-report=term

# Run specific test file
pytest tests/test_routes_jobs.py -v

# View HTML coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

**Test Structure:**
- `tests/conftest.py` - Shared fixtures (database, test client)
- `tests/test_crud.py` - CRUD operation tests
- `tests/test_routes_*.py` - API endpoint tests
- `tests/test_schemas.py` - Pydantic model validation

See [tests/README.md](tests/README.md) for detailed testing documentation.

### Frontend Setup

```bash
cd frontend
npm install
```

### Running Locally

See the main [README.md](README.md) for detailed instructions on running the full stack with Docker Compose or individual services.

## Code Quality

We maintain high code quality standards through automated linting, formatting, and type checking.

### Python (Backend & Worker)

**Linting:**
```bash
# Check code quality
ruff check app/ worker/ scripts/

# Auto-fix issues
ruff check --fix app/ worker/ scripts/
```

**Formatting:**
```bash
# Check formatting
black --check app/ worker/ scripts/

# Auto-format
black app/ worker/ scripts/
```

**Import Sorting:**
```bash
# Check imports
isort --check-only app/ worker/

# Auto-sort imports
isort app/ worker/
```

**Type Checking:**
```bash
# Run type checks
mypy app/ worker/
```

**Configuration:**
- Line length: 120 characters
- Target Python version: 3.11+
- Configuration in `pyproject.toml`

### TypeScript (Frontend)

**Linting:**
```bash
cd frontend
npm run lint
```

**Formatting:**
```bash
cd frontend
# Check formatting
npm run format:check

# Auto-format
npm run format
```

**Type Checking:**
```bash
cd frontend
npx tsc --noEmit
```

**Building:**
```bash
cd frontend
npm run build
```

### Pre-commit Hooks

We use pre-commit hooks to catch issues before they're committed:

```bash
# Install hooks (one-time setup)
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

The hooks automatically run:
- **ruff**: Fast Python linter
- **black**: Code formatter
- **isort**: Import sorting
- **mypy**: Type checking
- **gitleaks**: Secret detection
- Additional checks for trailing whitespace, YAML/JSON/TOML syntax

## CI/CD Pipeline

All pull requests and pushes to main automatically trigger our CI/CD pipeline.

### Backend CI (`backend-ci.yml`)

Runs on changes to:
- `app/**`
- `worker/**`
- `*.py` files
- `requirements.txt`
- `pyproject.toml`

**Jobs:**
1. **Lint & Format Check** (Python 3.11, 3.12)
   - ruff check
   - black check
   - isort check
   - mypy type check (informational)

2. **Security Scan**
   - pip-audit (dependency vulnerabilities)
   - bandit (code security issues)

3. **Test with PostgreSQL**
   - Apply database schema
   - Run pytest suite with coverage
   - Generate coverage reports (XML, HTML, terminal)
   - Check 70%+ coverage threshold
   - Upload coverage artifacts
   - Add GitHub Actions summary with coverage stats

4. **Docker Build**
   - Build Docker image (CPU-compatible check)
   - Verify image builds successfully

### Frontend CI (`frontend-ci.yml`)

Runs on changes to:
- `frontend/**`

**Jobs:**
1. **Lint & Type Check** (Node 20, 22)
   - ESLint (informational - some errors pre-existing)
   - Prettier formatting (enforced)
   - TypeScript type check

2. **Build Verification**
   - Vite build
   - Bundle size check (warns if > 500KB)
   - Upload build artifacts

### Docker Build & Publish (`docker-build.yml`)

Runs on:
- Push to `main`
- Tags matching `v*`
- Manual workflow dispatch

**Features:**
- Builds Docker image with ROCm support
- Publishes to GitHub Container Registry (ghcr.io)
- Multiple tagging strategies (latest, semver, sha)
- Layer caching for fast rebuilds
- SBOM and provenance attestations
- Build time verification (target < 5 min with cache)

### Security Audit (`security-audit.yml`)

Runs on:
- Push/PR to main/develop (when dependency files change)
- Weekly schedule (Mondays at 9 AM UTC)
- Manual workflow dispatch

**Checks:**
- Dependency vulnerabilities (pip-audit, safety)
- Secret scanning (gitleaks)

## Pull Request Process

1. **Create a branch** from `main` with a descriptive name
   - Feature: `feature/description`
   - Bug fix: `fix/description`
   - Enhancement: `enhance/description`

2. **Make your changes**
   - Write clear, concise commit messages
   - Follow code quality guidelines
   - Add tests if applicable

3. **Test locally**
   ```bash
   # Backend
   pytest tests/
   ruff check app/ worker/
   black --check app/ worker/
   
   # Frontend
   cd frontend
   npm run lint
   npm run format:check
   npm run build
   ```

4. **Run pre-commit hooks**
   ```bash
   pre-commit run --all-files
   ```

5. **Push and create PR**
   - All CI checks must pass (see status badges on PR)
   - Provide clear description of changes
   - Link related issues

6. **Code Review**
   - Address reviewer feedback
   - Ensure all CI checks remain green

7. **Merge**
   - Once approved and all checks pass, maintainers will merge

## Branch Protection Rules

The `main` branch is protected with the following requirements:

### Required Status Checks

Before merging to `main`, the following checks must pass:

**Backend CI:**
- ✅ Lint & Format Check (Python 3.11)
- ✅ Lint & Format Check (Python 3.12)
- ✅ Security Scan
- ✅ Test with PostgreSQL
- ✅ Docker Build

**Frontend CI:**
- ✅ Lint & Type Check (Node 20)
- ✅ Lint & Type Check (Node 22)
- ✅ Build Verification

**Note:** Some checks use `continue-on-error: true` for informational warnings (mypy, ESLint some rules, security scans) that don't block merges but should be addressed when possible.

### Additional Requirements

- **Require branches to be up to date**: PRs must be rebased on latest main
- **Require pull request reviews**: At least one approving review from maintainers
- **Dismiss stale reviews**: New commits dismiss previous approvals
- **No force pushes**: Protect commit history
- **Linear history**: Prefer squash or rebase merges

### Workflow Timing

Our CI/CD is designed for fast feedback:
- **Target**: Most checks complete in < 5 minutes
- **Docker builds**: < 5 min with layer caching, < 15 min cold
- **Full test suite**: < 3 minutes

If checks take significantly longer, please report as an issue.

## Security

Please review [SECURITY.md](SECURITY.md) for:
- Reporting security vulnerabilities
- Secrets management guidelines
- Production security checklist
- Dependency update procedures

## Questions?

If you have questions or need help:
1. Check the [README.md](README.md) for project documentation
2. Search existing issues for similar questions
3. Open a new issue with the `question` label

Thank you for contributing! 🚀
