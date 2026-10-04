#!/usr/bin/env python3
"""Dry-run-first, bounded recovery for reviewed needs-attention and failed cohorts.

``alignment`` and ``yt-dlp`` select pending videos held by needs-attention jobs.
``failed-gpu-unavailable`` and ``failed-yt-dlp`` select terminally failed videos
whose recorded error matches the cohort. Each selected video moves to a fresh
single-video recovery job with a new attempt budget; failed videos also return
to the pending state. Ordinary job retry/requeue cannot do this because it
resets only the job row while the video stays failed.
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from app.audit import ACTION_ADMIN_ACTION, write_audit_event
from app.db import SessionLocal
from worker.state_model import TERMINAL_CAPTION_INGEST_STATES, VideoState, pending_video_eligibility_sql

ATTENTION_COHORT_PATTERNS = {
    "alignment": ("%align%", "%boolean index did not match indexed array%"),
    "yt-dlp": ("%yt-dlp%", "%youtube-dl%"),
}
FAILED_COHORT_PATTERNS = {
    "failed-gpu-unavailable": ("%no CUDA-capable device%", "%no GPU configuration succeeded%"),
    "failed-yt-dlp": ("%yt-dlp%", "%youtube-dl%"),
}
COHORT_PATTERNS = {**ATTENTION_COHORT_PATTERNS, **FAILED_COHORT_PATTERNS}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True, choices=sorted(COHORT_PATTERNS))
    parser.add_argument("--limit", required=True, type=int)
    parser.add_argument("--confirm", help="Required for mutation; must be RECOVER")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 5:
        parser.error("--limit must be between 1 and 5")
    return args


def recover(*, cohort: str, limit: int, mutate: bool) -> list[dict[str, str]]:
    db = SessionLocal()
    try:
        if mutate:
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext('hasanara-attention-recovery'))"))
        eligible = int(
            db.execute(
                text(f"SELECT COUNT(*) {pending_video_eligibility_sql()}"),
                {"pending_state": VideoState.PENDING.value},
            ).scalar_one()
        )
        available = max(0, 5 - eligible)
        if mutate and available == 0:
            raise RuntimeError(f"no recovery slots are available; {eligible} videos are already eligible")
        selection_limit = min(limit, available) if mutate else limit
        patterns = COHORT_PATTERNS[cohort]
        failed_cohort = cohort in FAILED_COHORT_PATTERNS
        source_job_state = "failed" if failed_cohort else "needs_attention"
        source_video_state = VideoState.FAILED.value if failed_cohort else VideoState.PENDING.value
        rows = (
            db.execute(
                text("""
                    SELECT j.id AS job_id, v.id AS video_id
                    FROM jobs j
                    JOIN videos v ON v.job_id = j.id
                    WHERE j.state = CAST(:source_job_state AS job_state)
                      AND v.state = CAST(:source_video_state AS job_state)
                      AND v.caption_ingest_state = ANY(CAST(:terminal_states AS text[]))
                      AND (v.diarization_error IS NULL OR v.diarization_error NOT LIKE 'canary-%')
                      AND EXISTS (
                          SELECT 1 FROM unnest(CAST(:patterns AS text[])) pattern
                          WHERE CASE WHEN CAST(:failed_cohort AS boolean)
                                THEN COALESCE(v.error, '')
                                ELSE COALESCE(j.last_failure_summary, j.error, '') END ILIKE pattern
                      )
                      AND (
                          NOT CAST(:failed_cohort AS boolean)
                          OR NOT EXISTS (
                              SELECT 1 FROM videos other
                              WHERE other.youtube_id = v.youtube_id
                                AND other.id <> v.id
                                AND other.state <> CAST(:source_video_state AS job_state)
                          )
                      )
                    ORDER BY j.updated_at, j.id, v.id
                    FOR UPDATE OF j, v SKIP LOCKED
                    LIMIT :limit
                """),
                {
                    "source_job_state": source_job_state,
                    "source_video_state": source_video_state,
                    "failed_cohort": failed_cohort,
                    "terminal_states": list(TERMINAL_CAPTION_INGEST_STATES),
                    "patterns": list(patterns),
                    "limit": selection_limit,
                },
            )
            .mappings()
            .all()
        )
        selected = [{"source_job_id": str(row["job_id"]), "video_id": str(row["video_id"])} for row in rows]
        if not mutate:
            db.rollback()
            return selected
        recovered: list[dict[str, str]] = []
        source_job_ids: set[str] = set()
        for row in selected:
            source_job_id = row["source_job_id"]
            source_job_ids.add(source_job_id)
            recovery_job_id = str(
                db.execute(
                    text("""
                        INSERT INTO jobs (
                            kind, input_url, priority, meta, owner_user_id,
                            state, stage, completed_units, total_units
                        )
                        SELECT
                            'single', 'https://www.youtube.com/watch?v=' || v.youtube_id,
                            j.priority,
                            (COALESCE(j.meta, '{}'::jsonb)
                                - 'normalized_url' - 'idempotency_key'
                                - 'staged' - 'batch_id' - 'batch_expected_jobs')
                                || jsonb_build_object('recovery', jsonb_build_object(
                                    'cohort', CAST(:cohort AS text),
                                    'source_job_id', j.id::text,
                                    'source_video_id', v.id::text
                                )),
                            j.owner_user_id, 'pending', 'queued', 0, 1
                        FROM jobs j
                        JOIN videos v ON v.job_id = j.id
                        WHERE j.id=:source_job_id AND j.state=CAST(:source_job_state AS job_state)
                          AND v.id=:video_id AND v.state=CAST(:source_video_state AS job_state)
                          AND v.caption_ingest_state = ANY(CAST(:terminal_states AS text[]))
                        RETURNING id
                    """),
                    {
                        "cohort": cohort,
                        "source_job_state": source_job_state,
                        "source_video_state": source_video_state,
                        "source_job_id": source_job_id,
                        "video_id": row["video_id"],
                        "terminal_states": list(TERMINAL_CAPTION_INGEST_STATES),
                    },
                ).scalar_one()
            )
            moved = db.execute(
                text("""
                    UPDATE videos
                    SET job_id=:recovery_job_id, idx=0, state='pending', error=NULL, updated_at=now()
                    WHERE id=:video_id AND job_id=:source_job_id
                      AND state=CAST(:source_video_state AS job_state)
                """),
                {
                    "source_video_state": source_video_state,
                    "recovery_job_id": recovery_job_id,
                    "video_id": row["video_id"],
                    "source_job_id": source_job_id,
                },
            )
            if moved.rowcount != 1:
                raise RuntimeError("recovery video ownership transfer did not affect exactly one row")
            write_audit_event(
                db,
                ACTION_ADMIN_ACTION,
                resource_type="recovery_job",
                resource_id=recovery_job_id,
                details={
                    "operation": "backlog_recovery",
                    "cohort": cohort,
                    "source_job_id": source_job_id,
                    "source_job_state": source_job_state,
                    "video_id": row["video_id"],
                },
            )
            recovered.append({**row, "job_id": recovery_job_id})
        for source_job_id in source_job_ids:
            db.execute(
                text("""
                    UPDATE jobs j
                    SET state='completed', stage='completed', error=NULL,
                        last_failure_summary=NULL, updated_at=now()
                    WHERE j.id=:source_job_id AND j.state=CAST(:source_job_state AS job_state)
                      AND NOT EXISTS (
                          SELECT 1 FROM videos v
                          WHERE v.job_id=j.id AND v.state <> 'completed'
                      )
                """),
                {"source_job_id": source_job_id, "source_job_state": source_job_state},
            )
        db.commit()
        return recovered
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    mutate = args.confirm == "RECOVER"
    rows = recover(cohort=args.cohort, limit=args.limit, mutate=mutate)
    print(json.dumps({"mode": "recovery" if mutate else "dry-run", "cohort": args.cohort, "selected": rows}))
    if not mutate:
        print("Dry run only. Re-run with --confirm RECOVER to mutate exactly this bounded cohort.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
