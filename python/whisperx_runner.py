#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone

import torch
import whisperx


def iso_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v is not None and v != "" else default


def health_check():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(json.dumps({
        "time": iso_now(),
        "cuda_available": torch.cuda.is_available(),
        "device": device,
        "torch_version": torch.__version__,
    }))


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--health":
        health_check()
        return
    if len(sys.argv) < 3:
        print("Usage: whisperx_runner.py <chunk_path> <out_json> | --health")
        sys.exit(1)

    chunk_path = sys.argv[1]
    out_json = sys.argv[2]

    # Detect ROCm (AMD), CUDA (NVIDIA), or fallback CPU
    def is_rocm():
        return hasattr(torch.version, "hip") and torch.version.hip is not None

    if torch.cuda.is_available():
        if is_rocm():
            device = "cuda"   # ROCm identifies as "cuda" in PyTorch
            print("[whisperx-runner] Using AMD ROCm GPU.", file=sys.stderr)
        else:
            device = "cuda"
            print("[whisperx-runner] Using NVIDIA CUDA GPU.", file=sys.stderr)
    else:
        device = "cpu"
        print("[whisperx-runner] No GPU detected, using CPU.", file=sys.stderr)

    # Always force large-v3
    model_name = "large-v3"

    # Default compute type
    if device == "cuda":
        compute_type = get_env("WHISPERX_COMPUTE_TYPE", "float16")
    else:
        compute_type = get_env("WHISPERX_COMPUTE_TYPE", "int8")

    # Optional override: user can still force CPU explicitly
    force_cpu = get_env("WHISPERX_FORCE_CPU", "").lower() in ["1", "true", "yes"]
    if force_cpu:
        if device != "cpu":
            print("[whisperx-runner] Forcing CPU mode (ignoring GPU).", file=sys.stderr)
        device = "cpu"
        compute_type = "int8"

    # Load audio and model
    audio = whisperx.load_audio(chunk_path)
    try:
        model = whisperx.load_model(model_name, device=device, compute_type=compute_type)
    except Exception as e:
        err_txt = str(e)
        # Detect execstack / ctranslate2 issue
        if "cannot enable executable stack" in err_txt.lower():
            print(
                "[whisperx-runner] Detected executable stack restriction loading ctranslate2.\n"
                "Rebuild your image ensuring binutils/execstack clears the bit, e.g.:\n"
                "  docker build -f docker/whisperx.cpu.Dockerfile -t local/whisperx:cpu .\n"
                "If you already rebuilt, verify: docker run --rm local/whisperx:cpu bash -c \"find /usr/local/lib/python3.10/site-packages -name 'libctranslate2*.so*' -exec execstack -q {} +\"\n",
                file=sys.stderr,
            )
        if force_cpu:
            raise
        fallback_reason = err_txt
        print(f"Primary model load failed: {fallback_reason}. Falling back to CPU with large-v3...", file=sys.stderr)
        device = "cpu"
        compute_type = "int8"
        model_name = "large-v3"
        model = whisperx.load_model(model_name, device=device, compute_type=compute_type)

    result = model.transcribe(audio, batch_size=int(get_env("WHISPERX_BATCH_SIZE", "16")), language=get_env("WHISPERX_LANGUAGE", "en"))
    segs = result.get("segments", []) or []

    # Alignment for word-level timestamps
    try:
        align_model, metadata = whisperx.load_align_model(
            language_code=get_env("WHISPERX_LANGUAGE", "en"), device=device
        )
        aligned = whisperx.align(
            segs,
            align_model,
            metadata,
            audio,
            device,
            return_char_alignments=False,
        )
        segs = aligned.get("segments", []) or segs
    except Exception as e:
        # Proceed without alignment if anything fails
        print(f"Alignment skipped: {e}", file=sys.stderr)

    # Build TranscriptJson
    segments = []
    words = []
    for s in segs:
        # segment fields from whisperx: start, end, text
        start = float(s.get("start", 0.0) or 0.0)
        end = float(s.get("end", start) or start)
        text = s.get("text", "") or ""
        segments.append(
            {
                "startSec": start,
                "endSec": end,
                "text": text,
            }
        )

        # word-level if available
        for w in s.get("words", []) or []:
            w_start = float(w.get("start", start) or start)
            w_end = float(w.get("end", w_start) or w_start)
            w_text = w.get("word") or w.get("text") or ""
            words.append(
                {
                    "startSec": w_start,
                    "endSec": w_end,
                    "text": w_text,
                }
            )

    transcript = {
        "videoId": "TBD",
        "source": {"url": ""},
        "processing": {
            "createdAt": iso_now(),
            "engine": f"whisperx@{model_name}",
            "language": get_env("WHISPERX_LANGUAGE", "en"),
            "chunkSec": 0,
            "overlapSec": 0,
        },
        "segments": segments,
        "words": words,
        "snippets": [],
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
