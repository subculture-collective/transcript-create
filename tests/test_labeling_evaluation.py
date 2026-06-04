from __future__ import annotations

from app.archive.labeling.evaluation import calculate_label_quality_metrics, format_label_quality_report


def test_calculate_label_quality_metrics_counts_statuses_evidence_and_rates():
    labels = [
        {"id": "label-1", "slug": "okbuddy", "label": "Okbuddy", "status": "published", "aliases": ["okbuddy"]},
        {"id": "label-2", "slug": "guest-one", "label": "Guest One", "status": "candidate", "aliases": []},
        {"id": "label-3", "slug": "empty", "label": "Empty", "status": "review", "aliases": []},
    ]
    assignments = [
        {"label_id": "label-1", "video_id": "video-1", "unit_type": "window", "status": "auto_published", "publish_tier": "gold", "evidence_count": 2},
        {"label_id": "label-1", "video_id": "video-2", "unit_type": "chapter", "status": "admin_approved", "publish_tier": "silver", "evidence_count": 1},
        {"label_id": "label-2", "video_id": "video-2", "unit_type": "window", "status": "rejected", "publish_tier": "shadow", "evidence_count": 0},
        {"label_id": "label-2", "video_id": "video-3", "unit_type": "window", "status": "shadow", "publish_tier": "shadow", "evidence_count": 0},
    ]

    metrics = calculate_label_quality_metrics(labels, assignments)

    assert metrics.labels_total == 3
    assert metrics.auto_published == 1
    assert metrics.review_candidates == 2
    assert metrics.shadow == 2
    assert metrics.assignments_total == 4
    assert metrics.assignments_without_evidence == 2
    assert metrics.admin_approval_rate == 0.5
    assert metrics.rejected_rate == 0.5
    assert metrics.labels_without_evidence == 2
    assert metrics.duplicate_collision_candidates == 3
    assert metrics.assignment_vods == 3
    assert metrics.window_assignments == 3
    assert metrics.chapter_assignments == 1


def test_format_label_quality_report_prints_contract_lines():
    metrics = calculate_label_quality_metrics([], [])

    output = format_label_quality_report(metrics)

    assert output.startswith("label quality report:\n")
    assert "labels_total=0" in output
    assert "auto_published=0" in output
    assert "review_candidates=0" in output
    assert "shadow=0" in output
    assert "assignments_total=0" in output
    assert "assignments_without_evidence=0" in output
    assert "admin_approval_rate=0.0" in output
    assert "rejected_rate=0.0" in output
