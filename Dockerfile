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
FROM rocm/dev-ubuntu-22.04:7.1 AS base

# Build argument for PyTorch ROCm wheel index
ARG ROCM_WHEEL_INDEX=https://download.pytorch.org/whl/rocm7.1

# Set environment variables for non-interactive installs
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies and development toolchain in a single layer
# We include python3-dev and build-essential so runtime packages that compile
# helper extensions (e.g. numba/triton helpers) can build their temporary
# C artefacts without "Python.h: No such file or directory" failures.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        python3 \
        python3-pip \
        python3-dev \
        libpython3-dev \
        build-essential \
        cmake \
        pkg-config \
        git \
        curl \
        unzip \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Deno for yt-dlp JavaScript runtime requirement
# yt-dlp requires a JS runtime (Deno/Node/Bun/QuickJS) to solve YouTube challenges
RUN curl -fsSL https://deno.land/install.sh | sh && \
    mv /root/.deno/bin/deno /usr/local/bin/deno && \
    chmod +x /usr/local/bin/deno && \
    deno --version

# =============================================================================
# Stage 2: Python dependencies
# =============================================================================
FROM base AS python-deps

# Copy only requirements files to leverage layer caching
COPY requirements.txt requirements-ml-runtime.txt constraints.txt ./
COPY scripts/verify_ml_runtime.py /tmp/verify_ml_runtime.py

# Install Python dependencies with pip cache mount for faster rebuilds
# Use BuildKit cache mount to persist pip cache across builds
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --no-cache-dir --upgrade pip==26.2 setuptools==83.0.0 wheel==0.47.0 && \
    TORCH_VERSION="$(sed -n 's/^torch==//p' requirements-ml-runtime.txt)" && \
    TORCHAUDIO_VERSION="$(sed -n 's/^torchaudio==//p' requirements-ml-runtime.txt)" && \
    TORCHCODEC_VERSION="$(sed -n 's/^torchcodec==//p' requirements-ml-runtime.txt)" && \
    # Install the accelerator-specific runtime before resolving pyannote.
    pip3 install --no-cache-dir --index-url ${ROCM_WHEEL_INDEX} \
        "torch==${TORCH_VERSION}" "torchaudio==${TORCHAUDIO_VERSION}" && \
    # TorchCodec does not publish ROCm wheels. Its CPU wheel is compatible
    # with Torch >=2.11 and pyannote receives in-memory waveforms in our worker.
    pip3 install --no-cache-dir --no-deps \
        --index-url https://download.pytorch.org/whl/cpu \
        "torchcodec==${TORCHCODEC_VERSION}" && \
    # Ubuntu 22.04 uses Python 3.10, like the CUDA ML image.
    WHISPER_VERSION="$(sed -n 's/^openai-whisper==//p' requirements.txt)" && \
    pip3 install --no-cache-dir --no-build-isolation -c requirements-ml-runtime.txt \
        "openai-whisper==${WHISPER_VERSION}" && \
    grep -v '^openai-whisper==' requirements.txt > /tmp/requirements-worker.txt && \
    grep -Ev '^(contourpy|scipy|networkx)==' constraints.txt > /tmp/constraints-worker.txt && \
    printf 'scipy==1.15.3\nnetworkx==3.4.2\n' >> /tmp/constraints-worker.txt && \
    pip3 install --no-cache-dir -c /tmp/constraints-worker.txt -c requirements-ml-runtime.txt -r /tmp/requirements-worker.txt && \
    pip3 check && \
    python3 /tmp/verify_ml_runtime.py

# Verify the selected accelerator metadata without requiring a GPU at build time.
RUN python3 -c "import torch; assert '+rocm7.1' in torch.__version__; print('Torch version:', torch.__version__); print('HIP version:', torch.version.hip)"

# =============================================================================
# Stage 3: Final application stage
# =============================================================================
FROM base AS app

# Avoid merging distro/base packaging libraries into the audited builder tree.
RUN rm -rf /usr/local/lib/python3.10/dist-packages/*

# Copy Python packages from deps stage
COPY --from=python-deps /usr/local/lib/python3.10/dist-packages /usr/local/lib/python3.10/dist-packages
COPY --from=python-deps /usr/local/bin /usr/local/bin

# Immutable runtime: installer vendors are unnecessary after build checks.
RUN python3 -m pip uninstall --yes pip && apt-get purge -y python3-pip

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
