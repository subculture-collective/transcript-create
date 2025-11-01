# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive contributor documentation and community resources
- CODE_OF_CONDUCT.md with Contributor Covenant 2.1
- CHANGELOG.md for tracking project changes
- CONTRIBUTORS.md for recognizing community contributions
- Issue templates for bug reports, feature requests, and questions
- Pull request template with comprehensive checklist
- Development documentation in docs/development/
- First-time contributor guide in docs/contributing/
- Enhanced pre-commit hooks for code quality and security

### Changed
- Enhanced CONTRIBUTING.md with welcome message and code of conduct reference
- Improved README.md with community resource links

## [1.0.0] - Unreleased

### Added
- Initial release of Transcript Create
- FastAPI backend with modular routers
- PostgreSQL database with queue system
- GPU-accelerated Whisper worker (ROCm/CUDA)
- Optional pyannote speaker diarization
- Vite React frontend with Tailwind CSS
- Full-text search with PostgreSQL FTS or OpenSearch
- Multiple export formats: SRT, VTT, JSON, PDF
- OAuth authentication (Google, Twitch)
- Stripe billing integration
- Admin analytics dashboard
- Comprehensive test suite (unit, integration, E2E)
- CI/CD pipelines for all components
- Docker and Kubernetes deployment support
- Monitoring with Prometheus and Grafana
- Automated database migrations with Alembic
- Official Python and JavaScript SDKs

### Security
- Pre-commit hooks with gitleaks secret detection
- Automated vulnerability scanning
- Regular dependency updates
- Security policy and vulnerability reporting process

## Release Notes

### Upcoming Features
See our [GitHub Issues](https://github.com/subculture-collective/transcript-create/issues) for planned features and enhancements.

### Migration Guide
For major version upgrades, see [MIGRATIONS.md](docs/MIGRATIONS.md) for database migration procedures.

### Breaking Changes
Breaking changes will be clearly marked in release notes and include migration paths.

---

**Note**: This changelog is updated automatically as part of the release process. For unreleased changes, see the commit history on the main branch.
