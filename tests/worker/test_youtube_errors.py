from worker.youtube.errors import YouTubeErrorKind, classify_youtube_error


def test_classify_youtube_error_throttle():
    err = classify_youtube_error("HTTP Error 429: Too Many Requests")
    assert err.kind == YouTubeErrorKind.THROTTLE


def test_classify_youtube_error_not_found():
    err = classify_youtube_error("Video unavailable")
    assert err.kind == YouTubeErrorKind.NOT_FOUND
