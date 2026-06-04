from __future__ import annotations

from typing import Any


def derive_chapters_from_window_labels(window_labels: list[dict[str, Any]], max_gap_ms: int = 60_000) -> list[dict[str, Any]]:
    ordered = sorted(window_labels, key=lambda row: (int(row.get("start_ms") or 0), str(row.get("label_id") or "")))
    chapters: list[dict[str, Any]] = []
    for row in ordered:
        label_id = str(row.get("label_id") or "")
        label = str(row.get("label") or label_id)
        start_ms = int(row.get("start_ms") or 0)
        end_ms = int(row.get("end_ms") or start_ms)
        if chapters and chapters[-1]["label_id"] == label_id and start_ms - chapters[-1]["end_ms"] <= max_gap_ms:
            chapters[-1]["end_ms"] = max(chapters[-1]["end_ms"], end_ms)
            chapters[-1]["evidence_count"] += 1
        else:
            chapters.append(
                {"label_id": label_id, "title": label, "start_ms": start_ms, "end_ms": end_ms, "evidence_count": 1}
            )
    return [chapter for chapter in chapters if chapter["end_ms"] > chapter["start_ms"]]
