from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root on path when executed as /app/scripts/report_label_quality.py.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.labeling.evaluation import build_label_quality_report, format_label_quality_report
from app.db import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        print(format_label_quality_report(build_label_quality_report(db)))
    finally:
        db.close()


if __name__ == "__main__":
    main()
