# ROCm 6.0 default target; adjust if your host uses a different ROCm version
# Note: Confirm the base image tag matches your driver/toolkit. Examples exist like:
#   pytorch/pytorch:2.4.0-rocm6.0
FROM pytorch/pytorch:2.4.0-rocm6.0

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY python/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Add user to typical GPU groups if needed; depends on host setup
# RUN groupadd -g 44 video && groupadd -g 104 render && usermod -aG video,render root

COPY python/whisperx_runner.py /app/whisperx_runner.py
ENTRYPOINT ["python", "/app/whisperx_runner.py"]
