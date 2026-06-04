from __future__ import annotations

from collections import defaultdict
from typing import Any


SAFE_SERIES_LABELS = {"chadvice", "okbuddy", "gaming", "guests"}


def derive_vod_label_assignments(
    window_assignments: list[dict[str, Any]],
    video_duration_seconds: int,
    min_windows: int = 2,
    min_duration_share: float = 0.04,
) -> list[dict[str, Any]]:
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assignment in window_assignments:
        if assignment.get("status") not in {"auto_published", "admin_approved"}:
            continue
        by_label[str(assignment["label_id"])].append(assignment)

    rollups: list[dict[str, Any]] = []
    duration_ms = max(1, int(video_duration_seconds or 0) * 1000)
    for label_id, rows in by_label.items():
        covered_ms = sum(max(0, int(row.get("end_ms") or 0) - int(row.get("start_ms") or 0)) for row in rows)
        duration_share = covered_ms / duration_ms
        if len(rows) < min_windows and duration_share < min_duration_share:
            continue
        rollups.append(
            {
                "label_id": label_id,
                "video_id": str(rows[0]["video_id"]),
                "unit_type": "vod",
                "status": "auto_published",
                "publish_tier": "gold" if all(row.get("publish_tier") == "gold" for row in rows) else "silver",
                "confidence_score": min(
                    0.99,
                    sum(float(row.get("confidence_score") or 0) for row in rows) / len(rows) + min(0.10, duration_share),
                ),
                "evidence_count": len(rows),
                "evidence": rows[:5],
            }
        )
    return rollups


def is_safe_auto_series(slug: str, distinct_videos: int, evidence_count: int) -> bool:
    return slug in SAFE_SERIES_LABELS and distinct_videos >= 2 and evidence_count >= 3


def person_assignment_kind(evidence: list[dict[str, Any]]) -> str:
    text = " ".join(str(item.get("snippet") or "").lower() for item in evidence)
    present_markers = ("joins us", "on stream", "guest", "with ", "talking to")
    return "person_present" if any(marker in text for marker in present_markers) else "person_mentioned"
