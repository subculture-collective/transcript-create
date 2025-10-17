# [CI/INFRA] Build & publish Docker images to GHCR

Goal: Build and publish container images for API and worker to ghcr.io/onnwee/transcript-create on pushes to main and tags.

Steps:
1) Create .github/workflows/docker-ghcr.yml that:
   - Logs into GHCR using GITHUB_TOKEN permissions packages:write.
   - Builds image(s) with appropriate build-args (ROCM_WHEEL_INDEX) and tags (sha, semver tags).
   - Pushes images on main and tags; supports PR build without push.
2) Optionally split API/worker if separate images are needed; otherwise single image used by both compose services.
3) Update README with pull instructions.

Acceptance criteria:
- Images pushed to GHCR with tags latest, sha, and semver on releases.
- Workflow green on main and tag events.

Metadata:
- Milestone: M1 — Foundation & CI Ready
- Labels: type:ci, area:infra, P0-blocker, status:ready
