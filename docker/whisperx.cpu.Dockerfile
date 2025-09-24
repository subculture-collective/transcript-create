FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY python/requirements.txt /app/requirements.txt
# Install CPU wheels for torch
RUN pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install -r requirements.txt

COPY python/whisperx_runner.py /app/whisperx_runner.py
ENTRYPOINT ["python", "/app/whisperx_runner.py"]
