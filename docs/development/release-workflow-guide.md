# Release Workflow Quick Start Guide

This guide shows how to use the automated release management system.

## Prerequisites

1. Install Node.js dependencies (first time only):
```bash
npm install
```

2. Install pre-commit hooks (first time only):
```bash
pre-commit install
```

## Daily Development

### Making Commits

Follow [Conventional Commits](https://www.conventionalcommits.org/) format:

```bash
# Interactive prompt (recommended for beginners)
npm run commit

# Or write directly
git commit -m "feat: add new feature"
git commit -m "fix: resolve bug in audio processing"
git commit -m "docs: update API documentation"
```

**Commit Types:**
- `feat:` - New feature (→ MINOR version bump)
- `fix:` - Bug fix (→ PATCH version bump)
- `feat!:` or `BREAKING CHANGE:` - Breaking change (→ MAJOR version bump)
- `docs:`, `chore:`, `test:`, etc. - No version bump

### Pre-commit Validation

The pre-commit hook will automatically:
- Validate commit message format
- Run linters and formatters
- Check for secrets

If validation fails, fix the issues and try again.

## Creating a Release

### 1. Ensure Main is Ready

```bash
# Make sure you're on main and up to date
git checkout main
git pull origin main

# Verify all CI checks pass
# Check: https://github.com/subculture-collective/transcript-create/actions
```

### 2. Run standard-version

```bash
# Automatic version bump based on commits since last release
npm run release

# Or specify version type explicitly
npm run release:patch   # 0.1.0 → 0.1.1 (bug fixes)
npm run release:minor   # 0.1.0 → 0.2.0 (new features)
npm run release:major   # 0.1.0 → 1.0.0 (breaking changes)
```

This will:
- Analyze commits since last release
- Determine version bump (major/minor/patch)
- Update version in all files:
  - `pyproject.toml`
  - `package.json`
  - `frontend/package.json`
  - `clients/javascript/package.json`
  - `e2e/package.json`
- Update `CHANGELOG.md` with categorized changes
- Create a git commit with changes
- Create a git tag (but not push it)

### 3. Review Changes

```bash
# Review the changelog
cat CHANGELOG.md

# Check version updates
git diff HEAD~1

# If everything looks good, proceed to next step
# If not, reset and fix:
git reset --hard HEAD~1
git tag -d v0.2.0  # Delete the tag
# Fix issues and try again
```

### 4. Push to Trigger Release

```bash
# Push the commit and tag
git push --follow-tags

# Or separately
git push origin main
git push origin v0.2.0
```

### 5. GitHub Actions Takes Over

Once the tag is pushed, GitHub Actions will automatically:

1. **Create GitHub Release**
   - Extract release notes from CHANGELOG.md
   - Create release at: https://github.com/subculture-collective/transcript-create/releases

2. **Build & Push Docker Images**
   - Build ROCm-enabled Docker image
   - Tag with multiple versions:
     - `ghcr.io/subculture-collective/transcript-create:v0.2.0` (exact)
     - `ghcr.io/subculture-collective/transcript-create:0.2.0` (no v)
     - `ghcr.io/subculture-collective/transcript-create:0.2` (minor)
     - `ghcr.io/subculture-collective/transcript-create:0` (major)
     - `ghcr.io/subculture-collective/transcript-create:latest` (for stable releases)

3. **Notify**
   - Workflow completion notification

Monitor progress: https://github.com/subculture-collective/transcript-create/actions

## Pre-release Versions

For alpha, beta, or release candidate versions:

```bash
# First release candidate for 1.0.0
npm run release -- --prerelease rc
# Creates v1.0.0-rc.0

# Next release candidate
npm run release -- --prerelease rc
# Creates v1.0.0-rc.1

# Alpha release
npm run release -- --prerelease alpha
# Creates v1.0.0-alpha.0

# Beta release
npm run release -- --prerelease beta
# Creates v1.0.0-beta.0
```

Pre-releases:
- Are marked as "pre-release" on GitHub
- Do NOT update the `latest` Docker tag
- Are useful for testing before stable release

## Hotfix Process

For urgent fixes to production:

```bash
# 1. Branch from the release tag
git checkout -b hotfix/v1.2.1 v1.2.0

# 2. Make the fix
git commit -m "fix: critical security vulnerability"

# 3. Run standard-version for patch
npm run release:patch

# 4. Merge to main
git checkout main
git merge hotfix/v1.2.1

# 5. Push with tag
git push --follow-tags
```

## Troubleshooting

### Commit message rejected

```
✖   subject may not be empty [subject-empty]
✖   type may not be empty [type-empty]
```

**Solution:** Use the correct format:
```bash
git commit -m "feat: your feature description"
```

Or use interactive mode:
```bash
npm run commit
```

### standard-version fails

```
Error: Could not get the commits
```

**Solution:** Ensure you have at least one previous tag, or use `--first-release`:
```bash
npm run release -- --first-release
```

### Want to undo a release

```bash
# Delete the local tag
git tag -d v0.2.0

# Reset the commit
git reset --hard HEAD~1

# If already pushed
git push origin :refs/tags/v0.2.0  # Delete remote tag
git push origin main --force  # Reset remote branch (⚠️ careful!)
```

### Docker image not building

Check the workflow status:
https://github.com/subculture-collective/transcript-create/actions/workflows/release.yml

Common issues:
- Dockerfile syntax errors
- Missing dependencies
- Build timeout

## Version Endpoint

Check the deployed version:

```bash
# Local
curl http://localhost:8000/version

# Production
curl https://api.yourapp.com/version
```

Returns:
```json
{
  "version": "0.2.0",
  "git_commit": "abc123def456",
  "build_date": "2025-10-29T19:00:00Z"
}
```

## Resources

- [Semantic Versioning](https://semver.org/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [standard-version docs](https://github.com/conventional-changelog/standard-version)
- [Full Release Process Guide](release-process.md)

## Questions?

- Check [CONTRIBUTING.md](../../CONTRIBUTING.md)
- Ask in GitHub Discussions
- Review [previous releases](https://github.com/subculture-collective/transcript-create/releases)
