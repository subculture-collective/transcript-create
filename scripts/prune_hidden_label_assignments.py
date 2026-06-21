#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import text

# Ensure repo root on path when executed as /app/scripts/prune_hidden_label_assignments.py.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db import SessionLocal, engine


CONFIRMATION = "DELETE HIDDEN TOPIC ASSIGNMENTS"


TARGET_STATS_SQL = text(
    """
    SELECT
        COUNT(*) AS assignments_to_delete,
        COUNT(DISTINCT a.label_id) AS labels_touched,
        COUNT(DISTINCT a.video_id) AS videos_touched,
        MIN(a.created_at) AS oldest_assignment,
        MAX(a.created_at) AS newest_assignment
    FROM archive_label_assignments AS a
    JOIN archive_labels AS l ON l.id = a.label_id
    WHERE l.kind = 'topic'
      AND l.status = 'hidden'
    """
)

QUICK_LABEL_STATS_SQL = text(
    """
    SELECT
        COUNT(*) AS hidden_topic_labels
    FROM archive_labels AS l
    WHERE l.kind = 'topic'
      AND l.status = 'hidden'
    """
)

FEEDBACK_COUNT_SQL = text(
    """
    SELECT COUNT(*) AS feedback_rows_touching_target
    FROM archive_label_feedback AS f
    JOIN archive_label_assignments AS a ON a.id = f.assignment_id
    JOIN archive_labels AS l ON l.id = a.label_id
    WHERE l.kind = 'topic'
      AND l.status = 'hidden'
    """
)

ORPHAN_WINDOW_COUNT_SQL = text(
    """
    SELECT COUNT(*) AS orphan_windows_before_prune
    FROM archive_transcript_windows AS w
    WHERE NOT EXISTS (
        SELECT 1
        FROM archive_label_assignments AS a
        WHERE a.window_id = w.id
    )
    """
)

TARGET_DISTRIBUTION_SQL = text(
    """
    SELECT
        a.status AS assignment_status,
        a.publish_tier,
        a.unit_type,
        a.source,
        COUNT(*) AS assignments
    FROM archive_label_assignments AS a
    JOIN archive_labels AS l ON l.id = a.label_id
    WHERE l.kind = 'topic'
      AND l.status = 'hidden'
    GROUP BY a.status, a.publish_tier, a.unit_type, a.source
    ORDER BY assignments DESC
    LIMIT 20
    """
)

TOP_LABELS_SQL = text(
    """
    SELECT
        l.id,
        l.slug,
        l.label,
        COUNT(*) AS assignments
    FROM archive_label_assignments AS a
    JOIN archive_labels AS l ON l.id = a.label_id
    WHERE l.kind = 'topic'
      AND l.status = 'hidden'
    GROUP BY l.id, l.slug, l.label
    ORDER BY assignments DESC
    LIMIT 25
    """
)

RUNNING_RUNS_SQL = text(
    """
    SELECT
        id,
        scope,
        extraction_tier,
        video_id,
        started_at,
        finished_at,
        model_name,
        prompt_version
    FROM archive_extraction_runs
    WHERE status = 'running'
    ORDER BY started_at
    """
)

STALE_RUNS_SQL = text(
    """
    SELECT
        id,
        scope,
        extraction_tier,
        video_id,
        started_at,
        finished_at,
        model_name,
        prompt_version
    FROM archive_extraction_runs
    WHERE status = 'running'
      AND started_at < now() - (:stale_hours || ' hours')::interval
    ORDER BY started_at
    """
)

CANCEL_STALE_RUNS_SQL = text(
    """
    UPDATE archive_extraction_runs
    SET
        status = 'cancelled',
        finished_at = COALESCE(finished_at, now()),
        error = CASE
            WHEN error IS NULL OR error = '' THEN :reason
            ELSE error || E'\n' || :reason
        END
    WHERE status = 'running'
      AND started_at < now() - (:stale_hours || ' hours')::interval
    RETURNING id, scope, extraction_tier, video_id, started_at, status
    """
)

DELETE_BATCH_SQL = text(
    """
    WITH deleted AS (
        DELETE FROM archive_label_assignments AS a
        USING archive_labels AS l
        WHERE a.label_id = :label_id
          AND l.id = a.label_id
          AND l.kind = 'topic'
          AND l.status = 'hidden'
        RETURNING 1
    )
    SELECT COUNT(*) AS deleted_rows
    FROM deleted
    """
)

HIDDEN_TOPIC_LABELS_WITH_ASSIGNMENTS_SQL = text(
    """
    SELECT l.id, l.slug, l.label
    FROM archive_labels AS l
    WHERE l.kind = 'topic'
      AND l.status = 'hidden'
    ORDER BY l.id
    """
)


def _session():
    return SessionLocal()


def _fetch_mappings(sql, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    db = _session()
    try:
        return [dict(row) for row in db.execute(sql, params or {}).mappings().all()]
    finally:
        db.close()


def _fetch_scalar(sql, params: dict[str, Any] | None = None) -> Any:
    db = _session()
    try:
        return db.execute(sql, params or {}).scalar_one()
    finally:
        db.close()


def _print_rows(title: str, rows: list[dict[str, Any]]) -> None:
    print(f"\n== {title} ==")
    if not rows:
        print("(none)")
        return
    columns = list(rows[0].keys())
    print("\t".join(columns))
    for row in rows:
        print("\t".join(str(row.get(column, "")) for column in columns))


def print_preflight(stale_hours: int, *, exact: bool = False) -> None:
    quick_stats = _fetch_mappings(QUICK_LABEL_STATS_SQL)[0]
    running_runs = _fetch_mappings(RUNNING_RUNS_SQL)
    stale_runs = _fetch_mappings(STALE_RUNS_SQL, {"stale_hours": stale_hours})

    print("Hidden topic assignment prune preflight")
    print("target: archive_label_assignments joined to archive_labels(kind='topic', status='hidden')")
    for key, value in quick_stats.items():
        print(f"{key}: {value}")
    print(f"running_extraction_runs: {len(running_runs)}")
    print(f"stale_running_extraction_runs_older_than_{stale_hours}h: {len(stale_runs)}")

    if exact:
        stats = _fetch_mappings(TARGET_STATS_SQL)[0]
        feedback_count = _fetch_scalar(FEEDBACK_COUNT_SQL)
        orphan_window_count = _fetch_scalar(ORPHAN_WINDOW_COUNT_SQL)
        for key, value in stats.items():
            print(f"{key}: {value}")
        print(f"feedback_rows_touching_target: {feedback_count}")
        print(f"orphan_windows_before_prune: {orphan_window_count}")
        _print_rows("Target distribution", _fetch_mappings(TARGET_DISTRIBUTION_SQL))
        _print_rows("Top hidden topic labels", _fetch_mappings(TOP_LABELS_SQL))
    else:
        print("exact assignment counts skipped; pass --exact-preflight for the slower full-count report")

    _print_rows("Running extraction runs", running_runs)


def cancel_stale_runs(stale_hours: int) -> int:
    db = _session()
    try:
        rows = [
            dict(row)
            for row in db.execute(
                CANCEL_STALE_RUNS_SQL,
                {
                    "stale_hours": stale_hours,
                    "reason": "Cancelled before hidden-topic assignment prune.",
                },
            )
            .mappings()
            .all()
        ]
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    _print_rows("Cancelled stale extraction runs", rows)
    return len(rows)


def assert_safe_to_execute(args: argparse.Namespace) -> None:
    if args.confirm != CONFIRMATION:
        raise SystemExit(f'Execution requires --confirm "{CONFIRMATION}"')
    if not args.i_have_backup:
        raise SystemExit("Execution requires --i-have-backup after taking a current DB backup.")
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")
    if args.max_batches is not None and args.max_batches < 1:
        raise SystemExit("--max-batches must be >= 1 when provided")
    if args.stale_hours < 1:
        raise SystemExit("--stale-hours must be >= 1")


def assert_no_running_runs(allow_running_runs: bool) -> None:
    running_runs = _fetch_mappings(RUNNING_RUNS_SQL)
    if running_runs and not allow_running_runs:
        _print_rows("Blocking running extraction runs", running_runs)
        raise SystemExit(
            "Refusing to prune while extraction runs are marked running. "
            "Pause extraction and either mark stale runs with --cancel-stale-runs "
            "or pass --allow-running-runs if you intentionally accept that risk."
        )


def _set_delete_timeouts(db) -> None:
    db.execute(text("SET LOCAL lock_timeout = '2s'"))
    db.execute(text("SET LOCAL statement_timeout = '5min'"))


def delete_batches(batch_size: int, max_batches: int | None, sleep_seconds: float, commit_labels: int) -> int:
    label_rows = _fetch_mappings(HIDDEN_TOPIC_LABELS_WITH_ASSIGNMENTS_SQL)
    print(f"queued_hidden_topic_labels={len(label_rows)}", flush=True)

    total_deleted = 0
    batch_number = 0
    pending_deleted = 0
    pending_labels = 0
    db = _session()
    try:
        _set_delete_timeouts(db)
        for row in label_rows:
            deleted = int(db.execute(DELETE_BATCH_SQL, {"label_id": row["id"]}).scalar_one())
            pending_deleted += deleted
            pending_labels += 1

            if pending_deleted < batch_size and pending_labels < commit_labels:
                continue

            db.commit()
            batch_number += 1
            total_deleted += pending_deleted
            print(
                f"delete batch complete: batch={batch_number} labels={pending_labels} "
                f"deleted_rows={pending_deleted} total_deleted={total_deleted}",
                flush=True,
            )

            if max_batches is not None and batch_number >= max_batches:
                print(f"stopping after max_batches={max_batches}")
                return total_deleted

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

            pending_deleted = 0
            pending_labels = 0
            _set_delete_timeouts(db)

        if pending_labels > 0:
            db.commit()
            batch_number += 1
            total_deleted += pending_deleted
            print(
                f"delete batch complete: batch={batch_number} labels={pending_labels} "
                f"deleted_rows={pending_deleted} total_deleted={total_deleted}",
                flush=True,
            )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    if batch_number == 0:
        print("delete batch complete: deleted_rows=0")
    return total_deleted


def delete_batches_by_assignment_id(batch_size: int, max_batches: int | None, sleep_seconds: float) -> int:
    total_deleted = 0
    batch_number = 0
    old_delete_sql = text(
        """
        WITH doomed AS (
            SELECT a.id
            FROM archive_label_assignments AS a
            JOIN archive_labels AS l ON l.id = a.label_id
            WHERE l.kind = 'topic'
              AND l.status = 'hidden'
            ORDER BY a.id
            LIMIT :batch_size
            FOR UPDATE OF a SKIP LOCKED
        ),
        deleted AS (
            DELETE FROM archive_label_assignments AS a
            USING doomed AS d
            WHERE a.id = d.id
            RETURNING 1
        )
        SELECT COUNT(*) AS deleted_rows
        FROM deleted
        """
    )
    while True:
        db = _session()
        try:
            _set_delete_timeouts(db)
            deleted = int(db.execute(old_delete_sql, {"batch_size": batch_size}).scalar_one())
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        if deleted == 0:
            print("delete batch complete: deleted_rows=0")
            break

        batch_number += 1
        total_deleted += deleted
        print(f"delete batch complete: batch={batch_number} deleted_rows={deleted} total_deleted={total_deleted}", flush=True)

        if max_batches is not None and batch_number >= max_batches:
            print(f"stopping after max_batches={max_batches}")
            break

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return total_deleted


def vacuum_after_delete() -> None:
    print("running VACUUM (ANALYZE, PARALLEL 0) archive_label_assignments", flush=True)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("VACUUM (ANALYZE, PARALLEL 0) archive_label_assignments"))
        connection.execute(text("ANALYZE archive_labels"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safely prune assignments for hidden topic labels without deleting the labels themselves.",
        epilog=(
            "Default mode is read-only. Example execute command: "
            f'python scripts/prune_hidden_label_assignments.py --execute --i-have-backup '
            f'--cancel-stale-runs --confirm "{CONFIRMATION}"'
        ),
    )
    parser.add_argument("--execute", action="store_true", help="Actually delete target assignments. Default is read-only.")
    parser.add_argument("--confirm", default="", help="Required exact confirmation phrase for --execute.")
    parser.add_argument("--i-have-backup", action="store_true", help="Required for --execute after taking a current DB backup.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50_000,
        help="Commit after at least this many deleted rows; a single hot label can exceed this.",
    )
    parser.add_argument("--max-batches", type=int, default=None, help="Optional safety cap for delete batches.")
    parser.add_argument("--sleep-seconds", type=float, default=0.25, help="Delay between delete batches.")
    parser.add_argument("--commit-labels", type=int, default=250, help="Commit after this many hidden labels even if --batch-size is not reached.")
    parser.add_argument("--exact-preflight", action="store_true", help="Run slower exact counts/distribution before and after pruning.")
    parser.add_argument(
        "--legacy-assignment-id-loop",
        action="store_true",
        help="Use the original ordered assignment-id batch loop. Usually slower after partial deletes.",
    )
    parser.add_argument("--stale-hours", type=int, default=6, help="Age threshold for --cancel-stale-runs.")
    parser.add_argument(
        "--cancel-stale-runs",
        action="store_true",
        help="Before deleting, mark running extraction runs older than --stale-hours as cancelled.",
    )
    parser.add_argument(
        "--allow-running-runs",
        action="store_true",
        help="Allow pruning even if extraction runs are still marked running. Not recommended.",
    )
    parser.add_argument("--no-vacuum", action="store_true", help="Skip VACUUM (ANALYZE) after deletion.")
    args = parser.parse_args()

    print_preflight(args.stale_hours, exact=args.exact_preflight)

    if not args.execute:
        print("\nDry run only. No rows were changed.")
        return

    assert_safe_to_execute(args)
    if args.cancel_stale_runs:
        cancel_stale_runs(args.stale_hours)
    assert_no_running_runs(args.allow_running_runs)

    if args.legacy_assignment_id_loop:
        total_deleted = delete_batches_by_assignment_id(args.batch_size, args.max_batches, args.sleep_seconds)
    else:
        total_deleted = delete_batches(args.batch_size, args.max_batches, args.sleep_seconds, args.commit_labels)
    print(f"hidden topic assignment prune complete: deleted_rows={total_deleted}")

    if not args.no_vacuum and total_deleted > 0:
        vacuum_after_delete()

    print_preflight(args.stale_hours, exact=args.exact_preflight)


if __name__ == "__main__":
    main()
