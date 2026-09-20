# Blocking Dependency and SAST Gates

Transcript Archive blocks releases on reachable dependency advisories and high-severity
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
hooks. Each CPU, CUDA 12.6, and ROCm 7.1 image runs `pip check`, imports Torch,
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
- **pip:** build stages use 26.2, then remove pip from immutable runtime images.
  Its vendored msgpack and setuptools remained vulnerable even in pip 26.2.1;
  removing the installer removes that code rather than hiding its metadata.
- **Frontend:** the lockfile audit returned zero vulnerabilities on September 19
  after the earlier registry outage cleared. There is no active brace-expansion
  exception; the old path-specific exception description is retired.
- **Torch:** ML runtimes now pin 2.13.0, TorchAudio 2.11.0 and TorchCodec 0.14.0.
  The earlier conclusion that TorchAudio 2.13.0 was required was incorrect:
  upstream explicitly supports TorchAudio 2.11 with Torch 2.11 and later, and
  TorchCodec 0.14 with Torch 2.11 and later. CPU, CUDA 12.6 and ROCm 7.1 wheels
  are available. The separate CUDA 12.8 faster-whisper ingest role is unchanged
  in accelerator selection. Triton 3.7.1 and repeated ML constraints prevent
  later dependency installation from silently downgrading Torch.
- **Lightning scanner correction:** Trivy's September 19 database incorrectly
  gives `CVE-2026-58659` a fixed version of `2022.6.15`. Version 2.6.6 contains
  the upstream checkpoint-instantiator allowlist fix. The exact package/version
  VEX statement in `security/lightning-2.6.6.vex.json` records it as fixed.
  Before accepting it, local and release image gates run
  `scripts/check_lightning_patch.py` inside the exact image with networking
  disabled. This requires version 2.6.6, the patched source SHA-256, and actual
  rejection of an untrusted checkpoint instantiator. Any drift fails closed;
  other packages, versions and advisories remain blocking. This is a verified
  fixed-artifact correction, not renewed acceptance of vulnerable code.

Sources: [Torch advisory](https://github.com/advisories/GHSA-rrmf-rvhw-rf47),
[TorchAudio compatibility](https://github.com/pytorch/audio),
[TorchCodec compatibility](https://github.com/meta-pytorch/torchcodec),
[official CUDA 12.6 wheels](https://download.pytorch.org/whl/cu126/),
[ROCm 7.1 wheels](https://download.pytorch.org/whl/rocm7.1/), and
[Lightning checkpoint fix](https://github.com/Lightning-AI/pytorch-lightning/commit/d710d689510d50e800f53b3cd773cbca20b1f86f).

A future exception must identify the advisory, affected package and path,
reachability evidence, compensating control, owner, approval date, and an
expiry no more than 30 days later. CI exceptions must use the advisory's exact
identifier; blanket scanner suppression is not permitted.
