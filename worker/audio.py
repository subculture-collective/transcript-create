import subprocess
import logging
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Chunk:
    path: Path
    offset: float  # seconds

def download_audio(url: str, dest_dir: Path) -> Path:
    out = dest_dir / "raw.m4a"
    cmd = ["yt-dlp", "-v", "-f", "bestaudio", "-o", str(out), url]
    logging.info("Running: %s", " ".join(cmd))
    subprocess.check_call(cmd)
    return out

def ensure_wav_16k(src: Path) -> Path:
    wav = src.parent / "audio_16k.wav"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "info", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)]
    logging.info("Running: %s", " ".join(cmd))
    subprocess.check_call(cmd)
    return wav

def get_duration_seconds(path: Path) -> float:
    cmd = [
        "ffprobe","-hide_banner","-v","info","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)
    ]
    logging.info("Running: %s", " ".join(cmd))
    out = subprocess.check_output(cmd).decode().strip()
    return float(out)

def chunk_audio(wav: Path, chunk_seconds: int):
    dur = get_duration_seconds(wav)
    if dur <= chunk_seconds:
        logging.info("Duration %.2fs <= chunk size %ss, using single chunk", dur, chunk_seconds)
        return [Chunk(path=wav, offset=0.0)]
    chunks = []
    idx = 0
    start = 0.0
    while start < dur:
        end = min(start + chunk_seconds, dur)
        chunk_path = wav.parent / f"chunk_{idx:04d}.wav"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "info", "-y", "-i", str(wav),
            "-ss", f"{start}", "-to", f"{end}",
            "-c", "copy", str(chunk_path)
        ]
        logging.info("Running: %s", " ".join(cmd))
        subprocess.check_call(cmd)
        chunks.append(Chunk(path=chunk_path, offset=start))
        start = end
        idx += 1
    return chunks
