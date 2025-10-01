ARG ROCM_VERSION=6.0
ARG PYTORCH_VERSION=2.4.0
ARG TORCHAUDIO_VERSION=2.4.0
ARG TORCHVISION_VERSION=0.19.0
# Official ROCm developer base; choose version matching your host drivers (e.g., 6.0, 6.1)
FROM rocm/dev-ubuntu-22.04:${ROCM_VERSION}

# Re-declare ARGs after FROM so they're available in this build stage
ARG ROCM_VERSION
ARG PYTORCH_VERSION
ARG TORCHAUDIO_VERSION
ARG TORCHVISION_VERSION

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    ffmpeg git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip

# Install PyTorch ROCm wheels via the official index URL matching ROCM_VERSION
# You can override ROCM_WHL_INDEX at build time if needed
ARG ROCM_WHL_INDEX=https://download.pytorch.org/whl/rocm6.0
RUN python3 -m pip install --no-cache-dir \
    "torch==${PYTORCH_VERSION}+rocm${ROCM_VERSION}" \
    "torchaudio==${TORCHAUDIO_VERSION}+rocm${ROCM_VERSION}" \
    "torchvision==${TORCHVISION_VERSION}+rocm${ROCM_VERSION}" \
    --index-url ${ROCM_WHL_INDEX}

WORKDIR /app
COPY python/requirements.txt /app/requirements.txt
# requirements.txt includes whisperx and may list torch/torchaudio, which are already satisfied
RUN python3 -m pip install --no-cache-dir -r /app/requirements.txt

COPY python/whisperx_runner.py /app/whisperx_runner.py
# Recommended: mount a host Hugging Face cache directory (set HF_HOME env; e.g. /app/hf-cache or /root/.cache/huggingface)
# Example docker run addition:
#   -v /host/path/.hf-cache:/root/.cache/huggingface -e HF_HOME=/root/.cache/huggingface
ENV WHISPERX_MODEL=large-v2 \
    WHISPERX_LANGUAGE=en \
    WHISPERX_BATCH_SIZE=16 \
    WHISPERX_COMPUTE_TYPE=float16
ENTRYPOINT ["python3", "/app/whisperx_runner.py"]
