#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import signal
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.enrichment_queue import (
    OWNER_LOCK,
    discover_jobs,
    finish_job,
    next_job,
    pause_queue,
    queue_status,
    reconcile_input_run,
    requeue_run,
    resume_queue,
)
from app.archive.enrichment_service import enrich_video_candidates
from app.archive.openrouter_enrichment import PROMPT_VERSION
from app.db import SessionLocal, engine
from app.settings import settings


@dataclass(frozen=True)
class QueueDependencies:
    select_video: Callable[[Any, str, str, int], str | None]
    enrich_video: Callable[[Any, str], dict[str, Any]]
    on_credit_exhausted: Callable[[Any, str, str], None] | None = None
    load_guardrail_snapshot: Callable[[Any, str, int], "QueueGuardrailSnapshot"] | None = None
    select_requested_video: Callable[[Any, str, str, int, str], str | None] | None = None


@dataclass(frozen=True)
class QueueGuardrailSnapshot:
    attempts_24h: int
    recorded_cost_usd_24h: float
    recent_finished: int
    recent_failures: int
    reserved_cost_usd_24h: float = 0.0

    def as_dict(self) -> dict[str, int | float]:
        return {
            "attempts_24h": self.attempts_24h,
            "recorded_cost_usd_24h": round(self.recorded_cost_usd_24h, 6),
            "recent_finished": self.recent_finished,
            "recent_failures": self.recent_failures,
            "reserved_cost_usd_24h": round(self.reserved_cost_usd_24h, 6),
        }


def _uuid_argument(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a valid UUID") from exc
    if str(parsed) != value.casefold():
        raise argparse.ArgumentTypeError("must be a canonical UUID")
    return str(parsed)


def load_queue_guardrail_snapshot(db: Any, model: str, failure_window: int) -> QueueGuardrailSnapshot:
    row = (
        db.execute(
            text("""
            WITH attempts_24h AS (
                SELECT status, metrics, started_at, error
                FROM archive_extraction_runs
                WHERE model_name = :model
                  AND started_at >= now() - interval '24 hours'
            ),
            recent_finished AS (
                SELECT status
                FROM attempts_24h
                WHERE status IN ('completed', 'failed')
                  AND started_at >= COALESCE((SELECT max(created_at) FROM archive_enrichment_recoveries
                    WHERE model=:model AND prompt=:prompt),'-infinity'::timestamptz)
                  AND NOT ((status='failed' AND error='enrichment window contains no transcript blocks'
                    AND metrics->'input_preflight_reconciliation'->>'reason'='empty_balanced_window'
                    AND metrics->'input_preflight_reconciliation'->>'version'='1'
                    AND NOT (metrics ?| ARRAY['provider','cost_usd','prompt_tokens','completion_tokens'])) IS TRUE)
                ORDER BY started_at DESC
                LIMIT :failure_window
            )
            SELECT
                (SELECT COUNT(*) FROM attempts_24h) AS attempts_24h,
                (SELECT COALESCE(SUM(
                    CASE
                        WHEN jsonb_typeof(metrics -> 'cost_usd') = 'number'
                        THEN (metrics ->> 'cost_usd')::numeric
                        ELSE 0
                    END
                ), 0) FROM attempts_24h) AS recorded_cost_usd_24h,
                (SELECT COALESCE(SUM(CASE
                        WHEN jsonb_typeof(metrics -> 'cost_reservation_usd') = 'number'
                        THEN (metrics ->> 'cost_reservation_usd')::numeric
                        ELSE 0
                    END
                ), 0) FROM attempts_24h) AS reserved_cost_usd_24h,
                (SELECT COUNT(*) FROM recent_finished) AS recent_finished,
                (SELECT COUNT(*) FROM recent_finished WHERE status = 'failed') AS recent_failures
        """),
            {"model": model, "prompt": PROMPT_VERSION, "failure_window": failure_window},
        )
        .mappings()
        .one()
    )
    return QueueGuardrailSnapshot(
        attempts_24h=int(row["attempts_24h"]),
        recorded_cost_usd_24h=float(row["recorded_cost_usd_24h"]),
        recent_finished=int(row["recent_finished"]),
        recent_failures=int(row["recent_failures"]),
        reserved_cost_usd_24h=float(row["reserved_cost_usd_24h"]),
    )


def evaluate_queue_guardrails(
    snapshot: QueueGuardrailSnapshot,
    *,
    max_attempts_24h: int,
    max_cost_usd_24h: float,
    failure_window: int,
    max_failure_rate: float,
) -> dict[str, Any] | None:
    details = snapshot.as_dict()
    if snapshot.attempts_24h >= max_attempts_24h:
        return {"status": "guardrail_halted", "reason": "attempt_limit_24h", "guardrails": details}
    if snapshot.recorded_cost_usd_24h + snapshot.reserved_cost_usd_24h >= max_cost_usd_24h:
        return {"status": "guardrail_halted", "reason": "cost_limit_24h", "guardrails": details}
    if snapshot.recent_finished >= failure_window:
        failure_rate = snapshot.recent_failures / snapshot.recent_finished
        details["recent_failure_rate"] = round(failure_rate, 6)
        if failure_rate >= max_failure_rate:
            return {"status": "guardrail_halted", "reason": "failure_rate", "guardrails": details}
    return None


def select_next_video(db: Any, model: str, prompt_version: str, failure_cooldown_seconds: int) -> str | None:
    selected = db.execute(
        text("""
            SELECT CAST(v.id AS text)
            FROM videos AS v
            WHERE v.state = 'completed'
              AND COALESCE(v.duration_seconds, 0) > 0
              AND EXISTS (
                  SELECT 1 FROM transcript_blocks AS tb WHERE tb.video_id = v.id
                  UNION ALL
                  SELECT 1 FROM segments AS s WHERE s.video_id = v.id
                  UNION ALL
                  SELECT 1
                  FROM youtube_transcripts AS yt
                  JOIN youtube_segments AS ys ON ys.youtube_transcript_id = yt.id
                  WHERE yt.video_id = v.id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM archive_video_chapters AS moderated
                  WHERE moderated.video_id = v.id
                    AND (moderated.status <> 'candidate' OR moderated.source <> 'automatic')
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM archive_video_chapters AS current
                  WHERE current.video_id = v.id
                    AND current.model_name = :model
                    AND current.prompt_version = :prompt
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM archive_extraction_runs AS recent
                  WHERE recent.video_id = v.id
                    AND recent.model_name = :model
                    AND recent.status IN ('running', 'failed')
                    AND recent.started_at > now() - make_interval(secs => :failure_cooldown_seconds)
              )
            ORDER BY v.uploaded_at DESC NULLS LAST, v.created_at DESC, v.id
            LIMIT 1
        """),
        {
            "model": model,
            "prompt": prompt_version,
            "failure_cooldown_seconds": failure_cooldown_seconds,
        },
    ).scalar_one_or_none()
    return str(selected) if selected is not None else None


def select_requested_video(
    db: Any,
    model: str,
    prompt_version: str,
    failure_cooldown_seconds: int,
    video_id: str,
) -> str | None:
    """Select one pristine, explicitly requested video without replacing prior review work."""
    selected = db.execute(
        text("""
            SELECT CAST(v.id AS text)
            FROM videos AS v
            WHERE v.id = CAST(:video_id AS uuid)
              AND v.state = 'completed'
              AND COALESCE(v.duration_seconds, 0) > 0
              AND EXISTS (
                  SELECT 1 FROM transcript_blocks AS tb WHERE tb.video_id = v.id
                  UNION ALL
                  SELECT 1 FROM segments AS s WHERE s.video_id = v.id
                  UNION ALL
                  SELECT 1
                  FROM youtube_transcripts AS yt
                  JOIN youtube_segments AS ys ON ys.youtube_transcript_id = yt.id
                  WHERE yt.video_id = v.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM archive_video_chapters AS chapter WHERE chapter.video_id = v.id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM archive_label_assignments AS assignment
                  WHERE assignment.video_id = v.id AND assignment.source = 'llm'
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM archive_extraction_runs AS recent
                  WHERE recent.video_id = v.id
                    AND recent.model_name = :model
                    AND recent.prompt_version = :prompt
                    AND recent.status IN ('running', 'failed')
                    AND recent.started_at > now() - make_interval(secs => :failure_cooldown_seconds)
              )
            LIMIT 1
        """),
        {
            "video_id": video_id,
            "model": model,
            "prompt": prompt_version,
            "failure_cooldown_seconds": failure_cooldown_seconds,
        },
    ).scalar_one_or_none()
    return str(selected) if selected is not None else None


def mark_credit_exhausted_run(db: Any, video_id: str, model: str) -> None:
    db.execute(
        text("""
            UPDATE archive_extraction_runs
            SET status = 'cancelled',
                metrics = COALESCE(metrics, '{}'::jsonb) || jsonb_build_object('reason', 'credit_exhausted'),
                error = 'OpenRouter credits exhausted',
                finished_at = COALESCE(finished_at, now())
            WHERE id = (
                SELECT id
                FROM archive_extraction_runs
                WHERE video_id = :video_id
                  AND model_name = :model
                  AND status = 'failed'
                ORDER BY started_at DESC
                LIMIT 1
            )
        """),
        {"video_id": video_id, "model": model},
    )
    db.commit()


def is_credit_exhaustion_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    while current is not None:
        message = str(current).casefold()
        if "http 402" in message or "insufficient credits" in message or "response error code 402" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


def run_queue_cycle(
    db: Any,
    *,
    model: str,
    prompt_version: str,
    failure_cooldown_seconds: int,
    dependencies: QueueDependencies,
    requested_video_id: str | None = None,
) -> dict[str, Any]:
    if requested_video_id is None:
        video_id = dependencies.select_video(db, model, prompt_version, failure_cooldown_seconds)
    else:
        if dependencies.select_requested_video is None:
            raise RuntimeError("requested-video selector is unavailable")
        video_id = dependencies.select_requested_video(
            db,
            model,
            prompt_version,
            failure_cooldown_seconds,
            requested_video_id,
        )
    if video_id is None:
        if requested_video_id is not None:
            return {"status": "ineligible", "video_id": requested_video_id}
        return {"status": "idle"}
    try:
        metrics = dependencies.enrich_video(db, video_id)
    except Exception as exc:
        failure_metrics = getattr(exc, "archive_enrichment_failure_metrics", None)
        if is_credit_exhaustion_error(exc):
            if dependencies.on_credit_exhausted is not None:
                dependencies.on_credit_exhausted(db, video_id, model)
            result: dict[str, Any] = {"status": "credit_exhausted", "video_id": video_id}
            if isinstance(failure_metrics, dict):
                result["metrics"] = failure_metrics
            return result
        result = {"status": "failed", "video_id": video_id, "error": str(exc)[:500]}
        if str(exc).startswith(
            ("OpenRouter request failed:", "OpenRouter request outcome uncertain:", "OpenRouter rate limit requires")
        ):
            result["reason"] = "provider_failure"
        if isinstance(failure_metrics, dict):
            result["metrics"] = failure_metrics
        return result
    return {"status": "completed", "video_id": video_id, "metrics": metrics}


def main(
    argv: Sequence[str] | None = None,
    *,
    config: Any = settings,
    dependencies: QueueDependencies | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    # Retain an actual checked-out connection: a pooled Session alone would
    # release/reassign a session advisory lock at commit boundaries.
    arguments = list(argv) if argv is not None else sys.argv[1:]
    if (
        dependencies is None
        and "--queue-status" not in arguments
        and (
            config.ARCHIVE_ENRICHMENT_ENABLED
            or "--requeue-run" in arguments
            or "--resume-queue" in arguments
            or "--reconcile-input-run" in arguments
        )
    ):
        with engine.connect() as connection:
            acquired = connection.execute(
                text("SELECT pg_try_advisory_lock(hashtext(:owner))"), {"owner": OWNER_LOCK}
            ).scalar_one()
            connection.commit()
            if not acquired:
                print(json.dumps({"status": "guardrail_halted", "reason": "queue_owner_busy"}))
                return 1
            try:
                return _main(argv, config=config, sleeper=sleeper, session_factory=lambda: Session(bind=connection))
            finally:
                connection.rollback()
                connection.execute(text("SELECT pg_advisory_unlock(hashtext(:owner))"), {"owner": OWNER_LOCK})
                connection.commit()
    return _main(argv, config=config, dependencies=dependencies, sleeper=sleeper)


def _main(
    argv: Sequence[str] | None = None,
    *,
    config: Any = settings,
    dependencies: QueueDependencies | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    session_factory: Callable[[], Any] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Continuously generate review-only archive enrichment candidates.")
    parser.add_argument("--once", action="store_true", help="Process at most one queue item and exit.")
    parser.add_argument("--continuous", action="store_true", help="Use the durable priority/retry queue.")
    parser.add_argument(
        "--requeue-run", type=_uuid_argument, help="Preserve and requeue a technical rejection; no provider call."
    )
    parser.add_argument("--queue-status", action="store_true", help="Read durable queue state without claiming work.")
    parser.add_argument(
        "--reconcile-input-run", type=_uuid_argument, help="Audit a proven unpaid empty-window failure."
    )
    parser.add_argument(
        "--resume-queue", action="store_true", help="Clear an operator-reviewed pause; no provider call."
    )
    parser.add_argument("--video-id", type=_uuid_argument, help="Process exactly one eligible video UUID.")
    args = parser.parse_args(argv)
    if args.video_id is not None and not args.once:
        parser.error("--video-id requires --once")
    if args.continuous and (args.once or args.video_id):
        parser.error("--continuous cannot be combined with --once or --video-id")
    if args.requeue_run or args.queue_status or args.resume_queue or args.reconcile_input_run:
        if not args.once or args.continuous or args.video_id:
            parser.error("queue maintenance requires --once and cannot select a video or continuous mode")
        if (
            sum(
                bool(value)
                for value in (args.requeue_run, args.queue_status, args.resume_queue, args.reconcile_input_run)
            )
            != 1
        ):
            parser.error("select exactly one queue maintenance operation")
        db = (session_factory or SessionLocal)()
        try:
            if args.reconcile_input_run:
                maintenance = reconcile_input_run(db, config.ARCHIVE_ENRICHMENT_MODEL, args.reconcile_input_run)
            elif args.requeue_run:
                maintenance = requeue_run(db, config.ARCHIVE_ENRICHMENT_MODEL, args.requeue_run)
            elif args.resume_queue:
                maintenance = resume_queue(db, config.ARCHIVE_ENRICHMENT_MODEL)
            else:
                maintenance = queue_status(db, config.ARCHIVE_ENRICHMENT_MODEL)
            print(json.dumps(maintenance, sort_keys=True))
            return 0
        finally:
            db.close()
    deps = dependencies or QueueDependencies(
        select_video=select_next_video,
        enrich_video=enrich_video_candidates,
        on_credit_exhausted=mark_credit_exhausted_run,
        load_guardrail_snapshot=load_queue_guardrail_snapshot,
        select_requested_video=select_requested_video,
    )

    stopping = False

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True

    if args.continuous:
        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)

    while not stopping:
        if not config.ARCHIVE_ENRICHMENT_ENABLED:
            result = {"status": "disabled"}
        else:
            db = (session_factory or SessionLocal)()
            try:
                result = None
                if args.continuous:
                    discover_jobs(db, config.ARCHIVE_ENRICHMENT_MODEL)
                if deps.load_guardrail_snapshot is not None:
                    failure_window = int(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_FAILURE_WINDOW", 20))
                    snapshot = deps.load_guardrail_snapshot(db, config.ARCHIVE_ENRICHMENT_MODEL, failure_window)
                    result = evaluate_queue_guardrails(
                        snapshot,
                        max_attempts_24h=int(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_MAX_ATTEMPTS_PER_24H", 20)),
                        max_cost_usd_24h=float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_MAX_COST_USD_PER_24H", 5.0)),
                        failure_window=failure_window,
                        max_failure_rate=float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_MAX_FAILURE_RATE", 0.25)),
                    )
                if result is not None and args.continuous and result.get("reason") == "failure_rate":
                    pause_queue(db, config.ARCHIVE_ENRICHMENT_MODEL, "failure_rate")
                if result is None and args.continuous:
                    result = next_job(
                        db,
                        config.ARCHIVE_ENRICHMENT_MODEL,
                        int(getattr(config, "ARCHIVE_ENRICHMENT_MAX_WINDOW_MINUTES", 90) * 60_000),
                    )
                    if result["status"] == "selected":
                        selected = str(result["video_id"])
                        continuous_deps = QueueDependencies(
                            select_video=lambda *_args, selected=selected: selected,
                            enrich_video=deps.enrich_video,
                            on_credit_exhausted=deps.on_credit_exhausted,
                        )
                        result = run_queue_cycle(
                            db,
                            model=config.ARCHIVE_ENRICHMENT_MODEL,
                            prompt_version=PROMPT_VERSION,
                            failure_cooldown_seconds=0,
                            dependencies=continuous_deps,
                        )
                        finish_job(db, config.ARCHIVE_ENRICHMENT_MODEL, selected, result)
                elif result is None:
                    result = run_queue_cycle(
                        db,
                        model=config.ARCHIVE_ENRICHMENT_MODEL,
                        prompt_version=PROMPT_VERSION,
                        failure_cooldown_seconds=config.ARCHIVE_ENRICHMENT_QUEUE_FAILURE_COOLDOWN_SECONDS,
                        dependencies=deps,
                        requested_video_id=args.video_id,
                    )
            finally:
                db.close()
        assert result is not None
        print(json.dumps(result, sort_keys=True), flush=True)
        if stopping:
            return 0
        if args.once:
            if args.video_id is not None and result["status"] != "completed":
                return 1
            return 0

        delay_by_status = {
            "input_parked": float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_SUCCESS_DELAY_SECONDS", 5)),
            "completed": float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_SUCCESS_DELAY_SECONDS", 5)),
            "failed": float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_FAILURE_DELAY_SECONDS", 30)),
            "idle": float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_POLL_SECONDS", 300)),
            "disabled": float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_POLL_SECONDS", 300)),
            "credit_exhausted": float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_CREDIT_COOLDOWN_SECONDS", 3600)),
            "guardrail_halted": float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_POLL_SECONDS", 300)),
            "paused": float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_POLL_SECONDS", 300)),
        }
        sleeper(delay_by_status[result["status"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "QueueDependencies",
    "QueueGuardrailSnapshot",
    "evaluate_queue_guardrails",
    "is_credit_exhaustion_error",
    "load_queue_guardrail_snapshot",
    "main",
    "mark_credit_exhausted_run",
    "run_queue_cycle",
    "select_next_video",
    "select_requested_video",
]
