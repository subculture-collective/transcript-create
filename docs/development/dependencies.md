# Dependency Management Guide

This document provides comprehensive guidelines for managing dependencies in transcript-create, including automated updates, security patching, and version policies.

## Table of Contents

- [Overview](#overview)
- [Automated Dependency Updates](#automated-dependency-updates)
- [Adding New Dependencies](#adding-new-dependencies)
- [Updating Dependencies](#updating-dependencies)
- [Security Patch Handling](#security-patch-handling)
- [Version Policy](#version-policy)
- [Dependency Freshness Monitoring](#dependency-freshness-monitoring)
- [Testing Updates](#testing-updates)
- [Breaking Changes](#breaking-changes)
- [Troubleshooting](#troubleshooting)

## Overview

transcript-create uses multiple dependency management systems:

- **Python (pip)**: API and worker backend dependencies
- **npm**: Frontend, E2E tests, and SDK dependencies
- **Docker**: Base images for containerized deployments
- **GitHub Actions**: CI/CD workflow actions

All dependencies are managed with automated updates via Dependabot and manual security monitoring.

## Automated Dependency Updates

### Dependabot Configuration

Dependabot is configured in `.github/dependabot.yml` to automatically create pull requests for dependency updates.

#### Update Schedule

| Ecosystem | Frequency | Day | Time (UTC) | PR Limit |
|-----------|-----------|-----|------------|----------|
| Python (pip) | Weekly | Monday | 09:00 | 10 |
| npm (all) | Weekly | Monday | 09:00 | 5-10 |
| Docker | Monthly | Monday | 09:00 | 3 |
| GitHub Actions | Monthly | Monday | 09:00 | 5 |

#### Grouping Strategy

To reduce PR noise, Dependabot groups updates:

- **Patch updates**: All patch version updates (e.g., 1.2.3 → 1.2.4) are grouped
- **Minor updates**: All minor version updates (e.g., 1.2.0 → 1.3.0) are grouped
- **Major updates**: Each major version update gets a separate PR for careful review

#### Labels and Reviewers

All Dependabot PRs are automatically labeled for easy filtering:

- `dependencies`: All dependency updates
- `python`: Python packages
- `javascript`: npm packages
- `docker`: Docker images
- `ci`: GitHub Actions
- `frontend`, `testing`, `sdk`, `tooling`: Specific subsystems

Maintainer `@onnwee` is automatically assigned as reviewer for Python, Docker, and frontend PRs.

### How Dependabot PRs Work

1. **Creation**: Dependabot scans for updates weekly/monthly and opens PRs
2. **CI Validation**: All PRs automatically trigger CI workflows
3. **Security Scanning**: Automated security scans run on all PRs
4. **Review**: Maintainers review changelog and test results
5. **Merge**: If tests pass and changes are acceptable, PR is merged
6. **Deployment**: Changes are deployed with the next release

### Reviewing Dependabot PRs

When reviewing a Dependabot PR:

1. **Check CI Status**: Ensure all tests pass
2. **Review Changelog**: Read the linked release notes for breaking changes
3. **Check Compatibility**: Verify compatibility with other dependencies
4. **Test Locally**: For major updates, test locally before merging
5. **Merge or Postpone**: Merge if safe, or postpone with a comment explaining why

## Adding New Dependencies

### Python Dependencies

#### Production Dependencies (requirements.txt)

1. **Choose the right package**:
   ```bash
   # Research alternatives
   pip search <package-name>
   # Check PyPI for package health: https://pypi.org/project/<package>
   ```

2. **Check security status**:
   ```bash
   # Use the gh-advisory-database tool (run automatically in CI)
   # Or manually check: https://github.com/advisories
   ```

3. **Install and pin exact version**:
   ```bash
   pip install <package>==<version>
   ```

4. **Add to requirements.txt** with pinned version:
   ```txt
   # Add with a comment explaining purpose
   # Example: PDF generation
   reportlab==4.4.4
   ```

5. **Update constraints.txt**:
   ```bash
   # In a clean virtual environment
   python3 -m venv /tmp/venv-deps
   source /tmp/venv-deps/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   pip freeze > constraints.txt
   deactivate
   ```

6. **Test the change**:
   ```bash
   # Run tests
   pytest
   
   # Run security scans
   pip-audit -r requirements.txt
   bandit -r app/ worker/
   ```

7. **Document why**: If the dependency is not obvious, add a comment in requirements.txt

#### Development Dependencies (requirements-dev.txt)

For testing, linting, or development-only tools:

1. Add to `requirements-dev.txt` with pinned version
2. Follow the same security checking process
3. No need to update constraints.txt (production only)

### npm Dependencies

#### Frontend Dependencies

1. **Navigate to frontend directory**:
   ```bash
   cd frontend
   ```

2. **Install with exact version**:
   ```bash
   # For production dependencies
   npm install --save-exact <package>@<version>
   
   # For dev dependencies
   npm install --save-exact --save-dev <package>@<version>
   ```

3. **Verify package-lock.json** is updated

4. **Run tests**:
   ```bash
   npm run test
   npm run lint
   npm run build
   ```

5. **Commit both package.json and package-lock.json**

#### Other npm Projects (e2e, SDK, root)

Follow the same process in the respective directory.

### Docker Base Images

Docker base images are defined in Dockerfiles:

- `Dockerfile` (ROCm/AMD GPU)
- `Dockerfile.cuda` (CUDA/NVIDIA GPU)
- `Dockerfile.cpu` (CPU-only)

**To update base image**:

1. **Choose specific tag** (never use `latest`):
   ```dockerfile
   # Good: specific version
   FROM rocm/dev-ubuntu-22.04:6.0.2
   
   # Bad: moving target
   FROM rocm/dev-ubuntu-22.04:latest
   ```

2. **Test build**:
   ```bash
   docker compose build
   ```

3. **Test runtime**:
   ```bash
   docker compose up -d
   docker compose logs -f worker
   ```

4. **Update related dependencies** (e.g., PyTorch ROCm wheels)

### GitHub Actions

Actions are defined in `.github/workflows/*.yml` files.

**To add new action**:

1. **Pin to major version** with SHA for security:
   ```yaml
   # Recommended: major version + SHA
   - uses: actions/checkout@v4.2.0
     # SHA: a1b2c3d...
   
   # Also acceptable: major version only (Dependabot will update)
   - uses: actions/checkout@v4
   ```

2. **Test workflow**:
   - Push to a branch
   - Verify workflow runs successfully in GitHub Actions

## Updating Dependencies

### Regular Updates

Dependabot handles most updates automatically. For manual updates:

#### Python

```bash
# Update specific package
pip install --upgrade <package>==<new-version>

# Update requirements.txt
pip freeze | grep <package> >> requirements.txt

# Regenerate constraints.txt
python3 -m venv /tmp/venv-deps
source /tmp/venv-deps/bin/activate
pip install -r requirements.txt
pip freeze > constraints.txt
```

#### npm

```bash
cd frontend  # or e2e, clients/javascript, etc.

# Update specific package
npm install <package>@<new-version>

# Update all packages (respecting semver ranges)
npm update

# Check for outdated packages
npm outdated
```

#### Docker

Update version in Dockerfile, then rebuild:

```bash
docker compose build --no-cache
docker compose up -d
docker compose logs -f
```

### Testing Updates

**Before merging any dependency update**:

1. **Run all tests**:
   ```bash
   # Python tests
   pytest
   
   # Frontend tests
   cd frontend && npm run test
   
   # E2E tests
   cd e2e && npm run test
   
   # Integration tests
   docker compose up -d
   # Run integration test suite
   ```

2. **Run security scans**:
   ```bash
   # Python
   pip-audit -r requirements.txt
   bandit -r app/ worker/
   
   # npm (if vulnerabilities exist)
   npm audit
   ```

3. **Build Docker images**:
   ```bash
   docker compose build
   ```

4. **Manual smoke testing**:
   - Start the application
   - Create a test job
   - Verify transcription works
   - Check logs for errors

## Security Patch Handling

### Security Advisory Response SLA

| Severity | Response Time | Action Required |
|----------|---------------|-----------------|
| **CRITICAL** | 24 hours | Immediate patch, emergency release |
| **HIGH** | 7 days | Prioritized patch, expedited release |
| **MEDIUM** | 30 days | Regular update cycle |
| **LOW** | Next release | Include in next scheduled release |

### Security Advisory Workflow

1. **Notification**:
   - GitHub Security Advisories (enabled)
   - Dependabot alerts (enabled)
   - Weekly security-audit.yml workflow runs
   - Email notifications to maintainers

2. **Assessment**:
   - Review advisory details
   - Determine impact on transcript-create
   - Check if vulnerability is exploitable in our usage
   - Classify severity (may differ from upstream)

3. **Patching**:
   - Create emergency branch: `security/CVE-YYYY-XXXXX`
   - Update affected dependency
   - Run security scans to verify fix
   - Run full test suite
   - Create PR with `security` label

4. **Deployment**:
   - Merge to main after tests pass
   - Trigger immediate deployment
   - Create security release notes
   - Notify users if action required

5. **Documentation**:
   - Update CHANGELOG.md with security fix
   - Document workarounds if any
   - Update SECURITY.md if relevant

### Manual Security Scanning

Run security scans locally:

```bash
# Python dependency vulnerabilities
pip-audit -r requirements.txt --desc

# Python code security issues
bandit -r app/ worker/ -ll

# Check for secrets
gitleaks detect --source . -v

# npm audit (in each npm directory)
cd frontend && npm audit
cd ../e2e && npm audit
cd ../clients/javascript && npm audit
```

### Handling False Positives

If a security advisory doesn't apply:

1. Document why in a comment
2. Create an ignore rule if needed
3. Monitor for future updates
4. Re-evaluate on next dependency update

## Version Policy

### Semantic Versioning

We follow [Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH):

- **PATCH** (1.2.3 → 1.2.4): Bug fixes, security patches (safe to auto-merge)
- **MINOR** (1.2.0 → 1.3.0): New features, backward compatible (review changelog)
- **MAJOR** (1.0.0 → 2.0.0): Breaking changes (test thoroughly, plan migration)

### Pinning Strategy

| Dependency Type | Strategy | Rationale |
|-----------------|----------|-----------|
| Python (requirements.txt) | Exact version (==) | Reproducible builds, security auditing |
| Python (requirements-dev.txt) | Exact version (==) | Consistent dev environments |
| npm (package.json) | Caret (^) or exact | Balance flexibility and stability |
| Docker base images | Specific tag | Immutable infrastructure |
| GitHub Actions | Major version (@v4) | Security + compatibility |

### Compatibility Guarantees

- **Python**: Minimum Python 3.12
- **Node.js**: Minimum Node.js 18 LTS
- **Docker**: Docker Compose v2
- **Browsers** (frontend): Last 2 versions of major browsers

### Deprecation Policy

When deprecating dependencies:

1. Announce in release notes (MINOR version)
2. Provide migration guide
3. Mark as deprecated (MINOR version)
4. Remove in next MAJOR version
5. Keep documentation for 2 major versions

## Dependency Freshness Monitoring

### Tracking Metrics

Monitor dependency health with these metrics:

1. **Version lag**: How far behind latest versions
2. **Security lag**: Time since last security patch
3. **Outdated count**: Number of outdated dependencies
4. **Abandoned packages**: Dependencies with no updates in >1 year

### Manual Checks

#### Python

```bash
# List all outdated packages
pip list --outdated

# Check for newer versions
pip install pip-review
pip-review
```

#### npm

```bash
# Check outdated packages
npm outdated

# Or use npm-check-updates
npx npm-check-updates
```

### Automated Monitoring

- **Dependabot**: Weekly scans and automatic PRs
- **Security workflows**: Weekly security-audit.yml runs
- **Dependency dashboard**: View in GitHub Insights → Dependency graph

### Target Goals

- ✅ 90% of dependencies up-to-date (patch versions)
- ✅ Zero known HIGH/CRITICAL vulnerabilities
- ✅ <7 day response time to security updates
- ✅ All dependencies updated at least once per quarter

## Testing Updates

### Automated Testing

All Dependabot PRs automatically trigger:

1. **Backend CI** (`.github/workflows/backend-ci.yml`):
   - Python linting (ruff, black, isort, mypy)
   - Unit tests (pytest)
   - Security scans (bandit, pip-audit)

2. **Frontend CI** (`.github/workflows/frontend-ci.yml`):
   - TypeScript compilation
   - ESLint
   - Unit tests (vitest)
   - Build verification

3. **Integration Tests** (`.github/workflows/integration-tests.yml`):
   - Docker compose build
   - API integration tests
   - Worker pipeline tests

4. **E2E Tests** (`.github/workflows/e2e-tests.yml`):
   - Playwright browser tests
   - Full user workflows

### Manual Testing Checklist

For major updates or security patches, test manually:

- [ ] Application starts successfully
- [ ] API endpoints respond correctly
- [ ] Job creation works
- [ ] Worker processes videos
- [ ] Transcription completes
- [ ] Frontend loads and functions
- [ ] Authentication works
- [ ] Export features work
- [ ] No errors in logs

### Staging Environment

Test updates in staging before production:

1. Deploy to staging environment
2. Run smoke tests
3. Monitor for 24 hours
4. Check error rates and performance
5. Deploy to production if stable

## Breaking Changes

### Identifying Breaking Changes

Review changelogs for these indicators:

- Major version bumps (1.x → 2.x)
- "BREAKING CHANGE" in release notes
- Removal of deprecated features
- API changes requiring code updates
- Configuration format changes

### Handling Breaking Changes

1. **Plan Migration**:
   - Read migration guide from upstream
   - Identify affected code
   - Estimate effort and risk

2. **Create Migration Branch**:
   ```bash
   git checkout -b feature/migrate-<package>-v<version>
   ```

3. **Update Code**:
   - Make necessary changes
   - Update tests
   - Update documentation

4. **Test Thoroughly**:
   - Run full test suite
   - Manual testing of affected features
   - Performance testing if relevant

5. **Document Changes**:
   - Update CHANGELOG.md
   - Update relevant documentation
   - Add migration guide if needed

6. **Communicate**:
   - Notify team in PR
   - Update deployment runbook if needed
   - Mention in release notes

### Rollback Plan

Before deploying breaking changes:

1. Document current state
2. Tag release before changes
3. Have rollback commands ready
4. Monitor deployment closely
5. Be prepared to roll back if issues arise

## Troubleshooting

### Common Issues

#### Dependency Conflicts

**Symptom**: `pip install` fails with conflict errors

**Solution**:
```bash
# Check for conflicts
pip check

# See dependency tree
pip install pipdeptree
pipdeptree

# Try resolving with constraints
pip install -r requirements.txt -c constraints.txt
```

#### Build Failures After Update

**Symptom**: Docker build fails after dependency update

**Solution**:
```bash
# Clear build cache
docker compose build --no-cache

# Check for breaking changes in changelog
# Revert if necessary
git revert <commit>

# Or pin to working version
# Edit requirements.txt or package.json
```

#### Test Failures After Update

**Symptom**: Tests pass locally but fail in CI

**Solution**:
```bash
# Ensure consistent environment
# Regenerate constraints.txt
pip freeze > constraints.txt

# Clear npm cache
npm ci  # instead of npm install

# Check for timing issues in tests
pytest -v  # verbose output
```

#### Security Scan False Positives

**Symptom**: Security scan flags vulnerability that doesn't apply

**Solution**:
1. Document why it's a false positive
2. Add suppression if appropriate:
   ```bash
   # pip-audit
   pip-audit --ignore-vuln <VULN-ID>
   
   # bandit
   # Add # nosec comment in code
   ```
3. Report false positive upstream

#### Dependabot PRs Not Created

**Symptom**: No PRs from Dependabot for weeks

**Solution**:
1. Check Dependabot logs in GitHub Insights → Dependency graph
2. Verify `.github/dependabot.yml` syntax
3. Check if PRs are blocked by existing PRs
4. Ensure repository has Dependabot enabled in Settings

#### Merge Conflicts in Dependabot PRs

**Symptom**: Dependabot PR has conflicts

**Solution**:
```bash
# Dependabot can rebase automatically
# Comment on the PR:
# @dependabot rebase

# Or merge manually:
git checkout <dependabot-branch>
git rebase main
git push --force-with-lease
```

### Getting Help

For dependency-related issues:

1. **Check this guide** first
2. **Review docs/DEPENDENCIES.md** for technical details
3. **Search GitHub Issues** for similar problems
4. **Check CI logs** for detailed error messages
5. **Ask in Discussions** for community help
6. **Open an Issue** with:
   - Dependency versions
   - Error messages
   - Steps to reproduce
   - Environment details (Python version, Node version, OS)

## Related Documentation

- [Technical Dependency Details](../DEPENDENCIES.md) - Deep dive into dependency structure
- [Release Process](./release-process.md) - How releases are managed
- [Security Guide](../SECURITY_GUIDE.md) - Security best practices
- [Contributing Guidelines](../../CONTRIBUTING.md) - How to contribute

## References

- [Dependabot Documentation](https://docs.github.com/en/code-security/dependabot)
- [GitHub Security Advisories](https://docs.github.com/en/code-security/security-advisories)
- [Semantic Versioning](https://semver.org/)
- [pip-audit Documentation](https://github.com/pypa/pip-audit)
- [npm audit Documentation](https://docs.npmjs.com/cli/v8/commands/npm-audit)
