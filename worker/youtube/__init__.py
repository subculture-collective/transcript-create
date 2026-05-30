"""YouTube worker adapter package."""

from .errors import YouTubeError, YouTubeErrorKind, classify_youtube_error
from .yt_dlp_executor import YtDlpError, YtDlpExecutionResult, YtDlpExecutor
