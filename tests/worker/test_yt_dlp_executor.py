import subprocess

import pytest

from worker.youtube.errors import YouTubeErrorKind
from worker.youtube.yt_dlp_executor import YtDlpError, YtDlpExecutionResult, YtDlpExecutor


def test_executor_run_wraps_subprocess_result(monkeypatch):
    class P:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *a, **k: P())
    result = YtDlpExecutor().run(["-J"], timeout=1)
    assert result == YtDlpExecutionResult(0, "ok", "")


def test_executor_run_json_parses_object(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout, check):
        assert cmd == ["yt-dlp", "-J", "https://example.test"]
        return subprocess.CompletedProcess(cmd, 0, stdout='{"id":"abc"}', stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    assert YtDlpExecutor(timeout=3).run_json(["-J", "https://example.test"]) == {"id": "abc"}


def test_executor_classifies_rate_limit(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout, check):
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout="",
            stderr="The current session has been rate-limited by YouTube for up to an hour.",
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(YtDlpError) as exc:
        YtDlpExecutor().run_json(["-J", "https://example.test"])
    assert exc.value.kind == YouTubeErrorKind.THROTTLE


def test_executor_rejects_args_that_include_binary():
    with pytest.raises(ValueError):
        YtDlpExecutor().run(["yt-dlp", "-J"])
