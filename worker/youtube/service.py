from __future__ import annotations

from dataclasses import dataclass
import json
import shlex
from pathlib import Path
import subprocess
from typing import Any, Literal

from app.logging_config import get_logger
from app.settings import settings
from worker.youtube_captions import YTCaptionTrack, YTSegment, YouTubeCaptionFetchError, YouTubeCaptionRateLimitError

logger = get_logger(__name__)

CaptionSource = Literal["direct", "yt-dlp"]


@dataclass(frozen=True)
class YouTubeCaptionResult:
    track: YTCaptionTrack
    segments: list[YTSegment]
    source: CaptionSource


def _fetch_ytdlp_metadata(url: str, *, flat_playlist: bool = False) -> dict[str, Any]:
    """Fetch yt-dlp JSON metadata using configured client fallback commands."""
    from worker.ytdlp_client_utils import get_client_extractor_args

    clients = [c.strip() for c in settings.YTDLP_CLIENT_ORDER.split(",") if c.strip()]
    disabled = {c.strip() for c in settings.YTDLP_CLIENTS_DISABLED.split(",") if c.strip()}
    commands: list[tuple[str, list[str]]] = []

    for client in clients:
        if client in disabled:
            continue
        extractor_args = get_client_extractor_args(client)
        if extractor_args is None:
            logger.warning("Unknown YTDLP client in metadata strategy; skipping", extra={"client": client})
            continue
        cmd = ["yt-dlp"]
        if flat_playlist:
            cmd.append("--flat-playlist")
        cmd.append("-J")
        cmd.extend(extractor_args)
        if settings.YTDLP_COOKIES_PATH and Path(settings.YTDLP_COOKIES_PATH).exists():
            cmd.extend(["--cookies", settings.YTDLP_COOKIES_PATH])
        if settings.YTDLP_EXTRA_ARGS:
            cmd.extend(shlex.split(settings.YTDLP_EXTRA_ARGS))
        cmd.append(url)
        commands.append((client, cmd))

    if not commands:
        cmd = ["yt-dlp"]
        if flat_playlist:
            cmd.append("--flat-playlist")
        cmd.extend(["-J", url])
        commands.append(("default", cmd))

    last_error: subprocess.CalledProcessError | None = None
    for client, cmd in commands:
        try:
            logger.info("Fetching yt-dlp metadata", extra={"client": client, "flat_playlist": flat_playlist})
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=settings.YTDLP_REQUEST_TIMEOUT,
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as exc:
            last_error = exc
            logger.warning(
                "yt-dlp metadata strategy failed",
                extra={"client": client, "stderr_snippet": (exc.stderr or "")[:200]},
            )

    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to fetch yt-dlp metadata")


def _fetch_legacy_auto_captions(youtube_id: str) -> tuple[YTCaptionTrack, list[YTSegment]] | None:
    from worker.youtube_captions import fetch_youtube_auto_captions

    return fetch_youtube_auto_captions(youtube_id)


def _download_audio(url: str, output_dir: Path) -> Path:
    from worker.audio import download_audio

    return download_audio(url, output_dir)


class YouTubeService:
    def fetch_metadata(self, url: str, *, flat_playlist: bool = False) -> dict[str, Any]:
        return _fetch_ytdlp_metadata(url, flat_playlist=flat_playlist)

    def fetch_auto_captions(self, youtube_id: str) -> YouTubeCaptionResult | None:
        result = _fetch_legacy_auto_captions(youtube_id)
        if result is None:
            return None

        track, segments = result
        return YouTubeCaptionResult(track=track, segments=segments, source="direct")

    def download_audio(self, url: str, output_dir: Path) -> Path:
        return _download_audio(url, output_dir)


_YOUTUBE_SERVICE = YouTubeService()


def get_youtube_service() -> YouTubeService:
    return _YOUTUBE_SERVICE


def fetch_metadata(url: str, *, flat_playlist: bool = False) -> dict[str, Any]:
    return _YOUTUBE_SERVICE.fetch_metadata(url, flat_playlist=flat_playlist)


def fetch_auto_captions(youtube_id: str) -> YouTubeCaptionResult | None:
    return _YOUTUBE_SERVICE.fetch_auto_captions(youtube_id)


def download_audio(url: str, output_dir: Path) -> Path:
    return _YOUTUBE_SERVICE.download_audio(url, output_dir)
