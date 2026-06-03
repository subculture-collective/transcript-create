#!/usr/bin/env python3
"""Refresh cached archive summary statistics.

This intentionally does the expensive transcript word-count pass out of band so
the public homepage can load from a tiny singleton table.
"""

from app.db import session_scope
from app.archive.refresher import refresh_archive_summary_stats


def main() -> None:
    with session_scope() as db:
        stats = refresh_archive_summary_stats(db)
        print(
            "archive_summary_stats refreshed: "
            f"videos={stats.video_count} "
            f"words={stats.transcript_word_count}"
        )


if __name__ == "__main__":
    main()
