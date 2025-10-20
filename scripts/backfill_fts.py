#!/usr/bin/env python3
import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

# Ensure repo root on path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [fts-backfill] %(message)s")

"""
Backfill FTS tsvector columns for existing rows. Because we created triggers, inserting or updating
new rows is automatic. For existing rows, force an update to populate text_tsv.
"""


def run_pass(conn, table: str, batch: int) -> int:
    if table == "segments":
        sql = """
            WITH cte AS (
                SELECT id FROM segments WHERE text_tsv IS NULL LIMIT :lim
            )
            UPDATE segments s
            SET text = s.text
            FROM cte
            WHERE s.id = cte.id
            RETURNING s.id
        """
    else:
        sql = """
            WITH cte AS (
                SELECT id FROM youtube_segments WHERE text_tsv IS NULL LIMIT :lim
            )
            UPDATE youtube_segments ys
            SET text = ys.text
            FROM cte
            WHERE ys.id = cte.id
            RETURNING ys.id
        """
    return conn.execute(text(sql), {"lim": batch}).rowcount or 0


def main(batch: int = 10000, until_empty: bool = False, max_iterations: int | None = None):
    eng = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    iterations = 0
    while True:
        with eng.begin() as conn:
            seg_updated = run_pass(conn, "segments", batch)
            yt_updated = run_pass(conn, "youtube_segments", batch)
        iterations += 1
        logging.info("pass=%d segments updated=%d youtube_segments updated=%d", iterations, seg_updated, yt_updated)
        if not until_empty:
            break
        if (seg_updated + yt_updated) == 0:
            logging.info("No more rows to update. Exiting.")
            break
        if max_iterations is not None and iterations >= max_iterations:
            logging.info("Reached max iterations (%d). Exiting.", max_iterations)
            break
    logging.info("FTS backfill complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill FTS tsvector columns for existing rows.")
    parser.add_argument("--batch", type=int, default=10000, help="Rows to update per table per pass (default: 10000)")
    parser.add_argument("--until-empty", action="store_true", help="Keep running passes until no rows are updated")
    parser.add_argument("--max-iterations", type=int, default=None, help="Safety cap when using --until-empty")
    args = parser.parse_args()
    if args.batch <= 0:
        raise SystemExit("--batch must be a positive integer")
    main(batch=args.batch, until_empty=args.until_empty, max_iterations=args.max_iterations)
