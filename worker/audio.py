import os
import time
import shlex
import subprocess
import logging
from dataclasses import dataclass
from pathlib import Path

from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class Chunk:
    path: Path
    offset: float  # seconds


def _yt_dlp_cmd(base_out: Path, url: str, extra: list[str] | None = None) -> list[str]:
    cmd = [
        "yt-dlp",
        "-v",
        "-f",
        "bestaudio",
        "-o",
        str(base_out),
        # be nice to YouTube infra
        "--sleep-requests",
        "1",
        # Retry a few times (-R is the stable alias for --retries)
        "-R",
        "3",
    ]
    # allow user-provided extra args (space-separated string)
    ytdlp_extra = os.getenv("YTDLP_EXTRA_ARGS", "").strip()
    if ytdlp_extra:
        try:
            cmd.extend(shlex.split(ytdlp_extra))
        except Exception:
            # fallback to raw split
            cmd.extend(ytdlp_extra.split())
    if extra:
        cmd.extend(extra)
    cmd.append(url)
    return cmd


def download_audio(url: str, dest_dir: Path) -> Path:
    out = dest_dir / "raw.m4a"
    attempts: list[tuple[str, list[str]]] = []
    # 1) default
    attempts.append(("default", []))
    # 2) try iOS client
    attempts.append(("ios-client", ["--extractor-args", "youtube:player_client=ios"]))
    # 3) try android client
    attempts.append(("android-client", ["--extractor-args", "youtube:player_client=android"]))
    # 4) add UA + Referer headers
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    attempts.append(("ua+referer", ["--user-agent", ua, "--add-header", "Referer:https://www.youtube.com"]))
    # 5) use cookies if provided
    cookies_path = os.getenv("YTDLP_COOKIES")
    if cookies_path and Path(cookies_path).exists():
        attempts.append(("cookies", ["--cookies", cookies_path]))

    last_err: Exception | None = None
    per_attempt_tries = int(os.getenv("YTDLP_TRIES", "2") or "2")
    sleep_between = float(os.getenv("YTDLP_TRY_SLEEP", "1") or "1")
    for label, extra in attempts:
        cmd = _yt_dlp_cmd(out, url, extra)
        for try_idx in range(1, per_attempt_tries + 1):
            logger.info(
                "Running yt-dlp command",
                extra={"attempt": label, "try": try_idx, "command": " ".join(cmd)},
            )
            try:
                subprocess.check_call(cmd)
                return out
            except subprocess.CalledProcessError as e:
                last_err = e
                logger.warning(
                    "yt-dlp attempt failed",
                    extra={"attempt": label, "try": try_idx, "returncode": e.returncode},
                )
            except Exception as e:  # network or other unexpected
                last_err = e
                logger.warning(
                    "yt-dlp attempt raised exception",
                    extra={"attempt": label, "try": try_idx, "error": str(e)},
                )
            # brief pause before retry within the same attempt profile
            if try_idx < per_attempt_tries:
                time.sleep(sleep_between)

    # If all attempts failed, raise the last error
    if last_err:
        raise last_err
    # Safety (should not reach)
    raise RuntimeError("yt-dlp failed with no captured exception")


def ensure_wav_16k(src: Path) -> Path:
    wav = src.parent / "audio_16k.wav"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "info",
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(wav),
    ]
    logger.info("Running ffmpeg command", extra={"command": " ".join(cmd)})
    subprocess.check_call(cmd)
    return wav


def get_duration_seconds(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-hide_banner",
        "-v",
        "info",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
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
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-y",
            "-i",
            str(wav),
            "-ss",
            f"{start}",
            "-to",
            f"{end}",
            "-c",
            "copy",
            str(chunk_path),
        ]
        logging.info("Running: %s", " ".join(cmd))
        subprocess.check_call(cmd)
        chunks.append(Chunk(path=chunk_path, offset=start))
        start = end
        idx += 1
    return chunks
