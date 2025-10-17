# [SEC/INFRA] SBOM generation for releases

Goal: Generate SBOM (CycloneDX or Syft) artifacts for containers and/or dependencies and attach to GitHub Releases.

Steps:
1) Create .github/workflows/sbom.yml that on release:
   - Builds images/artifacts.
   - Runs anchore/syft-action or cyclonedx for Python (and npm) to produce SBOMs.
   - Uploads as release assets.
2) Optionally generate SBOM on PR as artifact for inspection.

Acceptance criteria:
- SBOMs attached to releases; visible and downloadable.
- Build logs show packages and versions enumerated.

Metadata:
- Milestone: M1 — Foundation & CI Ready
- Labels: type:security, area:infra, P1-high, status:ready
