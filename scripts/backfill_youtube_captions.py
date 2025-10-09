#!/usr/bin/env python3
import logging
import sys
import argparse
from pathlib import Path
from sqlalchemy import create_engine, text

# Ensure repo root is on sys.path even if run from outside the repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.settings import settings
from worker.pipeline import capture_youtube_captions_for_unprocessed

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s [backfill] %(message)s')

def main(batch: int = 1):
    """Backfill YouTube captions.

    Default batch=1 to ensure each video commits independently. This avoids losing a large
    batch on Ctrl-C. Increase batch for speed if desired.
    """
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    total = 0
    with engine.begin() as conn:
        # Count videos without yt captions
        c = conn.execute(text(
            """
            SELECT count(*) FROM videos v
            WHERE NOT EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id)
            """
        )).scalar() or 0
        logging.info("Videos without YouTube captions: %d", c)
    while True:
        # Commit after each chunk. For batch=1 this means per-video commit.
        with engine.begin() as conn:
            processed = capture_youtube_captions_for_unprocessed(conn, limit=batch)
        total += processed
        if processed == 0:
            break
        logging.info("Processed batch=%d; cumulative=%d", processed, total)
    logging.info("Backfill complete. Total videos updated: %d", total)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Backfill YouTube captions for existing videos")
    parser.add_argument("--batch", type=int, default=1, help="Number of videos to process per transaction (default: 1)")
    args = parser.parse_args()
    main(batch=max(1, args.batch))
