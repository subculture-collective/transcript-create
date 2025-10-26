# Docker Build Variants

This document describes the available Docker image variants for transcript-create and their use cases.

## Overview

transcript-create provides three optimized Docker image variants:

1. **ROCm** - AMD GPU acceleration (default)
2. **CPU** - CPU-only for development/testing
3. **CUDA** - NVIDIA GPU acceleration

All variants use multi-stage builds for optimal image size and build time.

## Variants

### 1. ROCm Variant (Default)

**File:** `Dockerfile`

**Base Image:** `rocm/dev-ubuntu-22.04:6.0.2`

**Target Size:** <2.5GB (down from ~3GB)

**Use Cases:**
- Production deployments with AMD GPUs
- RDNA/GCN architecture support
- High-performance transcription

**Build:**
```bash
# Using build script (recommended)
./scripts/build-rocm.sh [rocm_version] [--no-cache] [--push]

# Examples
./scripts/build-rocm.sh                # Build with ROCm 6.0
./scripts/build-rocm.sh 6.1            # Build with ROCm 6.1
./scripts/build-rocm.sh 6.0 --no-cache # Build without cache

# Using docker directly
docker build -t transcript-create:rocm6.0 \
  --build-arg ROCM_WHEEL_INDEX=https://download.pytorch.org/whl/rocm6.0 \
  -f Dockerfile .
```

**Run:**
```bash
docker run -p 8000:8000 \
  --device=/dev/kfd --device=/dev/dri \
  --group-add video \
  -v ./data:/data \
  -v ./cache:/root/.cache \
  transcript-create:rocm6.0
```

**Supported ROCm Versions:**
- 6.0 (default)
- 6.1
- 6.2

### 2. CPU-Only Variant

**File:** `Dockerfile.cpu`

**Base Image:** `python:3.11-slim`

**Target Size:** <1GB

**Use Cases:**
- Development and testing
- CI/CD pipelines
- CPU-based inference (slower but no GPU required)
- Environments without GPU access

**Build:**
```bash
# Using build script (recommended)
./scripts/build-cpu.sh [--no-cache] [--push]

# Examples
./scripts/build-cpu.sh                # Build with cache
./scripts/build-cpu.sh --no-cache     # Build without cache

# Using docker directly
docker build -t transcript-create:cpu -f Dockerfile.cpu .
```

**Run:**
```bash
docker run -p 8000:8000 \
  -v ./data:/data \
  -v ./cache:/root/.cache \
  transcript-create:cpu
```

**Features:**
- Smallest image size (~800MB-1GB)
- No GPU dependencies
- Faster build times
- Ideal for development

### 3. CUDA Variant

**File:** `Dockerfile.cuda`

**Base Image:** `nvidia/cuda:12.1.0-runtime-ubuntu22.04`

**Target Size:** ~2.5GB

**Use Cases:**
- Production deployments with NVIDIA GPUs
- CUDA-accelerated inference
- Maximum performance on NVIDIA hardware

**Build:**
```bash
# Using build script (recommended)
./scripts/build-cuda.sh [cuda_version] [--no-cache] [--push]

# Examples
./scripts/build-cuda.sh                # Build with CUDA 12.1
./scripts/build-cuda.sh 11.8           # Build with CUDA 11.8
./scripts/build-cuda.sh --no-cache     # Build without cache

# Using docker directly
docker build -t transcript-create:cuda12.1 \
  --build-arg CUDA_WHEEL_INDEX=https://download.pytorch.org/whl/cu121 \
  -f Dockerfile.cuda .
```

**Run:**
```bash
docker run -p 8000:8000 \
  --gpus all \
  -v ./data:/data \
  -v ./cache:/root/.cache \
  transcript-create:cuda12.1
```

**Supported CUDA Versions:**
- 12.1 (default, recommended)
- 11.8

**Requirements:**
- NVIDIA GPU
- NVIDIA Container Toolkit
- CUDA-compatible drivers

## Build Arguments

All variants support the following build arguments:

### ROCm Variant
- `ROCM_WHEEL_INDEX` - PyTorch wheel index URL (default: rocm6.0)

### CUDA Variant
- `CUDA_WHEEL_INDEX` - PyTorch wheel index URL (default: cu121)

## Multi-Stage Build Architecture

All variants use a three-stage build process:

1. **Base Stage** - System dependencies and base image
2. **Python Dependencies Stage** - Install Python packages
3. **Application Stage** - Copy application code and finalize

This architecture provides:
- **Layer caching** - Rebuild only changed layers
- **Smaller images** - Only production dependencies in final stage
- **Faster builds** - Parallel builds with BuildKit
- **Better security** - Minimal attack surface

## Build Optimization Features

### BuildKit Cache Mounts

All variants use BuildKit cache mounts for pip:

```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --no-cache-dir -r requirements.txt
```

This persists pip's cache across builds, dramatically speeding up rebuilds.

### Layer Ordering

Layers are ordered by change frequency:
1. System packages (rarely change)
2. Python dependencies (change occasionally)
3. Application code (change frequently)

This maximizes cache hits during development.

### Image Size Reduction

- Remove apt cache: `rm -rf /var/lib/apt/lists/*`
- Use `--no-install-recommends` for apt
- Install only required system packages
- Pre-compile Python files
- Exclude unnecessary files via `.dockerignore`

## Environment Variables

### All Variants

- `PYTHONUNBUFFERED=1` - Real-time logging
- `PYTHONDONTWRITEBYTECODE=1` - No .pyc files
- `HF_HOME=/root/.cache/hf` - Hugging Face cache
- `PDF_FONT_PATH=/app/fonts/DejaVuSerif.ttf` - PDF font path

### ROCm Variant

- `FORCE_GPU=true` - Force GPU usage
- `WHISPER_BACKEND=whisper` - Use PyTorch backend

### CPU Variant

- `FORCE_GPU=false` - CPU-only mode
- `WHISPER_BACKEND=faster-whisper` - Use faster-whisper backend

### CUDA Variant

- `FORCE_GPU=true` - Force GPU usage
- `WHISPER_BACKEND=whisper` - Use PyTorch backend
- `NVIDIA_VISIBLE_DEVICES=all` - All GPUs visible
- `NVIDIA_DRIVER_CAPABILITIES=compute,utility` - GPU capabilities

## Health Checks

All variants include health checks:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
```

This enables:
- Container orchestration (Kubernetes, Docker Compose)
- Automatic restart on failure
- Load balancer health monitoring

## Performance Comparison

| Variant | Image Size | Build Time (no cache) | Build Time (cached) | Inference Speed |
|---------|-----------|----------------------|-------------------|----------------|
| ROCm 6.0 | ~2.3GB | 15-20 min | 2-5 min | Fast (GPU) |
| CPU | ~900MB | 8-12 min | 1-3 min | Slow (CPU) |
| CUDA 12.1 | ~2.4GB | 15-20 min | 2-5 min | Fastest (GPU) |

*Note: Times measured on GitHub Actions runners with BuildKit caching*

## CI/CD Integration

### GitHub Actions

The Docker build workflow (`.github/workflows/docker-build.yml`) automatically:
- Builds the ROCm variant on push to main
- Uses GitHub Actions cache for faster builds
- Pushes to GitHub Container Registry
- Generates SBOMs and attestations
- Signs images (optional)

### Building All Variants

To build all variants locally:

```bash
# Build all variants
./scripts/build-rocm.sh
./scripts/build-cpu.sh
./scripts/build-cuda.sh

# Or with docker-compose
docker-compose build
```

## Security

All variants:
- ✅ Run as root (required for volume permissions in docker-compose)
- ✅ Include health checks
- ✅ Use specific version tags (no `latest` in production)
- ✅ Minimize installed packages
- ✅ Clean apt cache

For production deployments with non-root users, consider:
- Using Kubernetes security contexts
- Running with user namespace remapping
- Using read-only root filesystems

## Troubleshooting

### BuildKit Not Enabled

If builds fail with cache mount errors:

```bash
export DOCKER_BUILDKIT=1
docker build ...
```

### Permission Issues

If you encounter permission issues with mounted volumes:

```bash
# Fix ownership
sudo chown -R $USER:$USER ./data ./cache
```

### GPU Not Detected

**ROCm:**
```bash
# Check devices
ls -la /dev/kfd /dev/dri

# Check group membership
groups | grep video

# Add user to video group
sudo usermod -a -G video $USER
```

**CUDA:**
```bash
# Check NVIDIA runtime
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# Install NVIDIA Container Toolkit if needed
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

## Best Practices

1. **Use variant-specific tags** - Don't use `latest` in production
2. **Enable BuildKit** - For faster builds and cache mounts
3. **Mount volumes** - Persist data and model caches
4. **Monitor health** - Use health check endpoints
5. **Security scanning** - Run Trivy scans before deployment
6. **Resource limits** - Set memory/CPU limits in production

## References

- [Docker Multi-Stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [BuildKit Documentation](https://docs.docker.com/build/buildkit/)
- [ROCm Documentation](https://rocm.docs.amd.com/)
- [NVIDIA Container Toolkit](https://github.com/NVIDIA/nvidia-docker)
- [PyTorch Installation](https://pytorch.org/get-started/locally/)
