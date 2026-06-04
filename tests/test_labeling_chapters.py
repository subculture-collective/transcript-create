from __future__ import annotations

from app.archive.labeling.chapters import derive_chapters_from_window_labels


def test_chapters_group_adjacent_windows_with_same_label():
    rows = [
        {"label_id": "topic-gaza", "label": "Gaza", "start_ms": 0, "end_ms": 120000},
        {"label_id": "topic-gaza", "label": "Gaza", "start_ms": 120000, "end_ms": 240000},
        {"label_id": "topic-gaming", "label": "Gaming", "start_ms": 600000, "end_ms": 720000},
    ]

    chapters = derive_chapters_from_window_labels(rows, max_gap_ms=60_000)

    assert chapters[0]["title"] == "Gaza"
    assert chapters[0]["start_ms"] == 0
    assert chapters[0]["end_ms"] == 240000
    assert chapters[0]["evidence_count"] == 2
    assert chapters[1]["title"] == "Gaming"


def test_chapters_do_not_group_same_label_across_large_gap():
    rows = [
        {"label_id": "topic-gaza", "label": "Gaza", "start_ms": 0, "end_ms": 120000},
        {"label_id": "topic-gaza", "label": "Gaza", "start_ms": 300000, "end_ms": 420000},
    ]

    chapters = derive_chapters_from_window_labels(rows, max_gap_ms=60_000)

    assert len(chapters) == 2
    assert chapters[0]["end_ms"] == 120000
    assert chapters[1]["start_ms"] == 300000


def test_chapters_drop_zero_length_rows():
    rows = [{"label_id": "topic-gaza", "label": "Gaza", "start_ms": 120000, "end_ms": 120000}]

    assert derive_chapters_from_window_labels(rows) == []
