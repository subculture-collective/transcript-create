#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root on path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.intelligence_repository import refresh_archive_intelligence
from app.db import session_scope


def main() -> None:
    with session_scope() as db:
        stats = refresh_archive_intelligence(db, quick=False)
    print("archive intelligence refreshed: " + " ".join(f"{key}={value}" for key, value in sorted(stats.items())))


if __name__ == "__main__":
    main()
