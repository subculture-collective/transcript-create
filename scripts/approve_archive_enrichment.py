#!/usr/bin/env python3
"""Apply the authorized PR28 cleanup and current successful-run approval.

Default is a complete transactional rehearsal that rolls back all mutations.
No provider requests, queue resume, or source/transcript deletion occurs here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.archive.enrichment_cleanup import cleanup_legacy
from app.archive.enrichment_publication import QUALITY_CUTOFF, approve_run
from app.archive.enrichment_queue import OWNER_LOCK
from app.archive.openrouter_enrichment import PROMPT_VERSION
from app.db import engine


def run_maintenance(db: Session) -> dict:
    acquired = db.execute(
        text("SELECT pg_try_advisory_xact_lock(hashtext(:owner))"), {"owner": OWNER_LOCK}
    ).scalar_one()
    if not acquired:
        raise ValueError("Stop the enrichment worker before maintenance")
    if db.execute(
        text("SELECT 1 FROM archive_extraction_runs WHERE model_name IS NOT NULL AND status='running' LIMIT 1")
    ).scalar():
        raise ValueError("Unresolved running extraction exists")
    if db.execute(text("SELECT 1 FROM archive_enrichment_jobs WHERE status='running' LIMIT 1")).scalar():
        raise ValueError("Unresolved running job exists")
    cleanup = cleanup_legacy(db)
    runs = (
        db.execute(
            text("""SELECT r.id FROM archive_extraction_runs r
        WHERE r.status='completed' AND r.model_name='deepseek/deepseek-v4-pro' AND r.prompt_version=:prompt
        AND r.started_at>=CAST(:cutoff AS timestamptz)
        AND EXISTS(SELECT 1 FROM archive_video_chapters c WHERE c.run_id=r.id)
        ORDER BY r.started_at,r.id"""),
            {"cutoff": QUALITY_CUTOFF, "prompt": PROMPT_VERSION},
        )
        .scalars()
        .all()
    )
    approvals = [approve_run(db, str(run)) for run in runs]
    return {"cutoff": QUALITY_CUTOFF, "cleanup": cleanup, "approvals": approvals}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args(argv)
    if args.apply != args.approved:
        parser.error("A committed operation requires both --apply and --approved")
    with Session(engine) as db:
        try:
            db.execute(text("SET LOCAL lock_timeout='10s'"))
            db.execute(text("SET LOCAL statement_timeout='120s'"))
            result = run_maintenance(db)
            if args.apply:
                db.commit()
            else:
                db.rollback()
            print(json.dumps({"committed": args.apply, **result}, sort_keys=True))
        except Exception as exc:
            db.rollback()
            print(json.dumps({"committed": False, "error": str(exc)[:500]}))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
