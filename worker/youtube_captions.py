from __future__ import annotations

import json
import logging
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.logging_config import get_logger
from app.settings import settings
from worker.po_token_manager import TokenType, get_token_manager
from worker.token_utils import redact_tokens_from_command
from worker.youtube.errors import YouTubeErrorKind, classify_youtube_error
from worker.youtube.yt_dlp_executor import YtDlpError, YtDlpExecutor

logger = get_logger(__name__)

# Import metrics at module level, but handle gracefully if not available
try:
    from worker.metrics import (
        ytdlp_operation_attempts_total,
        ytdlp_operation_duration_seconds,
        ytdlp_operation_errors_total,
        ytdlp_token_usage_total,
    )

    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False

    # Define no-op dummies if metrics are unavailable
    class _DummyMetric:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

    ytdlp_operation_attempts_total = _DummyMetric()
    ytdlp_operation_duration_seconds = _DummyMetric()
    ytdlp_operation_errors_total = _DummyMetric()
    ytdlp_token_usage_total = _DummyMetric()


@dataclass
class YTSegment:
    start: float
    end: float
    text: str


@dataclass
class YTCaptionTrack:
    url: str
    language: Optional[str]
    kind: str  # 'auto' or 'manual'
    ext: str  # 'json3', 'vtt', etc.


class YouTubeCaptionFetchError(RuntimeError):
    """Caption track exists, but download or parsing failed transiently/ambiguously."""


class YouTubeCaptionRateLimitError(YouTubeCaptionFetchError):
    """Caption download hit an explicit YouTube rate limit."""


def _build_metadata_strategies() -> List[Tuple[str, List[str]]]:
    """Build list of client strategies for metadata extraction.

    Returns list of (client_name, extractor_args) tuples.
    """
    from worker.ytdlp_client_utils import get_client_extractor_args

    strategies = []
    client_order = [c.strip() for c in settings.YTDLP_CLIENT_ORDER.split(",") if c.strip()]
    disabled_clients = set(c.strip() for c in settings.YTDLP_CLIENTS_DISABLED.split(",") if c.strip())

    for client in client_order:
        if client in disabled_clients:
            continue

        extractor_args = get_client_extractor_args(client)
        if extractor_args is not None:
            strategies.append((client, extractor_args))
        else:
            logger.warning(f"Unknown YTDLP client '{client}' in YTDLP_CLIENT_ORDER; skipping.")

    if not strategies:
        strategies.append(("default", []))

    return strategies


def _get_subs_token() -> Optional[str]:
    """Get Subs PO token from token manager.

    Returns:
        Token string or None if unavailable
    """
    # Check feature flag
    if not settings.PO_TOKEN_USE_FOR_CAPTIONS:
        logger.debug("PO token usage for captions disabled by feature flag")
        return None

    token_manager = get_token_manager()
    token = token_manager.get_token(TokenType.SUBS)

    if token:
        logger.debug("Subs token available for caption fetch")
    else:
        logger.debug("No Subs token available")

    return token


def _yt_dlp_json(url: str) -> Dict[str, Any]:
    """Return yt-dlp JSON metadata for a YouTube URL using client fallback strategy with retry."""
    from pathlib import Path

    from worker.metrics import youtube_requests_total
    from worker.youtube_resilience import (
        ErrorClass,
        YouTubeRateLimitError,
        classify_error,
        get_circuit_breaker,
        retry_with_backoff,
    )

    strategies = _build_metadata_strategies()

    # Get circuit breaker for metadata operations
    circuit_breaker = None
    if settings.YTDLP_CIRCUIT_BREAKER_ENABLED:
        circuit_breaker = get_circuit_breaker("youtube_metadata")

    last_error = None

    for client_name, extractor_args in strategies:
        # Use factory functions to capture loop variables correctly for retry closures
        def make_fetch_metadata(cname: str, cargs: List[str]):
            """Create metadata fetch function with explicit parameter binding."""
            def fetch_metadata():
                """Single metadata fetch attempt that can be retried."""
                cmd = ["-J"]
                cmd.extend(cargs)

                # Add cookies if configured
                if settings.YTDLP_COOKIES_PATH and Path(settings.YTDLP_COOKIES_PATH).exists():
                    cmd.extend(["--cookies", settings.YTDLP_COOKIES_PATH])

                # Add Subs PO token if available
                subs_token = _get_subs_token()
                has_token = bool(subs_token)
                if subs_token:
                    # Format: --extractor-args "youtube:po_token=subs:TOKEN"
                    extractor_arg = f"youtube:po_token=subs:{subs_token}"
                    cmd.extend(["--extractor-args", extractor_arg])
                    logger.info("Subs token added to metadata fetch command")

                cmd.append(url)

                logger.info(
                    "Fetching metadata with client",
                    extra={
                        "operation": "metadata",
                        "client": cname,
                        "command": redact_tokens_from_command(["yt-dlp", *cmd]),
                        "has_token": has_token,
                    },
                )

                start_time = time.time()
                try:
                    executor = YtDlpExecutor(timeout=settings.YTDLP_REQUEST_TIMEOUT)
                    metadata = executor.run_json(cmd)
                    duration = time.time() - start_time

                    logger.info(
                        "Metadata fetch succeeded",
                        extra={
                            "operation": "metadata",
                            "client": cname,
                            "exit_code": 0,
                            "duration_seconds": round(duration, 2),
                            "has_token": has_token,
                        },
                    )

                    # Update metrics
                    ytdlp_operation_duration_seconds.labels(operation="metadata", client=cname).observe(duration)
                    ytdlp_operation_attempts_total.labels(operation="metadata", client=cname, result="success").inc()
                    ytdlp_token_usage_total.labels(operation="metadata", has_token=str(has_token).lower()).inc()

                    return metadata

                except YtDlpError as e:
                    duration = time.time() - start_time

                    error_class = classify_error(e.returncode or 1, e.stderr, e)

                    logger.warning(
                        "Metadata fetch failed",
                        extra={
                            "operation": "metadata",
                            "client": cname,
                            "exit_code": e.returncode,
                            "error_class": error_class.value,
                            "duration_seconds": round(duration, 2),
                            "has_token": has_token,
                            "stderr_snippet": e.stderr[:200],
                        },
                    )

                    ytdlp_operation_duration_seconds.labels(operation="metadata", client=cname).observe(duration)
                    ytdlp_operation_attempts_total.labels(operation="metadata", client=cname, result="failure").inc()
                    ytdlp_operation_errors_total.labels(
                        operation="metadata", client=cname, error_class=error_class.value
                    ).inc()
                    ytdlp_token_usage_total.labels(operation="metadata", has_token=str(has_token).lower()).inc()

                    raise subprocess.CalledProcessError(e.returncode or 1, e.command, stderr=e.stderr) from e

                except subprocess.CalledProcessError as e:
                    duration = time.time() - start_time

                    error_class = classify_error(e.returncode, e.stderr or "", e)

                    logger.warning(
                        "Metadata fetch failed",
                        extra={
                            "operation": "metadata",
                            "client": cname,
                            "exit_code": e.returncode,
                            "error_class": error_class.value,
                            "duration_seconds": round(duration, 2),
                            "has_token": has_token,
                            "stderr_snippet": (e.stderr or "")[:200],
                        },
                    )

                    # Update metrics
                    ytdlp_operation_duration_seconds.labels(operation="metadata", client=cname).observe(duration)
                    ytdlp_operation_attempts_total.labels(operation="metadata", client=cname, result="failure").inc()
                    ytdlp_operation_errors_total.labels(
                        operation="metadata", client=cname, error_class=error_class.value
                    ).inc()
                    ytdlp_token_usage_total.labels(operation="metadata", has_token=str(has_token).lower()).inc()

                    raise

            return fetch_metadata  # noqa: B023 (false positive - function returned immediately)

        fetch_metadata = make_fetch_metadata(client_name, extractor_args)

        def make_classify_metadata_error(cname: str):
            """Create error classifier with explicit parameter binding."""
            def classify_metadata_error(e: Exception) -> ErrorClass:
                """Classify metadata fetch error and handle token invalidation."""
                stderr = getattr(e, "stderr", "") or str(e)
                returncode = getattr(e, "returncode", 0)
                error_class = classify_error(returncode, stderr, e)

                # Check if error indicates invalid/expired Subs token
                stderr_lower = stderr.lower()
                is_token_error = (
                    error_class == ErrorClass.TOKEN
                    or ("po_token" in stderr_lower and ("invalid" in stderr_lower or "expired" in stderr_lower))
                    or (("403" in stderr_lower) and ("token" in stderr_lower or "po_token" in stderr_lower))
                    or ("token" in stderr_lower and "expired" in stderr_lower)
                )

                if is_token_error:
                    token_manager = get_token_manager()
                    token_manager.mark_token_invalid(TokenType.SUBS, reason="metadata_fetch_failed")
                    logger.warning(
                        "Subs token marked invalid during metadata fetch",
                        extra={"client": cname, "returncode": returncode}
                    )

                return error_class
            return classify_metadata_error  # noqa: B023 (false positive - function returned immediately)

        classify_metadata_error = make_classify_metadata_error(client_name)

        try:
            # Use retry with backoff for metadata fetch
            result = retry_with_backoff(
                fetch_metadata,
                max_attempts=settings.YTDLP_TRIES_PER_CLIENT,
                base_delay=settings.YTDLP_BACKOFF_BASE_DELAY,
                max_delay=settings.YTDLP_BACKOFF_MAX_DELAY,
                circuit_breaker=circuit_breaker,
                classify_func=classify_metadata_error,
            )
            youtube_requests_total.labels(operation="metadata", result="success").inc()
            return result

        except subprocess.CalledProcessError as e:
            last_error = e
            error_class = classify_metadata_error(e)
            logger.warning(
                f"Metadata fetch failed with {client_name}: {e.returncode}",
                extra={"error_class": error_class.value, "stderr_snippet": (e.stderr or "")[:200]}
            )
            if error_class == ErrorClass.THROTTLE:
                raise YouTubeRateLimitError(
                    "YouTube rate-limited caption metadata fetching; pause caption ingest before retrying."
                ) from e
        except Exception as e:
            last_error = e
            error_class = classify_metadata_error(e)
            logger.warning(
                f"Metadata fetch raised exception with {client_name}: {e}",
                extra={"error_class": error_class.value}
            )
            if error_class == ErrorClass.THROTTLE:
                raise

    # All strategies failed
    youtube_requests_total.labels(operation="metadata", result="failure").inc()
    if last_error:
        raise last_error
    raise RuntimeError("Failed to fetch metadata with all client strategies")


def _pick_auto_caption(data: dict) -> Optional[YTCaptionTrack]:
    """Select an auto-generated caption track if available.

    yt-dlp JSON typically contains `automatic_captions` keyed by language code.
    We prefer English variants first, otherwise pick the first available.
    """
    auto = data.get("automatic_captions") or {}
    if not auto:
        return None
    # Preferred order of language keys
    prefs = ["en", "en-US", "en-GB"]
    # Prefer json3, then vtt
    prefer_ext_order = ["json3", "vtt"]
    candidates: List[Tuple[str, str, str]] = []  # (lang, url, ext)
    saw_caption_track = False
    for lang, tracks in auto.items():
        for t in tracks:
            if t.get("url"):
                saw_caption_track = True
            ext = t.get("ext")
            if ext in ("json3", "vtt") and t.get("url"):
                candidates.append((lang, t.get("url"), ext))
    if not candidates:
        if saw_caption_track:
            raise YouTubeCaptionFetchError("Caption tracks found, but none use supported json3/vtt formats")
        return None
    # choose preferred language and preferred ext
    for ext in prefer_ext_order:
        for p in prefs:
            for lang, u, e in candidates:
                if lang == p and e == ext:
                    return YTCaptionTrack(url=u, language=lang, kind="auto", ext=e)
        # fallback to any language for this ext
        for lang, u, e in candidates:
            if e == ext:
                return YTCaptionTrack(url=u, language=lang, kind="auto", ext=e)
    # else pick first
    lang, u, e = candidates[0]
    return YTCaptionTrack(url=u, language=lang, kind="auto", ext=e)


def _download_caption_with_ytdlp(url: str, youtube_id: str, track: YTCaptionTrack) -> Optional[bytes]:
    """Fallback caption download using yt-dlp's subtitle writer."""
    language = track.language or "en"
    ext = track.ext or "json3"
    with tempfile.TemporaryDirectory(prefix="yt-caption-") as tmpdir:
        outtmpl = str(Path(tmpdir) / "%(id)s.%(ext)s")
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-subs",
            "--remote-components",
            "ejs:github",
            "--sub-langs",
            language,
            "--sub-format",
            ext,
            "-o",
            outtmpl,
        ]
        if settings.YTDLP_COOKIES_PATH and Path(settings.YTDLP_COOKIES_PATH).exists():
            cmd.extend(["--cookies", settings.YTDLP_COOKIES_PATH])
        if settings.YTDLP_EXTRA_ARGS:
            cmd.extend(shlex.split(settings.YTDLP_EXTRA_ARGS))
        cmd.append(url)

        start_time = time.time()
        logger.info(
            "Falling back to yt-dlp caption download",
            extra={
                "operation": "captions",
                "youtube_id": youtube_id,
                "language": language,
                "ext": ext,
                "command": redact_tokens_from_command(cmd),
            },
        )
        proc = subprocess.run(cmd, capture_output=True, text=False, timeout=settings.YTDLP_REQUEST_TIMEOUT)
        duration = time.time() - start_time
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace")[:500]
            logger.warning(
                "yt-dlp caption fallback failed",
                extra={
                    "operation": "captions",
                    "youtube_id": youtube_id,
                    "exit_code": proc.returncode,
                    "duration_seconds": round(duration, 2),
                    "stderr": stderr,
                },
            )
            ytdlp_operation_duration_seconds.labels(operation="captions", client="yt-dlp").observe(duration)
            ytdlp_operation_attempts_total.labels(operation="captions", client="yt-dlp", result="failure").inc()
            return None

        candidates = sorted(Path(tmpdir).glob(f"*.{language}.{ext}")) or sorted(Path(tmpdir).glob(f"*.{ext}"))
        if not candidates:
            logger.warning(
                "yt-dlp caption fallback produced no caption file",
                extra={"operation": "captions", "youtube_id": youtube_id, "duration_seconds": round(duration, 2)},
            )
            ytdlp_operation_duration_seconds.labels(operation="captions", client="yt-dlp").observe(duration)
            ytdlp_operation_attempts_total.labels(operation="captions", client="yt-dlp", result="failure").inc()
            return None

        payload = candidates[0].read_bytes()
        logger.info(
            "yt-dlp caption fallback succeeded",
            extra={
                "operation": "captions",
                "youtube_id": youtube_id,
                "language": language,
                "ext": ext,
                "duration_seconds": round(duration, 2),
                "size_bytes": len(payload),
            },
        )
        ytdlp_operation_duration_seconds.labels(operation="captions", client="yt-dlp").observe(duration)
        return payload


def _parse_vtt_to_segments(vtt_bytes: bytes) -> List[YTSegment]:
    def parse_ts(ts: str) -> float:
        # HH:MM:SS.mmm or MM:SS.mmm
        ts = ts.strip()
        parts = ts.split(":")
        if len(parts) == 3:
            h, m, s = parts
            sec, ms = (s.replace(",", ".").split(".") + ["0"])[:2]
            return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms[:3]) / 1000.0
        elif len(parts) == 2:
            m, s = parts
            sec, ms = (s.replace(",", ".").split(".") + ["0"])[:2]
            return int(m) * 60 + int(sec) + int(ms[:3]) / 1000.0
        return 0.0

    text = vtt_bytes.decode(errors="ignore").splitlines()
    segs: List[YTSegment] = []
    i = 0
    # Skip WEBVTT header if present
    if i < len(text) and text[i].strip().upper().startswith("WEBVTT"):
        i += 1
    # Skip optional header metadata lines until blank
    while i < len(text) and text[i].strip() != "":
        i += 1
    # Consume blank
    while i < len(text) and text[i].strip() == "":
        i += 1
    while i < len(text):
        # Optional cue id
        if i < len(text) and text[i].strip() and "-->" not in text[i]:
            i += 1
        if i >= len(text):
            break
        if "-->" not in text[i]:
            i += 1
            continue
        timing = text[i].strip()
        i += 1
        try:
            left, right = timing.split("-->")
            start = parse_ts(left)
            end = parse_ts(right)
        except Exception:
            # Malformed timing line, skip block
            while i < len(text) and text[i].strip() != "":
                i += 1
            while i < len(text) and text[i].strip() == "":
                i += 1
            continue
        lines = []
        while i < len(text) and text[i].strip() != "":
            lines.append(text[i].strip())
            i += 1
        # consume blank
        while i < len(text) and text[i].strip() == "":
            i += 1
        cue = " ".join(lines).strip()
        if cue:
            segs.append(YTSegment(start=start, end=end, text=cue))
    return segs


def _fetch_youtube_auto_captions_impl(youtube_id: str) -> Optional[tuple[YTCaptionTrack, List[YTSegment]]]:
    """Fetch auto captions (json3) for a given YouTube video id and parse to segments.

    Returns (track, segments) or None if unavailable.
    """
    url = f"https://www.youtube.com/watch?v={youtube_id}"
    logger.info("Probing yt-dlp metadata for captions", extra={"youtube_id": youtube_id, "url": url})
    data = _yt_dlp_json(url)
    track = _pick_auto_caption(data)
    if not track:
        logger.info("No auto captions found", extra={"youtube_id": youtube_id})
        return None
    logger.info(
        "Downloading captions from YouTube",
        extra={
            "operation": "captions",
            "youtube_id": youtube_id,
            "language": track.language,
            "ext": track.ext,
        },
    )
    # Download via stdlib (no extra deps)
    start_time = time.time()
    try:
        req = Request(track.url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=20) as resp:
            payload = resp.read()
        duration = time.time() - start_time

        logger.info(
            "Caption download succeeded",
            extra={
                "operation": "captions",
                "youtube_id": youtube_id,
                "language": track.language,
                "ext": track.ext,
                "duration_seconds": round(duration, 2),
                "size_bytes": len(payload),
            },
        )

        # Update metrics (use "default" as client since this is direct HTTP download, not yt-dlp)
        ytdlp_operation_duration_seconds.labels(operation="captions", client="direct").observe(duration)
        ytdlp_operation_attempts_total.labels(operation="captions", client="direct", result="success").inc()

    except Exception as e:
        duration = time.time() - start_time

        logger.warning(
            "Caption download failed",
            extra={
                "operation": "captions",
                "youtube_id": youtube_id,
                "ext": track.ext,
                "duration_seconds": round(duration, 2),
                "error": str(e)[:200],
            },
        )

        # Update metrics
        ytdlp_operation_duration_seconds.labels(operation="captions", client="direct").observe(duration)
        ytdlp_operation_attempts_total.labels(operation="captions", client="direct", result="failure").inc()

        status = getattr(e, "code", None)
        reason = getattr(e, "reason", "")
        error_text = f"{status or ''} {reason or ''} {e}".strip()
        if isinstance(e, HTTPError):
            try:
                body = e.read(2048).decode("utf-8", errors="ignore")
            except Exception:
                body = ""
            error_text = f"{error_text} {body}".strip()
        elif isinstance(e, URLError):
            error_text = f"{error_text} {getattr(e, 'reason', '')}".strip()

        if classify_youtube_error(error_text).kind == YouTubeErrorKind.THROTTLE:
            fallback_payload = _download_caption_with_ytdlp(url, youtube_id, track)
            if fallback_payload is None:
                raise YouTubeCaptionRateLimitError(f"Caption download rate-limited: {e}") from e
            payload = fallback_payload
            ytdlp_operation_attempts_total.labels(operation="captions", client="yt-dlp", result="success").inc()
        else:
            raise YouTubeCaptionFetchError(f"Caption download failed: {e}") from e

    segments: List[YTSegment] = []
    if track.ext == "json3":
        try:
            j = json.loads(payload)
        except Exception as e:
            logging.warning("Invalid json3 payload: %s", e)
            raise YouTubeCaptionFetchError(f"Invalid json3 caption payload: {e}") from e
        # json3 structure has 'events' with 'tStartMs' and 'dDurationMs'; text in 'segs'
        for ev in j.get("events", []) or []:
            start_ms = ev.get("tStartMs")
            dur_ms = ev.get("dDurationMs") or 0
            segs = ev.get("segs") or []
            if start_ms is None or not segs:
                continue
            text_parts = []
            for s in segs:
                t = s.get("utf8")
                if not t:
                    continue
                text_parts.append(t)
            text_joined = ("".join(text_parts)).strip()
            if not text_joined:
                continue
            start = float(start_ms) / 1000.0
            end = start + (float(dur_ms) / 1000.0 if dur_ms else 0.0)
            segments.append(YTSegment(start=start, end=end, text=text_joined))
    elif track.ext == "vtt":
        try:
            segments = _parse_vtt_to_segments(payload)
        except Exception as e:
            logging.warning("Failed to parse VTT: %s", e)
            raise YouTubeCaptionFetchError(f"Failed to parse VTT captions: {e}") from e
    else:
        logging.info("Unsupported caption ext: %s", track.ext)
        raise YouTubeCaptionFetchError(f"Unsupported caption ext: {track.ext}")
    return track, segments


def fetch_youtube_auto_captions(youtube_id: str) -> Optional[tuple[YTCaptionTrack, List[YTSegment]]]:
    return _fetch_youtube_auto_captions_impl(youtube_id)
