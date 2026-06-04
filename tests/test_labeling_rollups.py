from __future__ import annotations

from app.archive.labeling.rollups import derive_vod_label_assignments, is_safe_auto_series, person_assignment_kind


def test_vod_rollup_requires_multiple_windows_or_duration_share():
    window_assignments = [
        {
            "label_id": "topic-gaza",
            "video_id": "v1",
            "start_ms": 0,
            "end_ms": 120000,
            "confidence_score": 0.92,
            "status": "auto_published",
            "publish_tier": "gold",
        },
        {
            "label_id": "topic-gaza",
            "video_id": "v1",
            "start_ms": 120000,
            "end_ms": 240000,
            "confidence_score": 0.90,
            "status": "auto_published",
            "publish_tier": "gold",
        },
    ]

    rollups = derive_vod_label_assignments(window_assignments, video_duration_seconds=3600)

    assert rollups[0]["unit_type"] == "vod"
    assert rollups[0]["label_id"] == "topic-gaza"
    assert rollups[0]["evidence_count"] == 2
    assert rollups[0]["publish_tier"] == "gold"


def test_single_fleeting_window_does_not_become_vod_label():
    window_assignments = [
        {
            "label_id": "topic-gaza",
            "video_id": "v1",
            "start_ms": 0,
            "end_ms": 10000,
            "confidence_score": 0.92,
            "status": "auto_published",
            "publish_tier": "gold",
        },
    ]

    assert derive_vod_label_assignments(window_assignments, video_duration_seconds=7200) == []


def test_long_single_window_can_become_vod_label_by_duration_share():
    window_assignments = [
        {
            "label_id": "topic-gaza",
            "video_id": "v1",
            "start_ms": 0,
            "end_ms": 240000,
            "confidence_score": 0.92,
            "status": "admin_approved",
            "publish_tier": "silver",
        },
    ]

    rollups = derive_vod_label_assignments(window_assignments, video_duration_seconds=3600)

    assert rollups[0]["label_id"] == "topic-gaza"
    assert rollups[0]["publish_tier"] == "silver"


def test_ignores_unpublished_window_assignments():
    window_assignments = [
        {
            "label_id": "topic-gaza",
            "video_id": "v1",
            "start_ms": 0,
            "end_ms": 240000,
            "confidence_score": 0.92,
            "status": "candidate",
            "publish_tier": "gold",
        },
    ]

    assert derive_vod_label_assignments(window_assignments, video_duration_seconds=3600) == []


def test_series_labels_require_allowlist_and_sufficient_cross_video_evidence():
    assert is_safe_auto_series("gaming", distinct_videos=2, evidence_count=3)
    assert not is_safe_auto_series("gaming", distinct_videos=1, evidence_count=3)
    assert not is_safe_auto_series("gaming", distinct_videos=2, evidence_count=2)
    assert not is_safe_auto_series("random-drama", distinct_videos=4, evidence_count=10)


def test_person_assignment_kind_distinguishes_present_from_mentioned():
    assert person_assignment_kind([{"snippet": "A guest joins us on stream to talk labor."}]) == "person_present"
    assert person_assignment_kind([{"snippet": "Chat mentioned the senator during the segment."}]) == "person_mentioned"
