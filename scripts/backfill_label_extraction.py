#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

# Ensure repo root on path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.labeling.pipeline import extract_labels_for_video
from app.db import session_scope


def main(*, limit: int = 10, extraction_tier: str = "cheap") -> None:
    totals = {"videos": 0, "windows": 0, "candidates": 0, "assignments": 0}

    with session_scope() as db:
        rows = db.execute(
            text(
                """
                SELECT v.id
                FROM videos AS v
                WHERE (EXISTS (SELECT 1 FROM segments AS s WHERE s.video_id = v.id)
                   OR EXISTS (SELECT 1 FROM youtube_transcripts AS yt WHERE yt.video_id = v.id))
                  AND NOT EXISTS (
                    SELECT 1
                    FROM archive_extraction_runs AS r
                    WHERE r.video_id = v.id
                      AND r.scope = 'video'
                      AND r.extraction_tier = :extraction_tier
                      AND r.status = 'completed'
                  )
                ORDER BY COALESCE(v.duration_seconds, 999999) ASC, COALESCE(v.uploaded_at, v.created_at) DESC NULLS LAST
                LIMIT :limit
                """
            ),
            {"limit": limit, "extraction_tier": extraction_tier},
        ).all()

        for row in rows:
            video_id = str(row[0])
            result = extract_labels_for_video(db, video_id, extraction_tier=extraction_tier)
            totals["videos"] += 1
            totals["windows"] += int(result.get("windows") or 0)
            totals["candidates"] += int(result.get("candidates") or 0)
            totals["assignments"] += int(result.get("assignments") or 0)
            print("label extraction backfilled video: " + " ".join(f"{key}={value}" for key, value in sorted(result.items())), flush=True)

    print("label extraction backfill complete: " + " ".join(f"{key}={value}" for key, value in sorted(totals.items())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill label extraction for recent videos.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum videos to process")
    parser.add_argument(
        "--extraction-tier",
        choices=("cheap", "balanced", "premium"),
        default="cheap",
        help="Extraction tier to use",
    )
    args = parser.parse_args()
    main(limit=args.limit, extraction_tier=args.extraction_tier)
