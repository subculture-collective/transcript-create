#!/usr/bin/env python3
"""Backfill persisted transcript blocks for existing videos.

Finds videos that have raw segments but no transcript_blocks rows, builds
blocks deterministically from segments, and persists them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

# Ensure repo root is on sys.path even if run from outside the repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import crud
from app.logging_config import configure_logging, get_logger
from app.settings import settings
from app.transcripts.blocks import build_transcript_blocks
from app.transcripts.types import TranscriptSegment

configure_logging(
    service="script.backfill-transcript-blocks",
    level=settings.LOG_LEVEL,
    json_format=(settings.LOG_FORMAT == "json"),
)
logger = get_logger(__name__)


def _load_batch(conn, limit: int):
    return conn.execute(
        text(
            """
            SELECT v.id, v.youtube_id, v.title, COUNT(s.id) AS segment_count
            FROM videos v
            JOIN segments s ON s.video_id = v.id
            LEFT JOIN transcript_blocks tb ON tb.video_id = v.id
            WHERE tb.video_id IS NULL
            GROUP BY v.id, v.youtube_id, v.title
            ORDER BY v.created_at ASC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()


def _load_segments(conn, video_id):
    rows = conn.execute(
        text(
            """
            SELECT id, start_ms, end_ms, text, speaker_label
            FROM segments
            WHERE video_id = :video_id
            ORDER BY start_ms, id
            """
        ),
        {"video_id": str(video_id)},
    ).mappings().all()

    return [
        TranscriptSegment(
            start_ms=int(row["start_ms"]),
            end_ms=int(row["end_ms"]),
            text=row["text"],
            speaker_label=row["speaker_label"],
        )
        for row in rows
    ]


def main(batch_size: int = 100, dry_run: bool = False, until_empty: bool = True) -> int:
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    processed = 0

    logger.info("Starting transcript block backfill", extra={"batch_size": batch_size, "dry_run": dry_run})

    while True:
        with engine.begin() as conn:
            batch = _load_batch(conn, batch_size)

            if not batch:
                logger.info("No videos eligible for transcript block backfill")
                break

            logger.info("Loaded batch", extra={"batch_size": len(batch)})

            for row in batch:
                video_id = row["id"]
                segments = _load_segments(conn, video_id)
                if not segments:
                    logger.info("Skipping video with no segments", extra={"video_id": str(video_id)})
                    continue

                blocks = build_transcript_blocks(segments)
                logger.info(
                    "Built transcript blocks",
                    extra={
                        "video_id": str(video_id),
                        "youtube_id": row["youtube_id"],
                        "title": row["title"],
                        "segment_count": len(segments),
                        "block_count": len(blocks),
                        "dry_run": dry_run,
                    },
                )

                if not dry_run:
                    crud.replace_transcript_blocks(conn, video_id, blocks)
                    processed += 1
                else:
                    processed += 1

        if not until_empty or len(batch) < batch_size:
            break

    logger.info("Transcript block backfill complete", extra={"videos_processed": processed, "dry_run": dry_run})
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill persisted transcript blocks for existing videos")
    parser.add_argument("--batch-size", type=int, default=100, help="Videos to process per batch (default: 100)")
    parser.add_argument("--dry-run", action="store_true", help="Build blocks without writing to the database")
    parser.add_argument("--once", action="store_true", help="Run a single batch instead of looping until empty")
    args = parser.parse_args()

    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be a positive integer")

    raise SystemExit(main(batch_size=args.batch_size, dry_run=args.dry_run, until_empty=not args.once))
