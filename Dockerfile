FROM rocm/dev-ubuntu-22.04:6.0.2

ARG ROCM_WHEEL_INDEX=https://download.pytorch.org/whl/rocm6.0
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    ffmpeg python3 python3-pip git build-essential \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# Install app requirements first
RUN pip3 install --no-cache-dir -r requirements.txt && \
    # Remove any torch variants pulled in by other deps
    (pip3 uninstall -y torch torchvision torchaudio || true) && \
    # Install ROCm PyTorch wheels explicitly (ensure ROCm backend is used)
    pip3 install --no-cache-dir --index-url ${ROCM_WHEEL_INDEX} \
        torch==2.4.1+rocm6.0 torchaudio==2.4.1+rocm6.0 && \
    python3 - <<'PY'
import torch
print('Torch version:', torch.__version__)
print('HIP version:', getattr(torch.version, 'hip', None))
print('cuda.is_available:', torch.cuda.is_available())
PY

COPY . /app

# Optional: set default PDF font if present
ENV PDF_FONT_PATH=/app/fonts/DejaVuSerif.ttf

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
