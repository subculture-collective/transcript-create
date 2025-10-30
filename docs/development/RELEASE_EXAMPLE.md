# Release Process Example

This document shows a real example of the automated release process.

## Example Workflow: v0.1.0 → v0.2.0

### 1. Development Phase

Developers make commits following Conventional Commits:

```bash
git commit -m "feat: add speaker diarization support"
git commit -m "feat: add PDF export with custom fonts"
git commit -m "fix: resolve memory leak in audio processing"
git commit -m "perf: optimize database queries for search"
git commit -m "docs: update API authentication guide"
```

### 2. Ready to Release

```bash
# Check what standard-version will do (dry-run)
$ npm run release -- --dry-run

✔ bumping version in pyproject.toml from 0.1.0 to 0.2.0
✔ bumping version in package.json from 0.1.0 to 0.2.0
✔ bumping version in frontend/package.json from 0.1.0 to 0.2.0
✔ bumping version in clients/javascript/package.json from 0.1.0 to 0.2.0
✔ bumping version in e2e/package.json from 0.1.0 to 0.2.0
✔ outputting changes to CHANGELOG.md

---
### 0.2.0 (2025-10-29)

### ✨ Features

* add speaker diarization support ([abc123])
* add PDF export with custom fonts ([def456])

### 🐛 Bug Fixes

* resolve memory leak in audio processing ([ghi789])

### ⚡ Performance Improvements

* optimize database queries for search ([jkl012])

### 📚 Documentation

* update API authentication guide ([mno345])
---

✔ committing pyproject.toml package.json frontend/package.json clients/javascript/package.json e2e/package.json CHANGELOG.md
✔ tagging release v0.2.0
```

### 3. Execute Release

```bash
# Actually create the release
$ npm run release

✔ bumping version in pyproject.toml from 0.1.0 to 0.2.0
✔ bumping version in package.json from 0.1.0 to 0.2.0
✔ bumping version in frontend/package.json from 0.1.0 to 0.2.0
✔ bumping version in clients/javascript/package.json from 0.1.0 to 0.2.0
✔ bumping version in e2e/package.json from 0.1.0 to 0.2.0
✔ outputting changes to CHANGELOG.md
✔ committing pyproject.toml package.json frontend/package.json clients/javascript/package.json e2e/package.json CHANGELOG.md
✔ tagging release v0.2.0
ℹ Run `git push --follow-tags` to publish
```

### 4. Push Release

```bash
$ git push --follow-tags

Enumerating objects: 15, done.
Counting objects: 100% (15/15), done.
Delta compression using up to 8 threads
Compressing objects: 100% (10/10), done.
Writing objects: 100% (10/10), 2.5 KiB | 2.5 MiB/s, done.
Total 10 (delta 5), reused 0 (delta 0)
To github.com:subculture-collective/transcript-create.git
   47de4e5..b2c3d4e  main -> main
 * [new tag]         v0.2.0 -> v0.2.0
```

### 5. GitHub Actions Workflow

The release.yml workflow is automatically triggered:

```
Release Workflow
├─ Job: release
│  ├─ Checkout code (with full history)
│  ├─ Setup Node.js
│  ├─ Install dependencies
│  ├─ Extract version from tag (0.2.0)
│  ├─ Generate changelog section
│  └─ Create GitHub Release
│     ├─ Title: Release v0.2.0
│     ├─ Tag: v0.2.0
│     ├─ Body: Extracted from CHANGELOG.md
│     └─ Status: Published ✓
│
└─ Job: docker
   ├─ Checkout code
   ├─ Setup Docker Buildx
   ├─ Login to GHCR
   ├─ Extract metadata
   ├─ Build Docker image
   │  ├─ Build args:
   │  │  ├─ GIT_COMMIT=b2c3d4e
   │  │  ├─ BUILD_DATE=2025-10-29T19:00:00Z
   │  │  └─ VERSION=0.2.0
   │  └─ Tags:
   │     ├─ ghcr.io/subculture-collective/transcript-create:v0.2.0
   │     ├─ ghcr.io/subculture-collective/transcript-create:0.2.0
   │     ├─ ghcr.io/subculture-collective/transcript-create:0.2
   │     ├─ ghcr.io/subculture-collective/transcript-create:0
   │     └─ ghcr.io/subculture-collective/transcript-create:latest
   └─ Push to registry ✓
```

### 6. Verify Release

**GitHub Release:**
```
https://github.com/subculture-collective/transcript-create/releases/tag/v0.2.0

Release v0.2.0

### ✨ Features
- add speaker diarization support
- add PDF export with custom fonts

### 🐛 Bug Fixes
- resolve memory leak in audio processing

### ⚡ Performance Improvements
- optimize database queries for search

### 📚 Documentation
- update API authentication guide

Docker Images:
ghcr.io/subculture-collective/transcript-create:v0.2.0
ghcr.io/subculture-collective/transcript-create:latest
```

**Docker Images:**
```bash
$ docker pull ghcr.io/subculture-collective/transcript-create:v0.2.0
v0.2.0: Pulling from subculture-collective/transcript-create
✓ Downloaded

$ docker run --rm ghcr.io/subculture-collective/transcript-create:v0.2.0 python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"
0.2.0
```

**Version Endpoint:**
```bash
$ curl http://localhost:8000/version
{
  "version": "0.2.0",
  "git_commit": "b2c3d4e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3",
  "build_date": "2025-10-29T19:00:00Z"
}
```

**API Logs:**
```
2025-10-29T19:00:00.000Z INFO [api] API service started version=0.2.0 log_level=INFO
```

## CHANGELOG.md Result

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2025-10-29

### ✨ Features
- add speaker diarization support
- add PDF export with custom fonts

### 🐛 Bug Fixes
- resolve memory leak in audio processing

### ⚡ Performance Improvements
- optimize database queries for search

### 📚 Documentation
- update API authentication guide

## [0.1.0] - 2025-10-25

### Added
- Initial release of Transcript Create
- FastAPI backend with modular routers
- PostgreSQL database with queue system
- GPU-accelerated Whisper worker (ROCm/CUDA)
...
```

## Breaking Change Example: v0.2.0 → v1.0.0

If a breaking change is introduced:

```bash
$ git commit -m "feat!: remove Python 3.10 support

BREAKING CHANGE: Minimum Python version is now 3.11"

$ npm run release
# Automatically bumps to 1.0.0 (major version)

✔ bumping version in pyproject.toml from 0.2.0 to 1.0.0
✔ outputting changes to CHANGELOG.md

---
### 1.0.0 (2025-10-30)

### ⚠ BREAKING CHANGES

* Minimum Python version is now 3.11

### ✨ Features

* remove Python 3.10 support ([abc123])
---
```

## Pre-release Example: v1.0.0-beta.1

For testing before stable release:

```bash
$ npm run release -- --prerelease beta

✔ bumping version from 0.2.0 to 1.0.0-beta.1
✔ tagging release v1.0.0-beta.1
```

**GitHub Release:**
- Marked as "Pre-release" ⚠️
- Does NOT update `latest` Docker tag
- Available for testing: `ghcr.io/subculture-collective/transcript-create:v1.0.0-beta.1`

## Hotfix Example: v1.0.0 → v1.0.1

For urgent production fixes:

```bash
# Branch from release
$ git checkout -b hotfix/v1.0.1 v1.0.0

# Make fix
$ git commit -m "fix: critical security vulnerability in auth"

# Create patch release
$ npm run release:patch

✔ bumping version from 1.0.0 to 1.0.1

# Merge and push
$ git checkout main
$ git merge hotfix/v1.0.1
$ git push --follow-tags
```

Result: v1.0.1 published with security fix, no feature changes.

## Summary

The automated release system:

1. ✅ Analyzes commits to determine version bump
2. ✅ Updates all version files automatically
3. ✅ Generates categorized changelog
4. ✅ Creates git tag
5. ✅ Creates GitHub Release with notes
6. ✅ Builds and publishes Docker images with multiple tags
7. ✅ Provides version information via API endpoint

**Total time from commit to published release: ~5-10 minutes**

No manual version editing. No manual changelog writing. No manual Docker builds.
