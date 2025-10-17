# [SEC/INFRA] Container vulnerability scanning (Trivy)

Goal: Scan built Docker images for vulnerabilities on PRs and fail on high/critical (with allowlist). Upload SARIF.

Steps:
1) Create .github/workflows/trivy.yml that:
   - Builds docker image(s) (API and worker tags; can be a single image if shared).
   - Runs aquasecurity/trivy-action to scan image.
   - Uploads SARIF to GitHub Security.
   - Fails the job on high/critical unless allowlist is hit.
2) Provide .trivyignore for known acceptable items (comment why) and keep minimal.

Acceptance criteria:
- Trivy workflow runs on PR and main.
- SARIF uploaded; Security tab shows findings.
- High/Critical cause failures unless ignored in .trivyignore.

Metadata:
- Milestone: M1 — Foundation & CI Ready
- Labels: type:security, area:infra, P1-high, status:ready
