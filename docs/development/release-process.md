# Release Process

This document outlines the versioning scheme, release procedures, and checklists for creating releases of Transcript Create.

## Table of Contents

- [Automated Release Process](#automated-release-process)
- [Versioning Scheme](#versioning-scheme)
- [Release Types](#release-types)
- [Release Checklist](#release-checklist)
- [Creating a Release](#creating-a-release)
- [Post-Release Tasks](#post-release-tasks)
- [Hotfix Releases](#hotfix-releases)
- [Docker Images](#docker-images)

## Automated Release Process

We use an automated release process powered by:

- **standard-version**: Automated versioning and CHANGELOG generation
- **Conventional Commits**: Structured commit messages for automatic version bumping
- **GitHub Actions**: Automated release workflow triggered on version tags

### Quick Release Guide

1. **Ensure commits follow Conventional Commits format** (enforced by pre-commit hooks)
2. **Create a release** using standard-version:

```bash
# Automatic version bump based on commits
npm run release

# Or specify version type
npm run release:patch   # Bug fixes (0.1.0 → 0.1.1)
npm run release:minor   # New features (0.1.0 → 0.2.0)
npm run release:major   # Breaking changes (0.1.0 → 1.0.0)
```

3. **Review and commit the changes**:

```bash
# standard-version will have updated:
# - CHANGELOG.md
# - pyproject.toml
# - package.json
# - frontend/package.json
# - clients/javascript/package.json
# - e2e/package.json

git push origin main
```

4. **Create and push the tag**:

```bash
# standard-version creates a tag but doesn't push it
git push --follow-tags
```

5. **GitHub Actions will automatically**:
   - Create a GitHub Release with changelog
   - Build and push Docker images with proper tags
   - Notify on completion

### What Gets Automated

✅ **Version bumping** across all package files  
✅ **CHANGELOG.md** generation from commit messages  
✅ **Git tagging** with semantic version  
✅ **GitHub Release** creation with notes  
✅ **Docker images** built and published  
✅ **Multiple image tags** (latest, semver, major, minor)

### Conventional Commits Reference

Your commits determine the version bump automatically:

- `feat:` → MINOR version (0.1.0 → 0.2.0)
- `fix:` → PATCH version (0.1.0 → 0.1.1)
- `feat!:` or `BREAKING CHANGE:` → MAJOR version (0.1.0 → 1.0.0)
- `docs:`, `chore:`, etc. → No version bump

See [CONTRIBUTING.md](../../CONTRIBUTING.md#commit-message-guidelines) for complete commit format guidelines.

## Versioning Scheme

We follow [Semantic Versioning (SemVer) 2.0.0](https://semver.org/):

```
MAJOR.MINOR.PATCH

Example: 1.2.3
```

### Version Components

- **MAJOR** (1.x.x): Incompatible API changes, breaking changes
- **MINOR** (x.2.x): New features, backward-compatible functionality
- **PATCH** (x.x.3): Bug fixes, backward-compatible patches

### Pre-release Versions

For pre-releases, append a pre-release identifier:

```
1.0.0-alpha.1    # Alpha release
1.0.0-beta.2     # Beta release
1.0.0-rc.1       # Release candidate
```

### Examples

```
0.1.0 → 0.2.0    # New feature (pre-1.0)
1.0.0 → 1.0.1    # Bug fix
1.0.1 → 1.1.0    # New feature
1.5.2 → 2.0.0    # Breaking change
```

## Release Types

### Major Release (x.0.0)

**When**: Breaking changes, major architectural changes, or major new features

**Examples**:
- Removing deprecated APIs
- Changing database schema incompatibly
- Changing authentication mechanism
- Major UI redesign

**Communication**: Announce widely, provide migration guide

### Minor Release (x.y.0)

**When**: New features, enhancements, backward-compatible changes

**Examples**:
- Adding new API endpoints
- New export formats
- New configuration options
- Performance improvements

**Communication**: Release notes, changelog update

### Patch Release (x.y.z)

**When**: Bug fixes, security patches, minor improvements

**Examples**:
- Fixing bugs
- Security updates
- Documentation corrections
- Dependency updates

**Communication**: Brief release notes

## Release Checklist

### Pre-Release Checks

#### Code Quality
- [ ] All CI/CD checks pass on main branch
- [ ] All tests pass (unit, integration, E2E)
- [ ] Code coverage meets threshold (70%+)
- [ ] No critical security vulnerabilities (run `pip-audit`, `npm audit`)
- [ ] Linting passes with no warnings

#### Documentation
- [ ] CHANGELOG.md updated with all changes
- [ ] README.md up to date
- [ ] API documentation reflects current endpoints
- [ ] Migration guides written (for breaking changes)
- [ ] Version numbers updated in relevant files

#### Database
- [ ] All database migrations tested
- [ ] Migrations work both upgrade and downgrade
- [ ] Migration documentation complete
- [ ] Backup/restore tested (for major releases)

#### Testing
- [ ] Manual testing on staging environment
- [ ] Docker images build successfully
- [ ] Kubernetes deployment tested (if applicable)
- [ ] Performance benchmarks acceptable
- [ ] Cross-browser testing (for frontend changes)

#### Dependencies
- [ ] Dependencies up to date
- [ ] No known vulnerabilities in dependencies
- [ ] License compatibility verified

### Release Preparation

#### 1. Create Release Branch

```bash
# For major/minor releases
git checkout main
git pull origin main
git checkout -b release/v1.2.0

# For patch releases, branch from the release tag
git checkout -b release/v1.1.1 v1.1.0
```

#### 2. Update Version Numbers

Update version in relevant files:

```bash
# pyproject.toml
version = "1.2.0"

# frontend/package.json
"version": "1.2.0"

# app/__init__.py (if version exported)
__version__ = "1.2.0"
```

#### 3. Update CHANGELOG.md

Move items from `[Unreleased]` to new version section:

```markdown
## [1.2.0] - 2024-01-15

### Added
- New PDF export feature with custom fonts
- Speaker diarization support
- Admin analytics dashboard

### Changed
- Improved search performance by 2x
- Updated Docker base image to ROCm 6.1

### Fixed
- Fixed memory leak in worker process
- Corrected timestamp alignment in long videos

### Security
- Updated dependencies with security patches
- Implemented rate limiting on API endpoints

## [1.1.0] - 2023-12-01
...
```

#### 4. Commit and Push

```bash
git add .
git commit -m "chore: prepare release v1.2.0"
git push origin release/v1.2.0
```

#### 5. Create Pull Request

Create PR from `release/v1.2.0` to `main`:
- Title: "Release v1.2.0"
- Include changelog in PR description
- Request reviews from maintainers
- Ensure all CI checks pass

## Creating a Release

### After PR Merge

#### 1. Create Git Tag

```bash
# Pull latest main
git checkout main
git pull origin main

# Create annotated tag
git tag -a v1.2.0 -m "Release version 1.2.0

- New PDF export feature
- Speaker diarization support
- Performance improvements
"

# Push tag
git push origin v1.2.0
```

#### 2. Create GitHub Release

Go to [GitHub Releases](https://github.com/subculture-collective/transcript-create/releases):

1. Click "Draft a new release"
2. Choose tag: `v1.2.0`
3. Release title: `v1.2.0 - Feature Name` (e.g., "v1.2.0 - PDF Export & Diarization")
4. Description:
   ```markdown
   ## 🎉 What's New
   
   ### ✨ Features
   - **PDF Export**: Generate beautiful PDFs with custom fonts
   - **Speaker Diarization**: Identify different speakers in transcripts
   - **Admin Dashboard**: New analytics and user management
   
   ### 🚀 Improvements
   - 2x faster search performance
   - Reduced memory usage in worker
   - Better error messages
   
   ### 🐛 Bug Fixes
   - Fixed memory leak in long-running workers
   - Corrected timestamp alignment
   - Fixed OAuth redirect issues
   
   ### 📦 Docker Images
   
   ```bash
   docker pull ghcr.io/onnwee/transcript-create:v1.2.0
   docker pull ghcr.io/onnwee/transcript-create:1.2
   docker pull ghcr.io/onnwee/transcript-create:1
   docker pull ghcr.io/onnwee/transcript-create:latest
   ```
   
   ## 📝 Full Changelog
   
   See [CHANGELOG.md](https://github.com/subculture-collective/transcript-create/blob/main/CHANGELOG.md) for complete details.
   
   ## ⬆️ Upgrade Notes
   
   ### Database Migrations
   ```bash
   python scripts/run_migrations.py upgrade
   ```
   
   ### Breaking Changes
   None in this release.
   
   ## 🙏 Contributors
   
   Thank you to all contributors who made this release possible!
   ```

5. Check "Set as the latest release" (for stable releases)
6. Click "Publish release"

#### 3. Verify Docker Images

Docker images are automatically built by GitHub Actions:

```bash
# Wait for docker-build workflow to complete
# Verify images are published
docker pull ghcr.io/onnwee/transcript-create:v1.2.0
docker pull ghcr.io/onnwee/transcript-create:latest
```

## Post-Release Tasks

### Immediate

- [ ] Verify release appears on GitHub
- [ ] Verify Docker images are available
- [ ] Test installation from released artifacts
- [ ] Update any deployment configurations
- [ ] Announce release (if significant)

### Communication

#### Internal
- Update team on new release
- Share any deployment considerations
- Document known issues (if any)

#### External (for significant releases)
- **Twitter/Social Media**: Announce major features
- **Blog Post**: Write about significant changes
- **Email Newsletter**: Notify users (if list exists)
- **Community Forums**: Share in relevant communities

### Monitoring

After release, monitor for:
- [ ] Error rates in production
- [ ] Performance metrics
- [ ] User feedback and issues
- [ ] Security alerts

### Documentation Updates

- [ ] Update any user-facing documentation
- [ ] Update deployment guides
- [ ] Update API reference (if changed)
- [ ] Update SDK documentation (if API changed)

## Hotfix Releases

For critical bugs or security issues in production:

### 1. Create Hotfix Branch

```bash
# Branch from the release tag
git checkout -b hotfix/v1.2.1 v1.2.0
```

### 2. Apply Fix

```bash
# Make minimal changes to fix the issue
git commit -m "fix: critical bug causing data loss"
```

### 3. Update Version and Changelog

```bash
# Update version to 1.2.1
# Update CHANGELOG.md with hotfix details
git commit -m "chore: bump version to 1.2.1"
```

### 4. Release Process

```bash
# Merge to main
git checkout main
git merge hotfix/v1.2.1

# Create tag
git tag -a v1.2.1 -m "Hotfix: Fix critical bug"
git push origin main v1.2.1

# If needed, also merge to develop/next
git checkout develop
git merge hotfix/v1.2.1
git push origin develop
```

### 5. Emergency Communication

For critical security fixes:
- Notify users immediately
- Provide upgrade instructions
- Document the vulnerability (after fix is deployed)

## Docker Images

### Automatic Builds

Docker images are automatically built and published on:
- Push to `main` branch → `latest` tag
- Version tags (e.g., `v1.2.0`) → multiple tags:
  - `v1.2.0` (exact)
  - `1.2.0` (without v prefix)
  - `1.2` (minor)
  - `1` (major)
  - `latest` (if latest stable)

### Available Tags

```bash
# Specific version
ghcr.io/onnwee/transcript-create:v1.2.0
ghcr.io/onnwee/transcript-create:1.2.0

# Minor version (gets patch updates)
ghcr.io/onnwee/transcript-create:1.2

# Major version (gets minor and patch updates)
ghcr.io/onnwee/transcript-create:1

# Latest stable
ghcr.io/onnwee/transcript-create:latest

# ROCm variants
ghcr.io/onnwee/transcript-create:rocm6.0
ghcr.io/onnwee/transcript-create:rocm6.1
```

### Manual Docker Build

If needed, manually build and push:

```bash
# Build image
docker build -t ghcr.io/onnwee/transcript-create:v1.2.0 .

# Test image
docker run --rm ghcr.io/onnwee/transcript-create:v1.2.0 --version

# Push to registry
docker push ghcr.io/onnwee/transcript-create:v1.2.0
```

## Rollback Procedure

If a release has critical issues:

### 1. Immediate Mitigation

```bash
# Revert to previous stable version in production
docker pull ghcr.io/onnwee/transcript-create:v1.1.0
# Update deployment to use old version
```

### 2. Revert Code (if needed)

```bash
# Create revert commit
git revert v1.2.0

# Or reset to previous version
git checkout -b revert/v1.2.0
git reset --hard v1.1.0
git push origin revert/v1.2.0
```

### 3. Communication

- Notify users of the issue
- Explain rollback plan
- Provide timeline for fix

### 4. Fix and Re-release

- Fix the issue
- Test thoroughly
- Release as patch version (v1.2.1)

## Versioning Best Practices

### Breaking Changes

Always increment MAJOR version for:
- Removing endpoints or features
- Changing request/response formats
- Changing database schema incompatibly
- Changing configuration format

Provide:
- Migration guide
- Deprecation warnings (when possible)
- Backward compatibility period

### Feature Releases

Increment MINOR version for:
- New endpoints or features
- New optional configuration
- Enhanced functionality
- Performance improvements

### Patch Releases

Increment PATCH version for:
- Bug fixes
- Security patches
- Documentation updates
- Dependency updates (no new features)

## Changelog Format

Follow [Keep a Changelog](https://keepachangelog.com/) format:

```markdown
## [Version] - YYYY-MM-DD

### Added
- New features

### Changed
- Changes in existing functionality

### Deprecated
- Soon-to-be removed features

### Removed
- Removed features

### Fixed
- Bug fixes

### Security
- Security fixes
```

## Resources

- [Semantic Versioning](https://semver.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github)
- [Docker Tagging Best Practices](https://docs.docker.com/engine/reference/commandline/tag/)

## Questions?

- Review previous releases for examples
- Ask in GitHub discussions
- Check [CONTRIBUTING.md](../../CONTRIBUTING.md)

Happy releasing! 🚀
