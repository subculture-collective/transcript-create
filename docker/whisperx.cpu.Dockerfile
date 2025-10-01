FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git binutils patchelf && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY python/requirements.txt /app/requirements.txt
# Install CPU wheels for torch
RUN pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install -r requirements.txt && \
    echo 'Fixing executable stack flags (ctranslate2)...' && \
    find /usr/local/lib/python3.10/site-packages/ -maxdepth 3 -type f -name 'libctranslate2*.so*' -print -exec execstack -c {} \; || true

COPY python/whisperx_runner.py /app/whisperx_runner.py
# Recommended: mount persistent Hugging Face cache volume, e.g.:
#   -v /host/path/.hf-cache:/root/.cache/huggingface -e HF_HOME=/root/.cache/huggingface
ENV WHISPERX_MODEL=large-v2 \
    WHISPERX_LANGUAGE=en \
    WHISPERX_BATCH_SIZE=16 \
    WHISPERX_COMPUTE_TYPE=int8
ENTRYPOINT ["python", "/app/whisperx_runner.py"]
