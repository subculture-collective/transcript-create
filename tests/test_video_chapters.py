import uuid
from unittest.mock import Mock

from app.archive.video_chapters import build_grounded_chapters
from app.routes.videos import get_video_chapters


def test_build_grounded_chapters_groups_blocks_and_cites_source_text():
    blocks = [
        {
            "block_index": 0,
            "start_ms": 0,
            "end_ms": 30_000,
            "text": ">> Welcome to the stream. Today we cover the news.",
        },
        {"block_index": 1, "start_ms": 60_000, "end_ms": 90_000, "text": "More opening discussion."},
        {"block_index": 2, "start_ms": 660_000, "end_ms": 690_000, "text": "The rally begins in New Jersey."},
    ]

    chapters = build_grounded_chapters(blocks, duration_ms=900_000)

    assert len(chapters) == 2
    assert chapters[0]["title"] == "Opening: Welcome to the stream."
    assert chapters[0]["end_ms"] == 660_000
    assert chapters[1]["title"] == "The rally begins in New Jersey."
    assert chapters[1]["end_ms"] == 900_000
    assert chapters[1]["evidence"] == [
        {"block_index": 2, "start_ms": 660_000, "end_ms": 690_000, "text": "The rally begins in New Jersey."}
    ]


def test_build_grounded_chapters_returns_empty_for_empty_blocks():
    assert build_grounded_chapters([]) == []


def test_video_chapter_route_uses_transcript_fallback(monkeypatch):
    video_id = uuid.uuid4()
    blocks = [{"block_index": 0, "start_ms": 0, "end_ms": 20_000, "text": "Opening discussion."}]
    monkeypatch.setattr(
        "app.routes.videos.crud.get_video", lambda db, requested_id: {"id": requested_id, "duration_seconds": 60}
    )
    monkeypatch.setattr("app.routes.videos.crud.list_transcript_blocks", lambda db, requested_id: blocks)

    result = Mock()
    result.mappings.return_value.all.return_value = []
    db = Mock()
    db.execute.return_value = result

    response = get_video_chapters(video_id, db=db)

    assert response.source == "transcript"
    assert response.chapters[0].title == "Opening: Opening discussion."
    assert response.chapters[0].evidence[0].text == "Opening discussion."
