# Blocking Dependency and SAST Gates

HasanAra blocks releases on reachable dependency advisories and high-severity
Python SAST findings. The canonical runtime gate uses Python 3.11 and Node 20.

Run the focused gates locally with:

```bash
python scripts/check_security_exceptions.py
pip-audit --local --skip-editable \
  --ignore-vuln GHSA-rrmf-rvhw-rf47 \
  --ignore-vuln PYSEC-2026-3624
pip-audit -r requirements.txt --no-deps --disable-pip
pip-audit -r constraints.txt --no-deps --disable-pip
pip-audit -r requirements-ml-runtime.txt --no-deps --disable-pip \
  --ignore-vuln GHSA-rrmf-rvhw-rf47 \
  --ignore-vuln PYSEC-2026-3624
bandit -r app/ worker/ -lll -ii
python scripts/check_security_exceptions.py --npm-audit --package-dir frontend
```

The installed-environment pip-audit covers resolved transitive packages in
backend CI. The three manifest audits independently cover every exact direct,
full-snapshot, and image-specific ML runtime pin without invoking package build
hooks. Each CPU, CUDA 12.8, and ROCm 7.1 image runs `pip check`, imports Torch,
TorchAudio, TorchCodec, and pyannote, and is blocked by fixed high/critical
Trivy application-library findings. Operating-system findings are reported
separately; package-type scanning is conservative and is not described as
reachability analysis. Bandit blocks
high-severity findings with medium-or-higher confidence. The frontend gate
blocks high and critical npm advisories.

The Gitea release workflow builds and loads an image once, scans that local
artifact, and pushes it without rebuilding. It then resolves and rescans the
exact registry digest before Cosign-signing and attaching verified SLSA and SBOM
attestations. Gitea prerelease creation waits for every digest scan and
verification artifact. Kubernetes deployment is manual-only: it resolves the
requested tag, verifies provenance and application libraries for that exact
digest, and supplies the immutable digest to every Helm workload. The retired
GitHub/GHCR and duplicate production workflows must not be restored.

## Active exceptions

`PYSEC-2026-3624` affects the transitive `lightning==2.6.5` dependency used
by the diarization worker. The vulnerable path imports an attacker-controlled
`_instantiator` while loading a Lightning checkpoint. HasanAra does not accept
checkpoint or model uploads, does not call `LightningModule.load_from_checkpoint`,
and keeps model identifiers operator-controlled; CI fails if a direct call is
introduced. Upstream has committed a fix but has not published a patched PyPI
release.

- Owner: backend maintainers
- Approved: 2026-08-07
- Renewal approved by the operator: 2026-09-06 UTC, for seven days
- Reassessed: 2026-09-06; Lightning 2.6.5 remains the latest PyPI release and
  no patched wheel is available. The deployed API contains neither Lightning
  nor PyTorch. The source check found no direct forbidden calls; this does not
  establish transitive unreachability in the ML workers.
- Expires: 2026-09-13 UTC
- Required action: upgrade to the first compatible patched Lightning release
  and remove the exact ignore immediately

`GHSA-rrmf-rvhw-rf47` affects `torch==2.11.0` in the transcription and
diarization worker images. It requires local invocation of `torch.jit.script`.
HasanAra accepts audio/video input, never user model artifacts, and does not
call that compiler API; CI fails if the call appears. Model identifiers and
runtime configuration remain operator-controlled. The advisory is scored low.
Torch 2.13.0 is patched, but the production ML image remains pinned to 2.11.0
until the CUDA, pyannote, and GTX 1080 runtime matrix is qualified. A centralized
UTC date and AST-based call check
causes CI to fail when the exception expires or the compiler call is introduced
through either qualified or imported-alias syntax.

- Owner: backend maintainers
- Approved: 2026-07-10
- Renewal approved by the operator: 2026-09-06 UTC, for seven days
- Reassessed: 2026-09-06; Torch 2.13.0 is patched and 2.14.0 is the latest
  PyPI release. The source check found no direct forbidden compiler calls;
  production GPU compatibility for the upgrade is not yet qualified. The API
  deployment reuses unchanged ML image digests and preserves existing controls.
- Expires: 2026-09-13 UTC
- Required action: qualify Torch and TorchAudio 2.13.0 on every production ML
  image and remove the exact ignore before expiry

`1130588` and `1130589` / `GHSA-mh99-v99m-4gvg`, plus `1130736` and
`1130737` / `GHSA-rgw5-rvv9-x895`, affect only the exact dev-only
`brace-expansion` lockfile nodes: 1.1.16 at `node_modules/brace-expansion` and
2.1.2 beneath `@redocly/openapi-core` and
`@typescript-eslint/typescript-estree`. They are not part of the production
frontend bundle. The npm wrapper rejects any production reachability, node path,
version, or audit-path drift and recursively validates every advisory leaf; it
does not blanket-ignore dev dependencies or other high/critical findings.

- Owner: frontend maintainers
- Approved: 2026-07-24
- Reassessed: 2026-08-30; the lockfile paths remain dev-only, the recursive
  audit graph and production-reachability checks remain green, and patched
  transitive versions are available
- Expires: 2026-09-06 UTC
- Required action: update the three transitive lockfile nodes and delete this
  exception and its exact dev-only lockfile check before expiry

A future exception must identify the advisory, affected package and path,
reachability evidence, compensating control, owner, approval date, and an
expiry no more than 30 days later. CI exceptions must use the advisory's exact
identifier; blanket scanner suppression is not permitted.
