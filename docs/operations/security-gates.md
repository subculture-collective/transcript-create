# Blocking Dependency and SAST Gates

HasanAra blocks releases on reachable dependency advisories and high-severity
Python SAST findings. The canonical runtime gate uses Python 3.11 and Node 20.

Run the focused gates locally with no advisory suppressions:

```bash
rtk proxy python scripts/check_security_exceptions.py
rtk proxy python -m pip_audit --local --skip-editable
rtk proxy python -m pip_audit -r requirements.txt --no-deps --disable-pip
rtk proxy python -m pip_audit -r constraints.txt --no-deps --disable-pip
rtk proxy python -m pip_audit -r requirements-ml-runtime.txt --no-deps --disable-pip
rtk proxy python -m bandit -r app/ worker/ -lll -ii
rtk proxy python scripts/check_security_exceptions.py --npm-audit --package-dir frontend
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

## September 19 follow-up: no active exceptions

The historical Lightning and Torch exceptions expired September 13. Both
suppressions have been removed; the policy helper emits no pip-audit ignore
arguments. An incompatible or unavailable patched runtime remains a release
blocker, not an implicit exception renewal. The local verification shell now
preserves the validator's exit status before parsing its output.

- **AnyIO:** constraints pin 4.14.2, addressing the three findings reported in
  the development environment at 4.14.0.
- **Lightning:** constraints pin 2.6.6, matching the patched release for
  `PYSEC-2026-3624`. Import smoke passed. The previous statement that no patched
  PyPI release exists is obsolete.
- **Setuptools:** constraints pin 83.0.0, matching the existing Dockerfile build
  pin in the API and fixing `PYSEC-2026-3447`. The old constraints snapshot
  pinned 81.0.0. The ingest image build pin is also updated to 83.0.0.
- **pip:** API and ingest image build steps pin 26.2. The API's base image
  included pip 24.0 with six reported advisories. Remove its original pip
  distribution before copying the patched dependency stage, avoiding duplicate
  distribution metadata. The final API image inventory audits cleanly and
  `pip check` passes; this is a Python-package audit, not an OS image scan.
- **Frontend:** the lockfile audit returned zero vulnerabilities on September 19
  after the earlier registry outage cleared. There is no active brace-expansion
  exception; the old path-specific exception description is retired.
- **Torch remains blocked:** `GHSA-rrmf-rvhw-rf47` identifies 2.13.0 as patched.
  Repository ML runtime pins remain Torch/TorchAudio 2.11.0. The local development
  environment contains Torch 2.12.1 and is not an exact production ML environment.
  On September 19, the official Python 3.11 Linux x86_64 indexes listed Torch
  2.13.0 for CPU and ROCm 7.1, but none for CUDA 12.8. None of those three indexes
  listed TorchAudio 2.13.0, and its PyPI version endpoint returned 404. Do not
  combine an unmatched TorchAudio binary with a new Torch version just to clear
  the advisory. Refresh the compatible upstream wheel matrix, resolve the full
  ML role, and pass codec/pyannote/transcription hardware checks before changing
  the production pins. The local Torch 2.12.1 metadata also requires
  `setuptools<82`, conflicting with the patched 83.0.0; `uv pip check` correctly
  reports that unresolved ML environment conflict. Do not downgrade Setuptools
  back to its vulnerable version to satisfy it. Resolving the declared worker
  plus ML requirements also fails because Torch 2.11.0 requires `setuptools<82`.
  Existing combined ML Dockerfiles still pin Setuptools 81.0.0 and are not
  qualified for release; the secure global constraint intentionally prevents
  resolving that vulnerable combination. Resolve this as one compatible ML
  runtime upgrade, not an isolated pin override.

Sources: [Torch advisory](https://github.com/advisories/GHSA-rrmf-rvhw-rf47),
[official CPU wheels](https://download.pytorch.org/whl/cpu/),
[CUDA 12.8 wheels](https://download.pytorch.org/whl/cu128/),
[ROCm 7.1 wheels](https://download.pytorch.org/whl/rocm7.1/), and
[Lightning 2.6.6 metadata](https://pypi.org/pypi/lightning/2.6.6/json).

A future exception must identify the advisory, affected package and path,
reachability evidence, compensating control, owner, approval date, and an
expiry no more than 30 days later. CI exceptions must use the advisory's exact
identifier; blanket scanner suppression is not permitted.
