#!/usr/bin/env python3
# ruff: noqa: E402, I001
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.title_entity_curation import import_title_entity_curation_rows, read_curation_csv
from app.db import SessionLocal, session_scope


EPILOG = """
Examples:
  python scripts/suggest_people_from_titles.py --limit 2000 --format csv > title-entity-candidates.csv
  python scripts/import_title_entity_curation.py title-entity-candidates.curated.csv --dry-run
  python scripts/import_title_entity_curation.py title-entity-candidates.curated.csv
"""


def main(path: str, *, dry_run: bool = False) -> None:
    rows = read_curation_csv(path)
    if dry_run:
        db = SessionLocal()
        try:
            result = import_title_entity_curation_rows(db, rows)
            db.rollback()
        finally:
            db.close()
    else:
        with session_scope() as db:
            result = import_title_entity_curation_rows(db, rows)
    mode = "dry_run" if dry_run else "imported"
    print(
        f"{mode}=true rows={result['rows']} people={result['people']} "
        f"tags={result['tags']} aliases={result['aliases']}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import curated title-derived entities into HasanAra people/tags metadata.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("path", help="Curated CSV path")
    parser.add_argument("--dry-run", action="store_true", help="Validate and count rows without committing")
    args = parser.parse_args()
    main(args.path, dry_run=args.dry_run)
