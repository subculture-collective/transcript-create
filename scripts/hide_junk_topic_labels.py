#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text

# Ensure repo root on path when executed as /app/scripts/hide_junk_topic_labels.py.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.labeling.normalization import is_junk_phrase
from app.db import SessionLocal, engine


CONFIRMATION = "HIDE AUTOMATIC JUNK TOPIC LABELS"


BASE_LABELS_SQL = text(
    """
    SELECT
        l.id::text AS id,
        l.slug,
        l.label,
        l.created_at,
        l.canonical_id::text AS canonical_id,
        COUNT(a.id) AS assignments,
        COALESCE(BOOL_OR(a.status = 'admin_approved'), FALSE) AS has_admin_approved_assignment,
        COALESCE(BOOL_OR(a.source = 'admin'), FALSE) AS has_admin_source_assignment,
        EXISTS (
            SELECT 1
            FROM archive_label_feedback AS f
            WHERE f.label_id = l.id
        ) AS has_label_feedback,
        EXISTS (
            SELECT 1
            FROM archive_label_assignments AS af
            JOIN archive_label_feedback AS f ON f.assignment_id = af.id
            WHERE af.label_id = l.id
        ) AS has_assignment_feedback,
        EXISTS (
            SELECT 1
            FROM archive_label_aliases AS ali
            WHERE ali.label_id = l.id
              AND ali.status = 'active'
              AND ali.source IN ('admin', 'seed', 'hybrid')
        ) AS has_protected_alias
    FROM archive_labels AS l
    LEFT JOIN archive_label_assignments AS a ON a.label_id = l.id
    WHERE l.kind = 'topic'
      AND l.status = 'published'
      AND l.source = 'automatic'
      AND (:created_since = '' OR l.created_at >= CAST(:created_since AS timestamptz))
    GROUP BY l.id, l.slug, l.label, l.created_at, l.canonical_id
    ORDER BY l.id
    """
)

RUNNING_RUNS_SQL = text(
    """
    SELECT id, scope, extraction_tier, video_id, status, started_at, finished_at, model_name, prompt_version
    FROM archive_extraction_runs
    WHERE status = 'running'
    ORDER BY started_at
    """
)

DISTINCT_VIDEOS_FOR_LABELS_SQL = text(
    """
    SELECT COUNT(DISTINCT video_id) AS videos_touched
    FROM archive_label_assignments
    WHERE label_id IN :label_ids
    """
).bindparams(bindparam("label_ids", expanding=True))

ASSIGNMENT_DISTRIBUTION_SQL = text(
    """
    SELECT
        status AS assignment_status,
        source AS assignment_source,
        publish_tier,
        unit_type,
        COUNT(*) AS assignments
    FROM archive_label_assignments
    WHERE label_id IN :label_ids
    GROUP BY status, source, publish_tier, unit_type
    ORDER BY assignments DESC, status, source, publish_tier, unit_type
    LIMIT 40
    """
).bindparams(bindparam("label_ids", expanding=True))

HIDE_LABEL_SQL = text(
    """
    UPDATE archive_labels AS l
    SET status = 'hidden', updated_at = now()
    WHERE l.id = :label_id
      AND l.kind = 'topic'
      AND l.status = 'published'
      AND l.source = 'automatic'
      AND l.canonical_id IS NULL
      AND NOT EXISTS (SELECT 1 FROM archive_label_feedback AS f WHERE f.label_id = l.id)
      AND NOT EXISTS (
          SELECT 1
          FROM archive_label_assignments AS af
          JOIN archive_label_feedback AS f ON f.assignment_id = af.id
          WHERE af.label_id = l.id
      )
      AND NOT EXISTS (SELECT 1 FROM archive_label_assignments AS a WHERE a.label_id = l.id AND a.status = 'admin_approved')
      AND NOT EXISTS (SELECT 1 FROM archive_label_assignments AS a WHERE a.label_id = l.id AND a.source = 'admin')
      AND NOT EXISTS (
          SELECT 1
          FROM archive_label_aliases AS ali
          WHERE ali.label_id = l.id
            AND ali.status = 'active'
            AND ali.source IN ('admin', 'seed', 'hybrid')
      )
    RETURNING l.id::text AS id, l.slug, l.label
    """
)

DELETE_ASSIGNMENTS_FOR_LABEL_SQL = text(
    """
    WITH deleted AS (
        DELETE FROM archive_label_assignments AS a
        WHERE a.label_id = :label_id
          AND EXISTS (
              SELECT 1
              FROM archive_labels AS l
              WHERE l.id = a.label_id
                AND l.kind = 'topic'
                AND l.status = 'hidden'
          )
        RETURNING 1
    )
    SELECT COUNT(*) AS deleted_rows
    FROM deleted
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


def _int(value: Any) -> int:
    return int(value or 0)


def _exclusion_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if row.get("canonical_id"):
        reasons.append("canonical_label")
    if bool(row.get("has_label_feedback")):
        reasons.append("feedback_on_label")
    if bool(row.get("has_assignment_feedback")):
        reasons.append("feedback_on_assignments")
    if bool(row.get("has_admin_approved_assignment")):
        reasons.append("admin_approved_assignment")
    if bool(row.get("has_admin_source_assignment")):
        reasons.append("admin_source_assignment")
    if bool(row.get("has_protected_alias")):
        reasons.append("protected_alias_source")
    return reasons


def _load_plan(created_since: str = "") -> dict[str, Any]:
    base_labels = _fetch_mappings(BASE_LABELS_SQL, {"created_since": created_since})
    junk_labels = [row for row in base_labels if is_junk_phrase(str(row.get("label") or ""))]

    excluded_counts: Counter[str] = Counter()
    eligible_labels: list[dict[str, Any]] = []
    for row in junk_labels:
        reasons = _exclusion_reasons(row)
        if reasons:
            excluded_counts.update(reasons)
            continue
        eligible_labels.append(row)

    label_ids = [str(row["id"]) for row in eligible_labels]
    assignments_to_prune = sum(_int(row.get("assignments")) for row in eligible_labels)
    videos_touched = 0
    distribution: list[dict[str, Any]] = []
    if label_ids:
        videos_touched = _int(_fetch_scalar(DISTINCT_VIDEOS_FOR_LABELS_SQL, {"label_ids": label_ids}))
        distribution = _fetch_mappings(ASSIGNMENT_DISTRIBUTION_SQL, {"label_ids": label_ids})

    top_labels = [
        {
            "id": row["id"],
            "slug": row["slug"],
            "label": row["label"],
            "assignments": _int(row.get("assignments")),
        }
        for row in sorted(eligible_labels, key=lambda item: (-_int(item.get("assignments")), str(item.get("label") or "")))[:25]
    ]

    excluded_rows = [
        {"reason": reason, "labels": count}
        for reason, count in sorted(excluded_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    return {
        "created_since": created_since,
        "base_labels": base_labels,
        "junk_labels": junk_labels,
        "eligible_labels": eligible_labels,
        "assignments_to_prune": assignments_to_prune,
        "videos_touched": videos_touched,
        "excluded_rows": excluded_rows,
        "distribution": distribution,
        "top_labels": top_labels,
        "running_runs": _fetch_mappings(RUNNING_RUNS_SQL),
    }


def print_preflight(plan: dict[str, Any] | None = None, *, created_since: str = "") -> dict[str, Any]:
    plan = plan or _load_plan(created_since)
    print("Hide automatic junk topic labels preflight")
    print("target: archive_labels(kind='topic', status='published', source='automatic') filtered by Python is_junk_phrase(label)")
    if plan.get("created_since"):
        print(f"created_since: {plan['created_since']}")
    print(f"published_automatic_topic_labels: {len(plan['base_labels'])}")
    print(f"junk_candidate_labels: {len(plan['junk_labels'])}")
    print(f"eligible_labels_to_hide: {len(plan['eligible_labels'])}")
    print(f"excluded_junk_labels: {len(plan['junk_labels']) - len(plan['eligible_labels'])}")
    print(f"assignments_to_prune: {plan['assignments_to_prune']}")
    print(f"videos_touched: {plan['videos_touched']}")
    print(f"running_extraction_runs: {len(plan['running_runs'])}")

    _print_rows("Excluded junk label reasons", plan["excluded_rows"])
    _print_rows("Assignment distribution for eligible labels", plan["distribution"])
    _print_rows("Top eligible labels by assignments", plan["top_labels"])
    _print_rows("Running extraction runs", plan["running_runs"])
    return plan


def assert_safe_to_execute(args: argparse.Namespace) -> None:
    if args.confirm != CONFIRMATION:
        raise SystemExit(f'Execution requires --confirm "{CONFIRMATION}"')
    if not args.i_have_backup:
        raise SystemExit("Execution requires --i-have-backup after taking a current DB backup.")
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")
    if args.commit_labels < 1:
        raise SystemExit("--commit-labels must be >= 1")
    if args.max_batches is not None and args.max_batches < 1:
        raise SystemExit("--max-batches must be >= 1 when provided")


def assert_no_running_runs(allow_running_runs: bool) -> None:
    running_runs = _fetch_mappings(RUNNING_RUNS_SQL)
    if running_runs and not allow_running_runs:
        _print_rows("Blocking running extraction runs", running_runs)
        raise SystemExit("Refusing to execute while extraction runs are marked running. Pass --allow-running-runs to override.")


def _set_timeouts(db) -> None:
    db.execute(text("SET LOCAL lock_timeout = '2s'"))
    db.execute(text("SET LOCAL statement_timeout = '5min'"))


def hide_labels(eligible_labels: list[dict[str, Any]], commit_labels: int, max_batches: int | None, sleep_seconds: float) -> list[dict[str, Any]]:
    print(f"queued_eligible_labels={len(eligible_labels)}", flush=True)
    total_hidden: list[dict[str, Any]] = []
    batch_number = 0
    pending_labels = 0
    db = _session()
    try:
        _set_timeouts(db)
        for row in eligible_labels:
            returned = [dict(item) for item in db.execute(HIDE_LABEL_SQL, {"label_id": row["id"]}).mappings().all()]
            if returned:
                total_hidden.extend(returned)
                pending_labels += 1

            if pending_labels < commit_labels:
                continue

            db.commit()
            batch_number += 1
            print(f"hide batch complete: batch={batch_number} labels={pending_labels} total_hidden={len(total_hidden)}", flush=True)
            if max_batches is not None and batch_number >= max_batches:
                print(f"stopping after max_batches={max_batches}")
                return total_hidden
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            pending_labels = 0
            _set_timeouts(db)

        if pending_labels > 0:
            db.commit()
            batch_number += 1
            print(f"hide batch complete: batch={batch_number} labels={pending_labels} total_hidden={len(total_hidden)}", flush=True)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    if batch_number == 0:
        print("hide batch complete: labels=0")
    return total_hidden


def prune_assignments_for_labels(label_ids: list[str], batch_size: int, commit_labels: int, max_batches: int | None, sleep_seconds: float) -> int:
    total_deleted = 0
    batch_number = 0
    pending_deleted = 0
    pending_labels = 0
    db = _session()
    try:
        _set_timeouts(db)
        for label_id in label_ids:
            deleted = int(db.execute(DELETE_ASSIGNMENTS_FOR_LABEL_SQL, {"label_id": label_id}).scalar_one())
            pending_deleted += deleted
            pending_labels += 1

            if pending_deleted < batch_size and pending_labels < commit_labels:
                continue

            db.commit()
            batch_number += 1
            total_deleted += pending_deleted
            print(
                f"prune batch complete: batch={batch_number} labels={pending_labels} "
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
            _set_timeouts(db)

        if pending_labels > 0:
            db.commit()
            batch_number += 1
            total_deleted += pending_deleted
            print(
                f"prune batch complete: batch={batch_number} labels={pending_labels} "
                f"deleted_rows={pending_deleted} total_deleted={total_deleted}",
                flush=True,
            )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    if batch_number == 0:
        print("prune batch complete: deleted_rows=0")
    return total_deleted


def vacuum_after_delete() -> None:
    print("running VACUUM (ANALYZE, PARALLEL 0) archive_label_assignments", flush=True)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("VACUUM (ANALYZE, PARALLEL 0) archive_label_assignments"))
        connection.execute(text("ANALYZE archive_labels"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hide automatic junk topic labels and prune their assignments safely.",
        epilog=(
            "Default mode is read-only. Example execute command: "
            f'python scripts/hide_junk_topic_labels.py --execute --i-have-backup --confirm "{CONFIRMATION}"'
        ),
    )
    parser.add_argument("--execute", action="store_true", help="Actually change rows. Default is read-only.")
    parser.add_argument("--confirm", default="", help="Required exact confirmation phrase for --execute.")
    parser.add_argument("--i-have-backup", action="store_true", help="Required for --execute after taking a current DB backup.")
    parser.add_argument("--batch-size", type=int, default=50_000, help="Assignment rows to prune per batch.")
    parser.add_argument("--commit-labels", type=int, default=250, help="Commit after this many labels even if --batch-size is not reached.")
    parser.add_argument("--max-batches", type=int, default=None, help="Optional safety cap for hide/prune batches.")
    parser.add_argument("--sleep-seconds", type=float, default=0.25, help="Delay between batches.")
    parser.add_argument(
        "--created-since",
        default="",
        help="Optional timestamptz lower bound for label created_at, e.g. 2026-06-20T21:00:00+00:00.",
    )
    parser.add_argument("--allow-running-runs", action="store_true", help="Allow execution even if extraction runs are marked running.")
    parser.add_argument("--no-vacuum", action="store_true", help="Skip VACUUM (ANALYZE) after pruning.")
    args = parser.parse_args()

    plan = print_preflight(created_since=args.created_since)
    if not args.execute:
        print("\nDry run only. No rows were changed.")
        return

    assert_safe_to_execute(args)
    assert_no_running_runs(args.allow_running_runs)
    hidden = hide_labels(plan["eligible_labels"], args.commit_labels, args.max_batches, args.sleep_seconds)
    hidden_ids = [str(row["id"]) for row in hidden]
    print(f"hidden_topic_labels={len(hidden_ids)}")
    deleted = prune_assignments_for_labels(hidden_ids, args.batch_size, args.commit_labels, args.max_batches, args.sleep_seconds)
    print(f"hidden_topic_assignment_prune complete: deleted_rows={deleted}")
    if not args.no_vacuum and deleted > 0:
        vacuum_after_delete()
    print_preflight(created_since=args.created_since)


if __name__ == "__main__":
    main()
