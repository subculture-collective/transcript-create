"""Subprocess boundary for yt-dlp operations."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any

from worker.youtube.errors import YouTubeErrorKind, classify_youtube_error

__all__ = ["YtDlpExecutionResult", "YtDlpError", "YtDlpExecutor"]


@dataclass(frozen=True)
class YtDlpExecutionResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass
class YtDlpError(RuntimeError):
    kind: YouTubeErrorKind
    stderr: str
    command: list[str]
    returncode: int | None = None

    def __str__(self) -> str:
        return f"yt-dlp failed with {self.kind.value}: {self.stderr[:300]}"


class YtDlpExecutor:
    def __init__(self, *, binary: str = "yt-dlp", timeout: int | float | None = None):
        self.binary = binary
        self.timeout = timeout

    def _command(self, args: list[str]) -> list[str]:
        if args and Path(args[0]).name == Path(self.binary).name:
            raise ValueError("YtDlpExecutor args must not include the yt-dlp binary")
        return [self.binary, *args]

    def run(self, args: list[str], *, timeout: int | float | None = None) -> YtDlpExecutionResult:
        cmd = self._command(args)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout if timeout is None else timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stderr = str(exc)
            raise YtDlpError(YouTubeErrorKind.TIMEOUT, stderr, cmd, None) from exc
        except OSError as exc:
            stderr = str(exc)
            error = classify_youtube_error(stderr, returncode=None)
            raise YtDlpError(error.kind, stderr, cmd, None) from exc
        if proc.returncode != 0:
            error = classify_youtube_error(proc.stderr or proc.stdout, returncode=proc.returncode)
            raise YtDlpError(error.kind, proc.stderr or proc.stdout, cmd, proc.returncode)
        return YtDlpExecutionResult(proc.returncode, proc.stdout, proc.stderr)

    def run_json(self, args: list[str], *, timeout: int | float | None = None) -> dict[str, Any]:
        result = self.run(args, timeout=timeout)
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            stderr = result.stderr or f"Invalid yt-dlp JSON output: {exc}"
            raise YtDlpError(YouTubeErrorKind.UNKNOWN, stderr, self._command(args), result.returncode) from exc
        if not isinstance(parsed, dict):
            raise YtDlpError(
                YouTubeErrorKind.UNKNOWN,
                "yt-dlp JSON output was not an object",
                self._command(args),
                result.returncode,
            )
        return parsed
