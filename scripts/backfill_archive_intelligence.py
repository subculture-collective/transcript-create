#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repo root on path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.intelligence_repository import (
    autopublish_search_topics,
    refresh_period_summaries,
    refresh_search_trends,
    refresh_topic_mentions,
    refresh_topic_period_stats,
    seed_archive_topics,
)
from app.db import session_scope


def main(*, seed_topics: bool = False, auto_topics: bool = False, rebuild_mentions: bool = False, refresh_stats: bool = False, refresh_search: bool = False, refresh_summaries: bool = False, all_steps: bool = False, quick: bool = False) -> None:
    selected = any([seed_topics, auto_topics, rebuild_mentions, refresh_stats, refresh_search, refresh_summaries])
    if all_steps or not selected:
        seed_topics = auto_topics = rebuild_mentions = refresh_stats = refresh_search = refresh_summaries = True

    stats: dict[str, int] = {}
    with session_scope() as db:
        if seed_topics:
            for key, value in seed_archive_topics(db).items():
                stats[f"seed_{key}"] = value
        if auto_topics:
            for key, value in autopublish_search_topics(db, limit=20).items():
                stats[f"auto_{key}"] = value
        if rebuild_mentions:
            for key, value in refresh_topic_mentions(db, segment_limit=1000 if quick else None).items():
                stats[f"mentions_{key}"] = value
        if refresh_stats:
            for granularity in ("month", "week"):
                for key, value in refresh_topic_period_stats(db, granularity=granularity).items():
                    stats[f"topic_stats_{granularity}_{key}"] = value
        if refresh_search:
            for key, value in refresh_search_trends(db, granularity="week").items():
                stats[f"search_trends_{key}"] = value
        if refresh_summaries:
            for granularity in ("month", "week"):
                for key, value in refresh_period_summaries(db, granularity=granularity, limit=72 if quick else 120).items():
                    stats[f"period_summaries_{granularity}_{key}"] = value
    print(
        "archive intelligence backfill complete: "
        + " ".join(f"{key}={value}" for key, value in sorted(stats.items()))
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill durable archive intelligence tables.")
    parser.add_argument("--seed-topics", action="store_true", help="Seed curated archive topics")
    parser.add_argument("--auto-topics", action="store_true", help="Publish automatic topics from search suggestions")
    parser.add_argument("--rebuild-mentions", action="store_true", help="Rebuild topic mentions from native transcript segments")
    parser.add_argument("--refresh-stats", action="store_true", help="Refresh per-topic period stats")
    parser.add_argument("--refresh-search-trends", action="store_true", help="Refresh search trend summaries")
    parser.add_argument("--refresh-summaries", action="store_true", help="Refresh period summaries")
    parser.add_argument("--all", action="store_true", dest="all_steps", help="Run every archive intelligence refresh step")
    parser.add_argument("--quick", action="store_true", help="Use bounded segment scans for faster smoke backfills")
    args = parser.parse_args()
    main(
        seed_topics=args.seed_topics,
        auto_topics=args.auto_topics,
        rebuild_mentions=args.rebuild_mentions,
        refresh_stats=args.refresh_stats,
        refresh_search=args.refresh_search_trends,
        refresh_summaries=args.refresh_summaries,
        all_steps=args.all_steps,
        quick=args.quick,
    )
