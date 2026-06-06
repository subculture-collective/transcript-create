#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from sqlalchemy import text

# Ensure repo root on path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.labeling.pipeline import extract_labels_for_video
from app.archive.labeling.repository import create_extraction_run, finish_extraction_run
from app.db import SessionLocal


def _json_metrics(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}
    return {}


def _run_scope(title_only: bool) -> str:
    return "video_title" if title_only else "video"


def _create_parent_run(*, limit: int, extraction_tier: str, title_only: bool, workers: int) -> str:
    db = SessionLocal()
    try:
        parent_run_id = create_extraction_run(
            db,
            scope="backfill",
            extraction_tier=extraction_tier,
            video_id=None,
            model_name="deterministic",
        )
        db.execute(
            text(
                """
                UPDATE archive_extraction_runs
                SET metrics = CAST(:metrics AS jsonb)
                WHERE id = :run_id
                """
            ),
            {
                "run_id": parent_run_id,
                "metrics": json.dumps(
                    {
                        "remaining": int(limit),
                        "claimed": 0,
                        "workers": int(workers),
                        "run_scope": _run_scope(title_only),
                    }
                ),
            },
        )
        db.commit()
        return parent_run_id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _claim_video(
    *,
    parent_run_id: str,
    extraction_tier: str,
    max_duration_seconds: int | None,
    title_only: bool,
    retry_stale_minutes: int,
) -> dict[str, str] | None:
    duration_sql = ""
    params: dict[str, object] = {
        "parent_run_id": parent_run_id,
        "extraction_tier": extraction_tier,
        "run_scope": _run_scope(title_only),
        "retry_stale_minutes": retry_stale_minutes,
    }
    if max_duration_seconds is not None:
        duration_sql = "AND COALESCE(v.duration_seconds, 0) <= :max_duration_seconds"
        params["max_duration_seconds"] = max_duration_seconds

    transcript_sql = "" if title_only else """
                  AND (EXISTS (SELECT 1 FROM segments AS s WHERE s.video_id = v.id)
                   OR EXISTS (SELECT 1 FROM youtube_transcripts AS yt WHERE yt.video_id = v.id))
    """

    db = SessionLocal()
    try:
        parent_row = db.execute(
            text(
                """
                SELECT id, metrics
                FROM archive_extraction_runs
                WHERE id = :parent_run_id
                FOR UPDATE
                """
            ),
            {"parent_run_id": parent_run_id},
        ).mappings().first()
        if parent_row is None:
            db.rollback()
            return None
        metrics = _json_metrics(parent_row.get("metrics"))
        remaining = int(metrics.get("remaining") or 0)
        if remaining <= 0:
            db.rollback()
            return None

        video_row = db.execute(
            text(
                f"""
                SELECT v.id
                FROM videos AS v
                WHERE 1 = 1
                  {transcript_sql}
                  {duration_sql}
                  AND NOT EXISTS (
                    SELECT 1
                    FROM archive_extraction_runs AS r
                    WHERE r.video_id = v.id
                      AND r.scope = :run_scope
                      AND r.extraction_tier = :extraction_tier
                      AND (
                        r.status = 'completed'
                        OR (
                          r.status = 'running'
                          AND r.started_at > now() - (:retry_stale_minutes || ' minutes')::interval
                        )
                      )
                  )
                ORDER BY COALESCE(v.duration_seconds, 999999) ASC,
                         COALESCE(v.uploaded_at, v.created_at) DESC NULLS LAST
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            ),
            params,
        ).first()
        if video_row is None:
            metrics["remaining"] = 0
            db.execute(
                text("UPDATE archive_extraction_runs SET metrics = CAST(:metrics AS jsonb) WHERE id = :parent_run_id"),
                {"parent_run_id": parent_run_id, "metrics": json.dumps(metrics)},
            )
            db.commit()
            return None

        video_id = str(video_row[0])
        child_run_id = create_extraction_run(
            db,
            scope=str(params["run_scope"]),
            extraction_tier=extraction_tier,
            video_id=video_id,
            model_name="deterministic",
        )
        metrics["remaining"] = remaining - 1
        metrics["claimed"] = int(metrics.get("claimed") or 0) + 1
        db.execute(
            text("UPDATE archive_extraction_runs SET metrics = CAST(:metrics AS jsonb) WHERE id = :parent_run_id"),
            {"parent_run_id": parent_run_id, "metrics": json.dumps(metrics)},
        )
        db.commit()
        return {"video_id": video_id, "run_id": child_run_id, "index": str(metrics["claimed"])}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _mark_claim_failed(run_id: str, metrics: dict[str, int], error: str) -> None:
    db = SessionLocal()
    try:
        finish_extraction_run(db, run_id, "failed", metrics, error=error)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _worker_loop(
    *,
    worker_id: int,
    parent_run_id: str,
    extraction_tier: str,
    max_duration_seconds: int | None,
    title_only: bool,
    no_keyphrases: bool,
    stop_on_error: bool,
    retry_stale_minutes: int,
) -> dict[str, int]:
    totals = {"videos": 0, "windows": 0, "candidates": 0, "assignments": 0, "errors": 0}
    while True:
        claim = _claim_video(
            parent_run_id=parent_run_id,
            extraction_tier=extraction_tier,
            max_duration_seconds=max_duration_seconds,
            title_only=title_only,
            retry_stale_minutes=retry_stale_minutes,
        )
        if claim is None:
            break

        video_id = claim["video_id"]
        run_id = claim["run_id"]
        print(
            f"label extraction claimed video: index={claim['index']} run_id={run_id} "
            f"video_id={video_id} worker={worker_id}",
            flush=True,
        )
        db = SessionLocal()
        try:
            result = extract_labels_for_video(
                db,
                video_id,
                extraction_tier=extraction_tier,
                title_only=title_only,
                include_keyphrases=not no_keyphrases,
                run_id=run_id,
            )
            db.commit()
            totals["videos"] += 1
            totals["windows"] += int(result.get("windows") or 0)
            totals["candidates"] += int(result.get("candidates") or 0)
            totals["assignments"] += int(result.get("assignments") or 0)
            progress = {"worker": worker_id, "index": claim["index"], **result}
            print(
                "label extraction backfilled video: "
                + " ".join(f"{key}={value}" for key, value in sorted(progress.items())),
                flush=True,
            )
        except Exception as exc:
            db.rollback()
            totals["errors"] += 1
            _mark_claim_failed(run_id, {"windows": 0, "candidates": 0, "assignments": 0}, str(exc))
            print(
                f"label extraction backfill error: worker={worker_id} index={claim['index']} "
                f"video_id={video_id} error={exc}",
                flush=True,
            )
            if stop_on_error:
                raise
        finally:
            db.close()

    return totals


def _finish_parent_run(parent_run_id: str, totals: dict[str, int], status: str = "completed") -> None:
    db = SessionLocal()
    try:
        finish_extraction_run(db, parent_run_id, status, totals)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main(
    *,
    limit: int = 10,
    extraction_tier: str = "cheap",
    max_duration_seconds: int | None = None,
    title_only: bool = False,
    no_keyphrases: bool = False,
    stop_on_error: bool = False,
    workers: int = 1,
    retry_stale_minutes: int = 720,
) -> None:
    workers = max(1, int(workers or 1))
    parent_run_id = _create_parent_run(
        limit=limit,
        extraction_tier=extraction_tier,
        title_only=title_only,
        workers=workers,
    )
    totals = {"videos": 0, "windows": 0, "candidates": 0, "assignments": 0, "errors": 0}
    status = "completed"
    try:
        if workers == 1:
            worker_totals = [
                _worker_loop(
                    worker_id=1,
                    parent_run_id=parent_run_id,
                    extraction_tier=extraction_tier,
                    max_duration_seconds=max_duration_seconds,
                    title_only=title_only,
                    no_keyphrases=no_keyphrases,
                    stop_on_error=stop_on_error,
                    retry_stale_minutes=retry_stale_minutes,
                )
            ]
        else:
            with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as executor:
                futures = [
                    executor.submit(
                        _worker_loop,
                        worker_id=worker_id,
                        parent_run_id=parent_run_id,
                        extraction_tier=extraction_tier,
                        max_duration_seconds=max_duration_seconds,
                        title_only=title_only,
                        no_keyphrases=no_keyphrases,
                        stop_on_error=stop_on_error,
                        retry_stale_minutes=retry_stale_minutes,
                    )
                    for worker_id in range(1, workers + 1)
                ]
                worker_totals = [future.result() for future in as_completed(futures)]

        for worker_result in worker_totals:
            for key in totals:
                totals[key] += int(worker_result.get(key) or 0)
    except Exception:
        status = "failed"
        raise
    finally:
        _finish_parent_run(parent_run_id, totals, status=status)

    print("label extraction backfill complete: " + " ".join(f"{key}={value}" for key, value in sorted(totals.items())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill label extraction for recent videos.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum videos to process")
    parser.add_argument("--max-duration-seconds", type=int, default=None, help="Skip videos longer than this duration")
    parser.add_argument("--title-only", action="store_true", help="Only match curated aliases against video titles")
    parser.add_argument("--no-keyphrases", action="store_true", help="Skip automatic keyphrase candidates")
    parser.add_argument("--workers", type=int, default=1, help="Parallel worker processes")
    parser.add_argument(
        "--retry-stale-minutes",
        type=int,
        default=720,
        help="Retry videos with running claims older than this many minutes",
    )
    parser.add_argument("--stop-on-error", action="store_true", help="Abort on first video error")
    parser.add_argument(
        "--extraction-tier",
        choices=("cheap", "balanced", "premium"),
        default="cheap",
        help="Extraction tier to use",
    )
    args = parser.parse_args()
    main(
        limit=args.limit,
        extraction_tier=args.extraction_tier,
        max_duration_seconds=args.max_duration_seconds,
        title_only=args.title_only,
        no_keyphrases=args.no_keyphrases,
        stop_on_error=args.stop_on_error,
        workers=args.workers,
        retry_stale_minutes=args.retry_stale_minutes,
    )
