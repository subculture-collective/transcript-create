#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.enrichment_service import enrich_video_candidates
from app.archive.openrouter_enrichment import PROMPT_VERSION
from app.db import SessionLocal
from app.settings import settings


@dataclass(frozen=True)
class QueueDependencies:
    select_video: Callable[[Any, str, str, int], str | None]
    enrich_video: Callable[[Any, str], dict[str, Any]]
    on_credit_exhausted: Callable[[Any, str, str], None] | None = None
    load_guardrail_snapshot: Callable[[Any, str, int], "QueueGuardrailSnapshot"] | None = None


@dataclass(frozen=True)
class QueueGuardrailSnapshot:
    attempts_24h: int
    recorded_cost_usd_24h: float
    recent_finished: int
    recent_failures: int

    def as_dict(self) -> dict[str, int | float]:
        return {
            "attempts_24h": self.attempts_24h,
            "recorded_cost_usd_24h": round(self.recorded_cost_usd_24h, 6),
            "recent_finished": self.recent_finished,
            "recent_failures": self.recent_failures,
        }


def load_queue_guardrail_snapshot(db: Any, model: str, failure_window: int) -> QueueGuardrailSnapshot:
    row = (
        db.execute(
            text("""
            WITH attempts_24h AS (
                SELECT status, metrics, started_at
                FROM archive_extraction_runs
                WHERE model_name = :model
                  AND started_at >= now() - interval '24 hours'
            ),
            recent_finished AS (
                SELECT status
                FROM attempts_24h
                WHERE status IN ('completed', 'failed')
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
                (SELECT COUNT(*) FROM recent_finished) AS recent_finished,
                (SELECT COUNT(*) FROM recent_finished WHERE status = 'failed') AS recent_failures
        """),
            {"model": model, "failure_window": failure_window},
        )
        .mappings()
        .one()
    )
    return QueueGuardrailSnapshot(
        attempts_24h=int(row["attempts_24h"]),
        recorded_cost_usd_24h=float(row["recorded_cost_usd_24h"]),
        recent_finished=int(row["recent_finished"]),
        recent_failures=int(row["recent_failures"]),
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
    if snapshot.recorded_cost_usd_24h >= max_cost_usd_24h:
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


def mark_credit_exhausted_run(db: Any, video_id: str, model: str) -> None:
    db.execute(
        text("""
            UPDATE archive_extraction_runs
            SET status = 'cancelled',
                metrics = jsonb_build_object('reason', 'credit_exhausted'),
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
        if "http 402" in message or "insufficient credits" in message:
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
) -> dict[str, Any]:
    video_id = dependencies.select_video(db, model, prompt_version, failure_cooldown_seconds)
    if video_id is None:
        return {"status": "idle"}
    try:
        metrics = dependencies.enrich_video(db, video_id)
    except Exception as exc:
        if is_credit_exhaustion_error(exc):
            if dependencies.on_credit_exhausted is not None:
                dependencies.on_credit_exhausted(db, video_id, model)
            return {"status": "credit_exhausted", "video_id": video_id}
        return {"status": "failed", "video_id": video_id, "error": str(exc)[:500]}
    return {"status": "completed", "video_id": video_id, "metrics": metrics}


def main(
    argv: Sequence[str] | None = None,
    *,
    config: Any = settings,
    dependencies: QueueDependencies | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    parser = argparse.ArgumentParser(description="Continuously generate review-only archive enrichment candidates.")
    parser.add_argument("--once", action="store_true", help="Process at most one queue item and exit.")
    args = parser.parse_args(argv)
    deps = dependencies or QueueDependencies(
        select_video=select_next_video,
        enrich_video=enrich_video_candidates,
        on_credit_exhausted=mark_credit_exhausted_run,
        load_guardrail_snapshot=load_queue_guardrail_snapshot,
    )

    while True:
        if not config.ARCHIVE_ENRICHMENT_ENABLED:
            result = {"status": "disabled"}
        else:
            db = SessionLocal()
            try:
                result = None
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
                if result is None:
                    result = run_queue_cycle(
                        db,
                        model=config.ARCHIVE_ENRICHMENT_MODEL,
                        prompt_version=PROMPT_VERSION,
                        failure_cooldown_seconds=config.ARCHIVE_ENRICHMENT_QUEUE_FAILURE_COOLDOWN_SECONDS,
                        dependencies=deps,
                    )
            finally:
                db.close()
        assert result is not None
        print(json.dumps(result, sort_keys=True), flush=True)
        if args.once:
            return 0

        delay_by_status = {
            "completed": float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_SUCCESS_DELAY_SECONDS", 5)),
            "failed": float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_FAILURE_DELAY_SECONDS", 30)),
            "idle": float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_POLL_SECONDS", 300)),
            "disabled": float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_POLL_SECONDS", 300)),
            "credit_exhausted": float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_CREDIT_COOLDOWN_SECONDS", 3600)),
            "guardrail_halted": float(getattr(config, "ARCHIVE_ENRICHMENT_QUEUE_POLL_SECONDS", 300)),
        }
        sleeper(delay_by_status[result["status"]])


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
]
