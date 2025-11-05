"""
Prometheus metrics definitions for the worker service.

This module defines all metrics collected by the worker including:
- Transcription pipeline metrics (duration, chunks)
- Video processing metrics (pending, in-progress)
- Model loading metrics
- Optional GPU metrics
"""

from prometheus_client import Counter, Gauge, Histogram

# Worker Processing Metrics
transcription_duration_seconds = Histogram(
    "transcription_duration_seconds",
    "Time spent transcribing video audio in seconds",
    ["model"],
    buckets=(10, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200),
)

download_duration_seconds = Histogram(
    "download_duration_seconds",
    "Time spent downloading video audio in seconds",
    buckets=(5, 10, 30, 60, 120, 300, 600, 900),
)

transcode_duration_seconds = Histogram(
    "transcode_duration_seconds",
    "Time spent transcoding audio to WAV in seconds",
    buckets=(1, 5, 10, 30, 60, 120, 300),
)

diarization_duration_seconds = Histogram(
    "diarization_duration_seconds",
    "Time spent on speaker diarization in seconds",
    buckets=(10, 30, 60, 120, 300, 600, 900, 1800),
)

# Video Queue Metrics
videos_pending = Gauge(
    "videos_pending",
    "Number of videos pending processing",
)

videos_in_progress = Gauge(
    "videos_in_progress",
    "Number of videos currently being processed",
    ["state"],  # downloading, transcoding, transcribing
)

videos_processed_total = Counter(
    "videos_processed_total",
    "Total number of videos processed",
    ["result"],  # completed, failed
)

# Whisper Model Metrics
whisper_model_load_seconds = Histogram(
    "whisper_model_load_seconds",
    "Time to load Whisper model in seconds",
    ["model", "backend"],
    buckets=(1, 5, 10, 30, 60, 120, 300),
)

whisper_chunk_transcription_seconds = Histogram(
    "whisper_chunk_transcription_seconds",
    "Time to transcribe a single audio chunk in seconds",
    ["model"],
    buckets=(5, 10, 30, 60, 120, 300, 600),
)

chunk_count = Histogram(
    "chunk_count",
    "Number of audio chunks per video",
    buckets=(1, 2, 3, 5, 10, 15, 20, 30, 50),
)

# GPU Metrics (optional, collected when available)
gpu_memory_used_bytes = Gauge(
    "gpu_memory_used_bytes",
    "GPU memory currently in use in bytes",
    ["device"],
)

gpu_memory_total_bytes = Gauge(
    "gpu_memory_total_bytes",
    "Total GPU memory available in bytes",
    ["device"],
)

# Worker State Metrics
worker_info = Gauge(
    "worker_info",
    "Worker information",
    ["whisper_model", "whisper_backend", "force_gpu"],
)

# PO Token Metrics
po_token_retrievals_total = Counter(
    "po_token_retrievals_total",
    "Total number of PO token retrievals",
    ["token_type", "result"],  # result: success, failed, cached
)

po_token_provider_attempts_total = Counter(
    "po_token_provider_attempts_total",
    "Total number of provider attempts",
    ["provider", "token_type"],
)

po_token_cache_hits_total = Counter(
    "po_token_cache_hits_total",
    "Total number of token cache hits",
    ["token_type"],
)

po_token_cache_misses_total = Counter(
    "po_token_cache_misses_total",
    "Total number of token cache misses",
    ["token_type"],
)

po_token_retrieval_latency_seconds = Histogram(
    "po_token_retrieval_latency_seconds",
    "Token retrieval latency in seconds",
    ["provider", "token_type"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10),
)

po_token_failures_total = Counter(
    "po_token_failures_total",
    "Total number of token failures (invalidations)",
    ["token_type", "reason"],
)

# YouTube Resilience Metrics
youtube_retry_attempts_total = Counter(
    "youtube_retry_attempts_total",
    "Total number of retry attempts for YouTube requests",
    ["operation", "error_class"],  # operation: download, metadata, captions
)

youtube_backoff_delays_seconds = Histogram(
    "youtube_backoff_delays_seconds",
    "Backoff delays applied between retries in seconds",
    ["operation"],
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60),
)

youtube_circuit_breaker_state = Gauge(
    "youtube_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open)",
    ["name"],
)

youtube_circuit_breaker_transitions_total = Counter(
    "youtube_circuit_breaker_transitions_total",
    "Total number of circuit breaker state transitions",
    ["name", "from_state", "to_state"],
)

youtube_requests_total = Counter(
    "youtube_requests_total",
    "Total number of YouTube requests",
    ["operation", "result"],  # result: success, failure
)

# Ingestion observability metrics
ytdlp_operation_duration_seconds = Histogram(
    "ytdlp_operation_duration_seconds",
    "Duration of yt-dlp operations in seconds",
    ["operation", "client"],  # operation: download, metadata, captions; client: web_safari, ios, android, tv, default
    buckets=(1, 2, 5, 10, 20, 30, 60, 120, 180, 300, 600),
)

ytdlp_operation_attempts_total = Counter(
    "ytdlp_operation_attempts_total",
    "Total number of yt-dlp operation attempts",
    ["operation", "client", "result"],  # result: success, failure
)

ytdlp_operation_errors_total = Counter(
    "ytdlp_operation_errors_total",
    "Total number of yt-dlp operation errors by classification",
    ["operation", "client", "error_class"],  # error_class: network, throttle, auth, token, not_found, timeout, unknown
)

ytdlp_token_usage_total = Counter(
    "ytdlp_token_usage_total",
    "Total number of yt-dlp operations with/without PO tokens",
    ["operation", "has_token"],  # has_token: true, false
)


def setup_worker_info(whisper_model: str, whisper_backend: str, force_gpu: bool):
    """Set worker information metric."""
    worker_info.labels(
        whisper_model=whisper_model,
        whisper_backend=whisper_backend,
        force_gpu=str(force_gpu),
    ).set(1)


def try_collect_gpu_metrics():
    """
    Attempt to collect GPU memory metrics from ROCm or CUDA.
    Returns True if successful, False otherwise.
    """
    # Try ROCm first
    try:
        import subprocess

        result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram", "--json"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            import json

            data = json.loads(result.stdout)
            for device_id, info in data.items():
                if isinstance(info, dict) and "VRAM Total Memory (B)" in info:
                    total = int(info["VRAM Total Memory (B)"])
                    used = int(info["VRAM Total Used Memory (B)"])
                    gpu_memory_total_bytes.labels(device=device_id).set(total)
                    gpu_memory_used_bytes.labels(device=device_id).set(used)
            return True
    except Exception:
        pass

    # Try PyTorch with CUDA
    try:
        import torch

        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                total = torch.cuda.get_device_properties(i).total_memory
                used = torch.cuda.memory_allocated(i)
                gpu_memory_total_bytes.labels(device=f"cuda:{i}").set(total)
                gpu_memory_used_bytes.labels(device=f"cuda:{i}").set(used)
            return True
    except Exception:
        pass

    return False
