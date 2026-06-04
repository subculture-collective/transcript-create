#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.video_metadata_repository import materialize_label_assignments_to_metadata, seed_metadata_label_aliases
from app.db import session_scope


def main(limit: int, seed_label_aliases: bool) -> None:
    with session_scope() as db:
        seed_result = seed_metadata_label_aliases(db) if seed_label_aliases else {"labels": 0, "aliases": 0}
        result = materialize_label_assignments_to_metadata(db, limit=limit)
    print(
        "label metadata materialization complete: "
        + " ".join(f"seed_{key}={value}" for key, value in sorted(seed_result.items()))
        + " "
        + " ".join(f"{key}={value}" for key, value in sorted(result.items()))
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Materialize accepted label assignments into Explore people/tags metadata.")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--no-seed-label-aliases", action="store_true", help="Skip seeding published metadata into label aliases first")
    args = parser.parse_args()
    main(args.limit, seed_label_aliases=not args.no_seed_label_aliases)
