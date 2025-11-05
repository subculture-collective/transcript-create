import logging
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from app.logging_config import get_logger
from app.settings import settings
from worker.po_token_manager import TokenType, get_token_manager
from worker.token_utils import redact_tokens_from_command

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
    from worker.ytdlp_client_utils import get_client_extractor_args

    # Parse client order from settings
    client_order = [c.strip() for c in settings.YTDLP_CLIENT_ORDER.split(",") if c.strip()]
    disabled_clients = set(c.strip() for c in settings.YTDLP_CLIENTS_DISABLED.split(",") if c.strip())

    # Client descriptions
    client_descriptions = {
        "web_safari": "Safari web client with HLS streaming",
        "ios": "iOS mobile client",
        "android": "Android mobile client",
        "tv": "TV embedded client (safe fallback)",
    }

    strategies = []

    for client in client_order:
        if client in disabled_clients:
            logger.debug(f"Skipping disabled client: {client}")
            continue

        extractor_args = get_client_extractor_args(client)
        if extractor_args:
            headers = ["--user-agent", _get_user_agent(client)]
            # Add Referer header for web_safari
            if client == "web_safari":
                headers.extend(["--add-header", "Referer:https://www.youtube.com"])

            strategies.append(
                ClientStrategy(
                    name=client,
                    extractor_args=extractor_args,
                    headers=headers,
                    description=client_descriptions.get(client, f"{client} client"),
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


def _get_po_tokens() -> dict[str, str]:
    """Get PO tokens from token manager.

    Returns:
        Dictionary with available tokens keyed by type
    """
    # Check feature flag
    if not settings.PO_TOKEN_USE_FOR_AUDIO:
        logger.debug("PO token usage for audio disabled by feature flag")
        return {}

    token_manager = get_token_manager()
    tokens = {}

    # Try to get Player and GVS tokens for audio downloads
    for token_type in [TokenType.PLAYER, TokenType.GVS]:
        token = token_manager.get_token(token_type)
        if token:
            tokens[token_type.value] = token

    if tokens:
        logger.debug("PO tokens available for audio download", extra={"token_types": list(tokens.keys())})

    return tokens


def _yt_dlp_cmd(base_out: Path, url: str, strategy: Optional[ClientStrategy] = None) -> List[str]:
    """Build yt-dlp command with optional client strategy and PO tokens."""
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

    # Add PO tokens if available
    po_tokens = _get_po_tokens()
    if po_tokens:
        # Build extractor args for PO tokens
        # Format: --extractor-args "youtube:po_token=player:TOKEN1;po_token=gvs:TOKEN2"
        token_args = []
        for token_type, token_value in po_tokens.items():
            token_args.append(f"po_token={token_type}:{token_value}")

        if token_args:
            extractor_arg = "youtube:" + ";".join(token_args)
            cmd.extend(["--extractor-args", extractor_arg])
            logger.info(
                "PO tokens added to yt-dlp command",
                extra={"token_types": list(po_tokens.keys())}
            )

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


def _download_with_strategy(url: str, out: Path, strategy: ClientStrategy, attempt: int) -> subprocess.CompletedProcess:
    """Execute a single download attempt with a specific client strategy.

    Args:
        url: YouTube URL to download
        out: Output path for downloaded file
        strategy: Client strategy to use
        attempt: Attempt number for logging

    Returns:
        Completed subprocess result

    Raises:
        subprocess.CalledProcessError: If download fails
    """
    cmd = _yt_dlp_cmd(out, url, strategy)
    logger.info(
        "Running yt-dlp command",
        extra={
            "client": strategy.name,
            "attempt": attempt,
            "command": redact_tokens_from_command(cmd),
        },
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
        timeout=settings.YTDLP_REQUEST_TIMEOUT,
    )

    # Log stderr if present even on success (may contain warnings)
    if result.stderr:
        logger.debug(
            "yt-dlp stderr output",
            extra={
                "client": strategy.name,
                "stderr_snippet": result.stderr[:200],
            },
        )

    return result


def download_audio(url: str, dest_dir: Path) -> Path:
    """Download audio from YouTube URL with client fallback strategy.

    Tries each configured client strategy in order until one succeeds.
    Uses retry with exponential backoff and circuit breaker for resilience.
    Logs structured information about attempts and failures.
    """
    from worker.metrics import youtube_requests_total
    from worker.youtube_resilience import ErrorClass, classify_error, get_circuit_breaker, retry_with_backoff

    out = dest_dir / "raw.m4a"
    strategies = _build_client_strategies()

    # Get circuit breaker for download operations
    circuit_breaker = None
    if settings.YTDLP_CIRCUIT_BREAKER_ENABLED:
        circuit_breaker = get_circuit_breaker("youtube_download")

    last_err: Exception | None = None

    for strategy_idx, strategy in enumerate(strategies):
        logger.info(
            "Attempting download with client strategy",
            extra={
                "client": strategy.name,
                "description": strategy.description,
                "url": url,
            },
        )

        # Create closures with explicit binding to avoid loop variable issues
        # We use a factory function pattern to ensure loop variables are captured correctly
        # Without this, the inner function would reference the loop variable which may change
        def make_download_attempt(strat: ClientStrategy, idx: int):
            """Create download attempt function with explicit parameter binding."""
            def download_attempt():
                """Single download attempt that can be retried."""
                return _download_with_strategy(url, out, strat, idx + 1)
            return download_attempt  # noqa: B023 (false positive - function returned immediately)

        download_attempt = make_download_attempt(strategy, strategy_idx)

        def classify_download_error(e: Exception) -> ErrorClass:
            """Classify download error and handle token invalidation."""
            stderr = getattr(e, "stderr", "") or str(e)
            returncode = getattr(e, "returncode", 0)
            error_class = classify_error(returncode, stderr, e)

            # Check if error indicates invalid/expired PO token
            stderr_lower = stderr.lower()
            is_token_error = (
                error_class == ErrorClass.TOKEN
                or ("po_token" in stderr_lower and ("invalid" in stderr_lower or "expired" in stderr_lower))
                or (("403" in stderr_lower) and ("token" in stderr_lower or "po_token" in stderr_lower))
            )

            if is_token_error:
                token_manager = get_token_manager()
                # Mark only player and GVS tokens as potentially invalid
                for token_type in [TokenType.PLAYER, TokenType.GVS]:
                    token_manager.mark_token_invalid(token_type, reason=error_class.value)
                logger.warning(
                    "Token-related error detected, marking player/gvs tokens invalid",
                    extra={"error_classification": error_class.value, "returncode": returncode}
                )

            return error_class

        try:
            # Use retry with backoff for each client strategy
            retry_with_backoff(
                download_attempt,
                max_attempts=settings.YTDLP_TRIES_PER_CLIENT,
                base_delay=settings.YTDLP_BACKOFF_BASE_DELAY,
                max_delay=settings.YTDLP_BACKOFF_MAX_DELAY,
                circuit_breaker=circuit_breaker,
                classify_func=classify_download_error,
            )

            logger.info(
                "Download succeeded",
                extra={
                    "client": strategy.name,
                },
            )
            youtube_requests_total.labels(operation="download", result="success").inc()
            return out

        except subprocess.CalledProcessError as e:
            last_err = e
            error_class = classify_download_error(e)
            logger.warning(
                "Client strategy failed after retries",
                extra={
                    "client": strategy.name,
                    "error_classification": error_class.value,
                    "returncode": e.returncode,
                },
            )
        except Exception as e:
            last_err = e
            logger.warning(
                "Client strategy raised exception",
                extra={
                    "client": strategy.name,
                    "error": str(e)[:200],
                    "error_type": type(e).__name__,
                },
            )

        # Log failure for this client before moving to next
        logger.info(
            "Client strategy exhausted, trying next",
            extra={
                "client": strategy.name,
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
    youtube_requests_total.labels(operation="download", result="failure").inc()

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
