import logging
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from app.logging_config import get_logger
from app.settings import settings

logger = get_logger(__name__)


@dataclass
class Chunk:
    path: Path
    offset: float  # seconds


@dataclass
class ClientStrategy:
    """Defines a YouTube client strategy for yt-dlp."""

    name: str
    extractor_args: List[str]
    headers: List[str]
    description: str


def _get_user_agent(client: str = "web_safari") -> str:
    """Return appropriate user agent for a given client."""
    user_agents = {
        "web_safari": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        ),
        "ios": "com.google.ios.youtube/19.09.3 (iPhone14,5; U; CPU iOS 15_6 like Mac OS X)",
        "android": "com.google.android.youtube/19.09.37 (Linux; U; Android 13) gzip",
        "tv": "Mozilla/5.0 (ChromiumStylePlatform) Cobalt/Version",
    }
    return user_agents.get(client, user_agents["web_safari"])


def _build_client_strategies() -> List[ClientStrategy]:
    """Build list of client strategies based on settings."""
    # Parse client order from settings
    client_order = [c.strip() for c in settings.YTDLP_CLIENT_ORDER.split(",") if c.strip()]
    disabled_clients = set(c.strip() for c in settings.YTDLP_CLIENTS_DISABLED.split(",") if c.strip())

    strategies = []

    for client in client_order:
        if client in disabled_clients:
            logger.debug(f"Skipping disabled client: {client}")
            continue

        if client == "web_safari":
            # web_safari with HLS preference
            strategies.append(
                ClientStrategy(
                    name="web_safari",
                    extractor_args=["--extractor-args", "youtube:player_client=web_safari"],
                    headers=[
                        "--user-agent",
                        _get_user_agent("web_safari"),
                        "--add-header",
                        "Referer:https://www.youtube.com",
                    ],
                    description="Safari web client with HLS streaming",
                )
            )
        elif client == "ios":
            strategies.append(
                ClientStrategy(
                    name="ios",
                    extractor_args=["--extractor-args", "youtube:player_client=ios"],
                    headers=[
                        "--user-agent",
                        _get_user_agent("ios"),
                    ],
                    description="iOS mobile client",
                )
            )
        elif client == "android":
            strategies.append(
                ClientStrategy(
                    name="android",
                    extractor_args=["--extractor-args", "youtube:player_client=android"],
                    headers=[
                        "--user-agent",
                        _get_user_agent("android"),
                    ],
                    description="Android mobile client",
                )
            )
        elif client == "tv":
            strategies.append(
                ClientStrategy(
                    name="tv",
                    extractor_args=["--extractor-args", "youtube:player_client=tv_embedded"],
                    headers=[
                        "--user-agent",
                        _get_user_agent("tv"),
                    ],
                    description="TV embedded client (safe fallback)",
                )
            )
        else:
            logger.warning(f"Unknown client type in YTDLP_CLIENT_ORDER: {client}")

    if not strategies:
        # Fallback to default strategy if none configured
        logger.warning("No client strategies configured, using default web_safari")
        strategies.append(
            ClientStrategy(
                name="web_safari",
                extractor_args=["--extractor-args", "youtube:player_client=web_safari"],
                headers=[
                    "--user-agent",
                    _get_user_agent("web_safari"),
                    "--add-header",
                    "Referer:https://www.youtube.com",
                ],
                description="Safari web client with HLS streaming (default)",
            )
        )

    return strategies


def _classify_error(returncode: int, stderr: str = "") -> str:
    """Classify yt-dlp error for logging."""
    stderr_lower = stderr.lower()
    if "unavailable" in stderr_lower or "private" in stderr_lower:
        return "video_unavailable"
    elif "sign in" in stderr_lower or "bot" in stderr_lower:
        return "authentication_required"
    elif "throttl" in stderr_lower:
        return "throttling"
    elif "403" in stderr_lower or "forbidden" in stderr_lower:
        return "forbidden"
    elif returncode == 1:
        return "generic_error"
    else:
        return f"error_code_{returncode}"


def _yt_dlp_cmd(base_out: Path, url: str, strategy: Optional[ClientStrategy] = None) -> List[str]:
    """Build yt-dlp command with optional client strategy."""
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
        # Retry a few times internally (-R is the stable alias for --retries)
        "-R",
        "3",
    ]

    # Add client strategy args
    if strategy:
        cmd.extend(strategy.extractor_args)
        cmd.extend(strategy.headers)

    # Add cookies if configured
    if settings.YTDLP_COOKIES_PATH and Path(settings.YTDLP_COOKIES_PATH).exists():
        cmd.extend(["--cookies", settings.YTDLP_COOKIES_PATH])

    # Allow user-provided extra args (from settings)
    if settings.YTDLP_EXTRA_ARGS:
        try:
            cmd.extend(shlex.split(settings.YTDLP_EXTRA_ARGS))
        except Exception:
            # fallback to raw split
            cmd.extend(settings.YTDLP_EXTRA_ARGS.split())

    cmd.append(url)
    return cmd


def download_audio(url: str, dest_dir: Path) -> Path:
    """Download audio from YouTube URL with client fallback strategy.

    Tries each configured client strategy in order until one succeeds.
    Logs structured information about attempts and failures.
    """
    out = dest_dir / "raw.m4a"
    strategies = _build_client_strategies()

    last_err: Exception | None = None
    last_stderr: str = ""

    for strategy in strategies:
        logger.info(
            "Attempting download with client strategy",
            extra={
                "client": strategy.name,
                "description": strategy.description,
                "url": url,
            },
        )

        for try_idx in range(1, settings.YTDLP_TRIES_PER_CLIENT + 1):
            cmd = _yt_dlp_cmd(out, url, strategy)
            logger.info(
                "Running yt-dlp command",
                extra={
                    "client": strategy.name,
                    "attempt": try_idx,
                    "command": " ".join(cmd),
                },
            )

            try:
                subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                total_attempts_made = try_idx + sum(
                    settings.YTDLP_TRIES_PER_CLIENT for _ in range(strategies.index(strategy))
                )
                logger.info(
                    "Download succeeded",
                    extra={
                        "client": strategy.name,
                        "attempt": try_idx,
                        "total_attempts": total_attempts_made,
                    },
                )
                return out
            except subprocess.CalledProcessError as e:
                last_err = e
                last_stderr = e.stderr or ""
                error_class = _classify_error(e.returncode, last_stderr)

                logger.warning(
                    "yt-dlp attempt failed",
                    extra={
                        "client": strategy.name,
                        "attempt": try_idx,
                        "returncode": e.returncode,
                        "error_classification": error_class,
                        "stderr_snippet": last_stderr[:200] if last_stderr else "",
                    },
                )
            except Exception as e:
                last_err = e
                logger.warning(
                    "yt-dlp attempt raised exception",
                    extra={
                        "client": strategy.name,
                        "attempt": try_idx,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

            # Brief pause before retry within the same client
            if try_idx < settings.YTDLP_TRIES_PER_CLIENT:
                time.sleep(settings.YTDLP_RETRY_SLEEP)

        # Log failure for this client before moving to next
        logger.info(
            "Client strategy exhausted, trying next",
            extra={
                "client": strategy.name,
                "attempts": settings.YTDLP_TRIES_PER_CLIENT,
            },
        )

    # All strategies failed
    logger.error(
        "All client strategies failed",
        extra={
            "total_clients_tried": len(strategies),
            "clients": [s.name for s in strategies],
            "url": url,
        },
    )

    if last_err:
        raise last_err
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
