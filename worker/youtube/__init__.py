"""YouTube worker adapter package."""

from .errors import YouTubeError, YouTubeErrorKind, classify_youtube_error
from .service import (
    YouTubeCaptionFetchError,
    YouTubeCaptionRateLimitError,
    YouTubeCaptionResult,
    YouTubeService,
    download_audio,
    fetch_auto_captions,
    fetch_metadata,
    get_youtube_service,
)
from .yt_dlp_executor import YtDlpError, YtDlpExecutionResult, YtDlpExecutor
