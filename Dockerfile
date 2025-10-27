# =============================================================================
# Multi-Stage Dockerfile for transcript-create (ROCm variant)
# =============================================================================
# This Dockerfile implements multi-stage builds for optimal image size and
# build time through layer caching.
#
# Build stages:
#   1. base       - System dependencies and ROCm base
#   2. python-deps - Python packages installation
#   3. app        - Final application stage
#
# Target image size: <2.5GB (down from ~3GB)
# Build time: <10 min with cache
# =============================================================================

# =============================================================================
# Stage 1: Base image with system dependencies
# =============================================================================
FROM rocm/dev-ubuntu-22.04:6.0.2 AS base

# Build argument for PyTorch ROCm wheel index
ARG ROCM_WHEEL_INDEX=https://download.pytorch.org/whl/rocm6.0

# Set environment variables for non-interactive installs
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies in a single layer
# Combine apt-get update, install, and cleanup to minimize layer size
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        python3 \
        python3-pip \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# =============================================================================
# Stage 2: Python dependencies
# =============================================================================
FROM base AS python-deps

# Copy only requirements files to leverage layer caching
COPY requirements.txt constraints.txt* ./

# Install Python dependencies with pip cache mount for faster rebuilds
# Use BuildKit cache mount to persist pip cache across builds
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --no-cache-dir -r requirements.txt && \
    # Remove any torch variants pulled in by other dependencies
    (pip3 uninstall -y torch torchvision torchaudio || true) && \
    # Install ROCm PyTorch wheels explicitly
    pip3 install --no-cache-dir --index-url ${ROCM_WHEEL_INDEX} \
        torch==2.4.1+rocm6.0 torchaudio==2.4.1+rocm6.0

# Verify PyTorch installation
RUN python3 -c "import torch; print('Torch version:', torch.__version__); print('HIP version:', getattr(torch.version, 'hip', None)); print('cuda.is_available:', torch.cuda.is_available())"

# =============================================================================
# Stage 3: Final application stage
# =============================================================================
FROM base AS app

# Copy Python packages from deps stage
COPY --from=python-deps /usr/local/lib/python3.10/dist-packages /usr/local/lib/python3.10/dist-packages
COPY --from=python-deps /usr/local/bin /usr/local/bin

# Set working directory
WORKDIR /app

# Copy application code (excluding files in .dockerignore)
COPY . /app

# Pre-compile Python files for faster startup
RUN python3 -m compileall -q /app

# Set optimal environment variables for production
ENV PDF_FONT_PATH=/app/fonts/DejaVuSerif.ttf \
    HF_HOME=/root/.cache/hf \
    HF_HUB_CACHE=/root/.cache/hf/hub \
    TRANSFORMERS_CACHE=/root/.cache/hf/transformers

# Add health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose API port
EXPOSE 8000

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
