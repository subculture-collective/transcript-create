# Dependency Management

## Overview

This document explains the dependency structure and management strategy for transcript-create.

## Files

- **requirements.txt**: Primary dependencies with pinned versions
- **constraints.txt**: Full dependency tree for reproducible builds
- **Dockerfile**: Special handling for PyTorch with ROCm/CUDA support

## Dependencies Structure

### Core Dependencies (requirements.txt)

All production dependencies are explicitly pinned to specific versions:

- **API Framework**: FastAPI, Uvicorn
- **Database**: SQLAlchemy, psycopg
- **Media Processing**: yt-dlp
- **Transcription**: faster-whisper, openai-whisper
- **Diarization**: pyannote.audio (optional)
- **Auth**: Authlib
- **Billing**: stripe
- **Export**: reportlab

### Full Dependency Tree (constraints.txt)

Contains all transitive dependencies with exact versions for:
- Reproducible builds across environments
- Security auditing
- Compatibility verification

## GPU Support: ROCm vs CUDA

### Why Special Handling?

PyTorch and related packages (torch, torchaudio) have different builds for:
- **CUDA**: NVIDIA GPUs
- **ROCm**: AMD GPUs
- **CPU**: No GPU acceleration

These cannot coexist and must be installed separately based on the target hardware.

### Dockerfile Strategy

The Dockerfile implements a two-stage installation:

1. **Install general dependencies** from requirements.txt
   ```dockerfile
   pip3 install -r requirements.txt
   ```

2. **Remove any conflicting torch packages** that may have been installed as transitive dependencies
   ```dockerfile
   pip3 uninstall -y torch torchvision torchaudio
   ```

3. **Install ROCm-specific PyTorch** from the appropriate wheel index
   ```dockerfile
   pip3 install --index-url ${ROCM_WHEEL_INDEX} \
       torch==2.4.1+rocm6.0 torchaudio==2.4.1+rocm6.0
   ```

### Build Arguments

- `ROCM_WHEEL_INDEX`: URL to PyTorch wheels for specific ROCm version
  - Default: `https://download.pytorch.org/whl/rocm6.0`
  - ROCm 6.1: `https://download.pytorch.org/whl/rocm6.1`
  - ROCm 6.2: `https://download.pytorch.org/whl/rocm6.2`

Example for different ROCm version:
```bash
docker compose build --build-arg ROCM_WHEEL_INDEX=https://download.pytorch.org/whl/rocm6.1
```

### For CUDA/NVIDIA

To use NVIDIA GPUs instead:

1. Change base image in Dockerfile:
   ```dockerfile
   FROM nvidia/cuda:12.8.0-cudnn8-runtime-ubuntu22.04
   ```

2. Change PyTorch installation:
   ```dockerfile
   pip3 install --index-url https://download.pytorch.org/whl/cu124 \
       torch==2.4.1+cu124 torchaudio==2.4.1+cu124
   ```

3. Update docker-compose.yml to use nvidia runtime

### For CPU-only

For development without GPU:

```dockerfile
pip3 install torch==2.4.1 torchaudio==2.4.1
```

Set in .env:
```bash
FORCE_GPU=false
```

## Updating Dependencies

### Security Updates

1. Check for vulnerabilities:
   ```bash
   pip-audit -r requirements.txt
   safety check -r requirements.txt
   ```

2. Update specific package:
   ```bash
   pip install --upgrade package-name==NEW_VERSION
   pip freeze | grep package-name
   ```

3. Test thoroughly in development

4. Update both requirements.txt and constraints.txt:
   ```bash
   # In a clean virtual environment
   pip install -r requirements.txt
   pip freeze > constraints.txt
   ```

5. Run security scans again to verify

### Major Version Updates

When updating to new major versions:

1. Review changelog and breaking changes
2. Update in a development branch
3. Run full test suite
4. Check compatibility with ROCm/CUDA versions
5. Update documentation if needed

### Automated Scanning

GitHub Actions automatically runs security scans:
- On push to main/develop branches
- On pull requests
- Weekly schedule (Mondays at 9 AM UTC)
- Manual trigger via workflow_dispatch

Scans fail on high/critical severity vulnerabilities.

## Constraints File

The `constraints.txt` file captures the complete resolved dependency tree. This provides:

### Benefits

1. **Reproducibility**: Exact versions for all dependencies
2. **Security**: Complete audit trail of all packages
3. **Debugging**: Easy to identify which transitive dependency changed

### When to Update

Update constraints.txt when:
- Adding new dependencies to requirements.txt
- Updating existing dependency versions
- After security updates
- Before major releases

### How to Generate

```bash
# Create clean virtual environment
python3 -m venv /tmp/venv-constraints
source /tmp/venv-constraints/bin/activate

# Install requirements
pip install --upgrade pip
pip install -r requirements.txt

# Generate constraints (excluding GPU packages)
pip freeze > constraints.txt

# Manually remove or comment nvidia-* packages if present
# These conflict with ROCm builds
```

## Known Compatibility Issues

### PyTorch + NumPy

- PyTorch 2.4.x requires numpy < 2.4
- pyannote.audio has specific numpy version requirements
- Current pinned versions are tested and compatible

### Python Version

- Tested on Python 3.12
- Some dependencies (numba, llvmlite) may have version-specific wheels
- Use Python 3.12 in production for best compatibility

### ROCm Compatibility

- Base image: `rocm/dev-ubuntu-22.04:6.0.2`
- PyTorch ROCm wheels: version must match base image
- Verify compatibility: https://pytorch.org/get-started/locally/

## Troubleshooting

### Import Errors

If you see import errors after dependency updates:

```bash
pip check  # Check for conflicts
pip list --outdated  # Check for outdated packages
pip install --force-reinstall -r requirements.txt
```

### GPU Detection Issues

If GPU is not detected:

```bash
# Inside container
python3 -c "import torch; print(torch.cuda.is_available())"
python3 -c "import torch; print(torch.version.hip)"
```

Expected output for ROCm:
- `cuda.is_available()`: True
- `version.hip`: "6.0" or similar

### Build Failures

If Docker build fails on PyTorch installation:

1. Check ROCM_WHEEL_INDEX URL is accessible
2. Verify PyTorch version is available for your ROCm version
3. Try a different ROCm version or PyTorch version
4. Check for wheel compatibility with Python version

## Development Workflow

### Local Development (No Docker)

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# For CPU-only torch
pip uninstall -y torch torchaudio
pip install torch==2.4.1 torchaudio==2.4.1
```

### Docker Development

```bash
# Build with current dependencies
docker compose build

# Rebuild specific service
docker compose build worker

# Force rebuild without cache
docker compose build --no-cache api worker
```

## Resources

- PyTorch Installation: https://pytorch.org/get-started/locally/
- ROCm Documentation: https://rocm.docs.amd.com/
- pip-audit: https://github.com/pypa/pip-audit
- Safety: https://github.com/pyupio/safety
- Gitleaks: https://github.com/gitleaks/gitleaks

## Questions?

For dependency-related issues:
1. Check this document first
2. Review Dockerfile for GPU installation logic
3. Check GitHub Issues for similar problems
4. Open a new issue with dependency versions and error output
