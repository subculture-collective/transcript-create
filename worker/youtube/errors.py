"""Normalized YouTube error types and classification helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class YouTubeErrorKind(str, Enum):
    THROTTLE = "throttle"
    AUTH = "auth"
    TOKEN = "token"
    NOT_FOUND = "not_found"
    NETWORK = "network"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class YouTubeError:
    kind: YouTubeErrorKind
    message: str
    returncode: int | None = None
    stderr: str = ""


def classify_youtube_error(stderr: str = "", *, returncode: int | None = None) -> YouTubeError:
    text = (stderr or "").lower()
    if (
        "429" in text
        or "too many requests" in text
        or "rate-limited" in text
        or "rate limited" in text
        or "current session has been rate" in text
        or ("up to an hour" in text and "youtube" in text)
        or "throttl" in text
    ):
        kind = YouTubeErrorKind.THROTTLE
    elif "po_token" in text or "po token" in text or "gvs po" in text:
        kind = YouTubeErrorKind.TOKEN
    elif (
        "403" in text
        or "forbidden" in text
        or "sign in" in text
        or "not a bot" in text
        or (
            "cookies" in text
            and ("expired" in text or "invalid" in text or "rotated" in text or "authentication" in text)
        )
    ):
        kind = YouTubeErrorKind.AUTH
    elif "404" in text or "not found" in text or "unavailable" in text or "private" in text:
        kind = YouTubeErrorKind.NOT_FOUND
    elif "timeout" in text or "timed out" in text:
        kind = YouTubeErrorKind.TIMEOUT
    elif "network" in text or "connection" in text:
        kind = YouTubeErrorKind.NETWORK
    else:
        kind = YouTubeErrorKind.UNKNOWN
    return YouTubeError(kind=kind, message=stderr or kind.value, returncode=returncode, stderr=stderr or "")
