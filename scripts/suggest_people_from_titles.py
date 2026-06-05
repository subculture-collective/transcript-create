#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.labeling.extractors import suggest_person_names_from_titles
from app.db import session_scope


def main(limit: int, output_format: str) -> None:
    with session_scope() as db:
        rows = db.execute(
            text(
                """
                SELECT id, title, uploaded_at, channel_name
                FROM videos
                WHERE title IS NOT NULL
                  AND title <> ''
                ORDER BY uploaded_at DESC NULLS LAST, created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
    suggestions = suggest_person_names_from_titles([dict(row) for row in rows])
    if output_format == "json":
        print(json.dumps(suggestions, indent=2, default=str))
        return
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=[
            "candidate",
            "guess_type",
            "count",
            "example_title",
            "example_video_id",
            "decision",
            "entity_type",
            "person_role",
            "canonical",
            "aliases",
            "notes",
        ],
    )
    writer.writeheader()
    for item in suggestions:
        first = item["titles"][0] if item.get("titles") else {}
        writer.writerow(
            {
                "candidate": item["name"],
                "guess_type": "person",
                "count": item["count"],
                "example_title": first.get("title", ""),
                "example_video_id": first.get("video_id", ""),
                "decision": "",
                "entity_type": "",
                "person_role": "",
                "canonical": "",
                "aliases": "",
                "notes": "",
            }
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Suggest possible people to add to the HasanAra people roster from VOD titles."
    )
    parser.add_argument("--limit", type=int, default=2000, help="Maximum videos to scan")
    parser.add_argument("--format", choices=("csv", "json"), default="csv")
    args = parser.parse_args()
    main(args.limit, args.format)
