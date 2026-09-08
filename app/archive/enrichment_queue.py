"""Durable scheduling. Call under the queue's connection-scoped owner lock.

No provider calls occur here. Database state survives process/container restarts.
Uncertain running attempts are never automatically replayed.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from .enrichment_preflight import IneligibleEnrichmentInputError, preflight_video
from .openrouter_enrichment import PROMPT_VERSION

# A single owner across prompts/models and one-shot CLI invocations. A dedicated
# connection must retain this session lock across commits and HTTP requests.
OWNER_LOCK = "hasanara-archive-enrichment-owner-v1"
MAX_ATTEMPTS = 3

# Exact local validation failures, never provider messages or arbitrary prefixes.
# These still consume paid attempt budgets and must pass validation on retry.
HANDLED_QUALITY_ERRORS = (
    "archive enrichment chapter evidence does not overlap its chapter",
    "archive enrichment quality gate: unsupported chapter evidence",
    "archive enrichment quality gate: no sustained categories",
    "Published chapters must be at least 30 seconds long",
)

PRISTINE_SQL = """
    v.state = 'completed' AND COALESCE(v.duration_seconds, 0) > 0
    AND COALESCE(v.title,'') NOT ILIKE '%NO STREAM TODAY%'
    AND EXISTS (
        SELECT 1 FROM transcript_blocks tb WHERE tb.video_id=v.id
        UNION ALL SELECT 1 FROM segments s WHERE s.video_id=v.id
        UNION ALL SELECT 1 FROM youtube_transcripts yt
          JOIN youtube_segments ys ON ys.youtube_transcript_id=yt.id WHERE yt.video_id=v.id
    )
    AND NOT EXISTS (SELECT 1 FROM archive_video_chapters c WHERE c.video_id=v.id)
    AND NOT EXISTS (SELECT 1 FROM archive_label_assignments a
                    WHERE a.video_id=v.id AND a.source='llm')
    AND NOT EXISTS (SELECT 1 FROM archive_chapter_feedback f WHERE f.video_id=v.id
        AND NOT EXISTS (SELECT 1 FROM archive_enrichment_maintenance_rows m
            WHERE m.table_name='archive_chapter_feedback' AND m.row_id=f.id::text))
"""


def params(model: str) -> dict[str, Any]:
    return {"model": model, "prompt": PROMPT_VERSION, "max_attempts": MAX_ATTEMPTS}


def discover_jobs(db: Any, model: str) -> int:
    """First scan is backfill; later discoveries are priority arrivals."""
    values = params(model)
    initialized = db.execute(
        text("""
            INSERT INTO archive_enrichment_queue_state(model,prompt) VALUES (:model,:prompt)
            ON CONFLICT DO NOTHING RETURNING initialized_at
        """),
        values,
    ).scalar_one_or_none()
    values["new_arrival"] = initialized is None
    # Historical failures consume the same retry allowance. Credit exhaustion is
    # a global pause, not a bad-video attempt. Existing running work is fenced by
    # next_job before any new provider request.
    result = db.execute(
        text(f"""
            INSERT INTO archive_enrichment_jobs
                (video_id,model,prompt,new_arrival,attempts,status,available_at)
            SELECT v.id,:model,:prompt,(:new_arrival AND NOT EXISTS (
                       SELECT 1 FROM archive_enrichment_maintenance_rows m
                       WHERE m.table_name IN ('archive_video_chapters','archive_label_assignments')
                         AND m.row_data->>'video_id'=v.id::text)),h.failures,
                   CASE WHEN h.failures>=:max_attempts THEN 'parked'
                        WHEN h.failures>0 THEN 'retry' ELSE 'pending' END,
                   COALESCE(h.last_failure + interval '1 hour',now())
              FROM videos v
              CROSS JOIN LATERAL (
                SELECT count(*)::integer failures,max(r.finished_at) last_failure
                  FROM archive_extraction_runs r WHERE r.video_id=v.id
                  AND r.model_name=:model AND r.prompt_version=:prompt AND r.status='failed'
              ) h
             WHERE NOT EXISTS (SELECT 1 FROM archive_enrichment_jobs j
                 WHERE j.video_id=v.id AND j.model=:model AND j.prompt=:prompt)
               AND {PRISTINE_SQL}
            ON CONFLICT DO NOTHING
        """),
        values,
    )
    db.commit()
    return int(result.rowcount)


def pause_queue(db: Any, model: str, reason: str) -> None:
    db.execute(
        text("""
            UPDATE archive_enrichment_queue_state SET paused_reason=:reason
             WHERE model=:model AND prompt=:prompt
        """),
        {**params(model), "reason": reason},
    )
    db.commit()


def reconcile_input_run(db: Any, model: str, run_id: str) -> dict[str, Any]:
    """Operator-only classification of proven pre-provider input failures.

    Keep failed status, all original metrics, attempt count and run reference.
    The marker affects only the provider failure-rate sample, never spend totals.
    Caller must hold OWNER_LOCK and stop the worker before invoking this.
    """
    values = {**params(model), "run_id": run_id}
    if db.execute(text("SELECT EXISTS(SELECT 1 FROM archive_enrichment_jobs WHERE status='running')")).scalar_one():
        raise ValueError("stop and reconcile running work first")
    row = (
        db.execute(
            text("""
        SELECT r.video_id,r.status,r.error,r.metrics FROM archive_extraction_runs r
        WHERE r.id=:run_id AND r.model_name=:model AND r.prompt_version=:prompt FOR UPDATE
    """),
            values,
        )
        .mappings()
        .one()
    )
    metrics = row["metrics"] or {}
    if row["status"] != "failed" or row["error"] != "enrichment window contains no transcript blocks":
        raise ValueError("only proven empty-window failures may be reconciled")
    if set(metrics) - {"model", "run_id", "prompt_version", "input_preflight_reconciliation"}:
        raise ValueError("provider usage or unknown metrics prohibit input reconciliation")
    values["video_id"] = row["video_id"]
    job = (
        db.execute(
            text("""
        SELECT status,last_run_id FROM archive_enrichment_jobs
        WHERE video_id=:video_id AND model=:model AND prompt=:prompt FOR UPDATE
    """),
            values,
        )
        .mappings()
        .one()
    )
    if job["status"] not in ("retry", "parked") or str(job["last_run_id"]) != run_id:
        raise ValueError("run is not the latest inactive queue attempt")
    if not db.execute(text(f"SELECT ({PRISTINE_SQL}) FROM videos v WHERE id=:video_id"), values).scalar_one():
        raise ValueError("existing review work is protected")
    try:
        preflight_video(db, str(row["video_id"]), 5_400_000)
    except IneligibleEnrichmentInputError as exc:
        if str(exc) != "empty_balanced_window":
            raise ValueError("historical input defect no longer reproduces") from exc
    else:
        raise ValueError("historical input defect no longer reproduces")
    db.execute(
        text("""
        UPDATE archive_extraction_runs
        SET metrics=COALESCE(metrics,'{}'::jsonb) || jsonb_build_object(
            'input_preflight_reconciliation', COALESCE(metrics->'input_preflight_reconciliation',
            jsonb_build_object('reason','empty_balanced_window','version',1,'reconciled_at',now())))
        WHERE id=:run_id
    """),
        values,
    )
    db.execute(
        text("""
        UPDATE archive_enrichment_jobs SET status='parked',reason='transcript_input:empty_balanced_window',updated_at=now()
        WHERE video_id=:video_id AND model=:model AND prompt=:prompt
    """),
        values,
    )
    db.commit()
    return {"status": "input_reconciled", "run_id": run_id, "video_id": str(row["video_id"])}


def resume_queue(db: Any, model: str) -> dict[str, Any]:
    """Explicit operator action, under OWNER_LOCK, after fixing the pause cause."""
    if db.execute(text("""
        SELECT EXISTS (SELECT 1 FROM archive_enrichment_jobs WHERE status='running')
            OR EXISTS (SELECT 1 FROM archive_extraction_runs WHERE status='running' AND model_name IS NOT NULL)
    """)).scalar_one():
        raise ValueError("uncertain running work must be reconciled before resuming")
    previous = db.execute(
        text(
            "SELECT paused_reason FROM archive_enrichment_queue_state WHERE model=:model AND prompt=:prompt FOR UPDATE"
        ),
        params(model),
    ).scalar_one_or_none()
    if not previous:
        raise ValueError("queue must be paused before explicit recovery")
    recovery = db.execute(
        text("""
        INSERT INTO archive_enrichment_recoveries(model,prompt,previous_reason)
        VALUES (:model,:prompt,:reason) RETURNING id
    """),
        {**params(model), "reason": previous},
    ).scalar_one()
    row = db.execute(
        text("""
        UPDATE archive_enrichment_queue_state SET paused_reason=NULL
        WHERE model=:model AND prompt=:prompt RETURNING initialized_at
    """),
        params(model),
    ).scalar_one_or_none()
    if row is None:
        raise ValueError("queue has not been initialized")
    db.commit()
    return {"status": "resumed", "model": model, "prompt": PROMPT_VERSION, "recovery_id": str(recovery)}


def queue_status(db: Any, model: str) -> dict[str, Any]:
    state = (
        db.execute(
            text("SELECT paused_reason FROM archive_enrichment_queue_state WHERE model=:model AND prompt=:prompt"),
            params(model),
        )
        .mappings()
        .one_or_none()
    )
    counts = (
        db.execute(
            text("""
        SELECT status,count(*) count FROM archive_enrichment_jobs
        WHERE model=:model AND prompt=:prompt GROUP BY status
    """),
            params(model),
        )
        .mappings()
        .all()
    )
    return {
        "status": "uninitialized" if state is None else "paused" if state["paused_reason"] else "ready",
        "reason": state["paused_reason"] if state else None,
        "jobs": {row["status"]: row["count"] for row in counts},
    }


def next_job(db: Any, model: str, max_window_ms: int = 5_400_000) -> dict[str, Any]:
    values = params(model)
    paused = db.execute(
        text("SELECT paused_reason FROM archive_enrichment_queue_state WHERE model=:model AND prompt=:prompt"),
        values,
    ).scalar_one()
    recovery_video = None
    if paused == "provider_cooldown":
        recovery = (
            db.execute(
                text("""
            SELECT j.video_id,j.available_at<=now() AS due FROM archive_enrichment_jobs j
            JOIN archive_extraction_runs r ON r.id=j.last_run_id
            WHERE j.model=:model AND j.prompt=:prompt AND j.status='retry'
              AND j.reason='provider_failure' AND j.attempts<:max_attempts
              AND r.status='failed' AND r.video_id=j.video_id
              AND r.model_name=j.model AND r.prompt_version=j.prompt
              AND r.id=(SELECT id FROM archive_extraction_runs
                        WHERE model_name=:model AND prompt_version=:prompt
                        ORDER BY started_at DESC,id DESC LIMIT 1)
              AND r.metrics->'provider_failure'->>'transient'='true'
            ORDER BY r.started_at DESC LIMIT 1
        """),
                values,
            )
            .mappings()
            .one_or_none()
        )
        if recovery is None:
            pause_queue(db, model, "provider_failure")
            return {"status": "paused", "reason": "provider_failure"}
        if not recovery["due"]:
            return {"status": "paused", "reason": paused}
        recovery_video = str(recovery["video_id"])
    elif paused:
        return {"status": "paused", "reason": paused}
    uncertain = db.execute(text("""
            SELECT EXISTS (SELECT 1 FROM archive_extraction_runs WHERE status='running'
                           AND model_name IS NOT NULL)
                OR EXISTS (SELECT 1 FROM archive_enrichment_jobs WHERE status='running')
        """)).scalar_one()
    if uncertain:
        pause_queue(db, model, "interrupted_or_external_run")
        return {"status": "paused", "reason": "interrupted_or_external_run"}
    values["recovery_video"] = recovery_video
    # A human may have acted after discovery. Park, never overwrite that work.
    db.execute(
        text(f"""
            UPDATE archive_enrichment_jobs j SET status='parked',reason='no_longer_pristine',updated_at=now()
            FROM videos v WHERE v.id=j.video_id AND j.model=:model AND j.prompt=:prompt
              AND j.status IN ('pending','retry') AND NOT ({PRISTINE_SQL})
        """),
        values,
    )
    row = (
        db.execute(
            text("""
            SELECT j.video_id,j.attempts FROM archive_enrichment_jobs j
            JOIN videos v ON v.id=j.video_id
            WHERE j.model=:model AND j.prompt=:prompt AND j.status IN ('pending','retry')
              AND j.available_at<=now() AND j.attempts<:max_attempts
              AND (CAST(:recovery_video AS uuid) IS NULL OR j.video_id=CAST(:recovery_video AS uuid))
            ORDER BY CASE WHEN j.status='retry' THEN 2 WHEN j.new_arrival THEN 0 ELSE 1 END,
                     v.uploaded_at DESC NULLS LAST,v.created_at DESC,v.id
            LIMIT 1 FOR UPDATE OF j SKIP LOCKED
        """),
            values,
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        if recovery_video is not None:
            pause_queue(db, model, "provider_failure")
            return {"status": "paused", "reason": "provider_failure"}
        db.commit()
        return {"status": "idle"}
    video_id = str(row["video_id"])
    try:
        preflight_video(db, video_id, max_window_ms)
    except IneligibleEnrichmentInputError as exc:
        reason = f"transcript_input:{exc}"
        db.execute(
            text("""
                UPDATE archive_enrichment_jobs SET status='parked',reason=:reason,updated_at=now()
                 WHERE video_id=:video_id AND model=:model AND prompt=:prompt
            """),
            {**values, "video_id": video_id, "reason": reason},
        )
        db.commit()
        return {"status": "input_parked", "video_id": video_id, "reason": reason}
    db.execute(
        text("""
            UPDATE archive_enrichment_jobs SET status='running',attempts=attempts+1,updated_at=now()
             WHERE video_id=:video_id AND model=:model AND prompt=:prompt
        """),
        {**values, "video_id": video_id},
    )
    db.commit()
    return {"status": "selected", "video_id": video_id, "attempt": row["attempts"] + 1}


def finish_job(db: Any, model: str, video_id: str, outcome: dict[str, Any]) -> None:
    """A quality failure retries; credit exhaustion persists a global pause."""
    status = outcome["status"]
    reason = None if status == "completed" else outcome.get("reason", status)
    if status == "failed" and reason == "failed" and outcome.get("metrics", {}).get("run_id"):
        quality_rejection = db.execute(
            text("""
                SELECT EXISTS (SELECT 1 FROM archive_extraction_runs
                WHERE id=CAST(:run_id AS uuid) AND video_id=:video_id
                  AND model_name=:model AND prompt_version=:prompt AND status='failed'
                  AND error=ANY(:quality_errors))
            """),
            {
                **params(model),
                "video_id": video_id,
                "run_id": outcome["metrics"]["run_id"],
                "quality_errors": list(HANDLED_QUALITY_ERRORS),
            },
        ).scalar_one()
        if quality_rejection:
            reason = "quality_rejected"
    updated = db.execute(
        text("""
            UPDATE archive_enrichment_jobs
               SET status=CASE WHEN :outcome='completed' THEN 'completed'
                               WHEN :outcome='credit_exhausted' THEN 'retry'
                               WHEN attempts>=:max_attempts THEN 'parked' ELSE 'retry' END,
                   attempts=attempts-CASE WHEN :outcome='credit_exhausted' THEN 1 ELSE 0 END,
                   available_at=now()+CASE WHEN attempts<=1 THEN interval '15 minutes' ELSE interval '1 hour' END,
                   last_run_id=CAST(:run_id AS uuid),reason=:reason,updated_at=clock_timestamp()
             WHERE video_id=:video_id AND model=:model AND prompt=:prompt AND status='running'
        """),
        {
            **params(model),
            "video_id": video_id,
            "outcome": status,
            "run_id": outcome.get("metrics", {}).get("run_id"),
            "reason": reason,
        },
    )
    if updated.rowcount != 1:
        db.rollback()
        pause_queue(db, model, "queue_state_conflict")
        raise RuntimeError("queue attempt state changed unexpectedly")
    paused = db.execute(
        text("SELECT paused_reason FROM archive_enrichment_queue_state WHERE model=:model AND prompt=:prompt"),
        params(model),
    ).scalar_one()
    if paused == "provider_cooldown":
        # A recovery probe is a normal counted extraction, never a history reset.
        if status == "completed":
            db.execute(
                text(
                    "UPDATE archive_enrichment_queue_state SET paused_reason=NULL WHERE model=:model AND prompt=:prompt"
                ),
                params(model),
            )
            db.commit()
        else:
            pause_queue(db, model, "credit_exhausted" if status == "credit_exhausted" else "provider_failure")
    elif outcome.get("reason") == "provider_failure":
        transient = outcome.get("metrics", {}).get("provider_failure", {}).get("transient") is True
        pause_queue(db, model, "provider_cooldown" if transient else "provider_failure")
    elif status == "credit_exhausted":
        # Commit the outcome and pause atomically. A restart must not slip
        # between recording exhausted credit and persisting its stop condition.
        pause_queue(db, model, "credit_exhausted")
    else:
        # Export/configuration failures can happen before an extraction run is
        # created. Include them in a durable systemic breaker rather than
        # silently consuming every video's retry allowance.
        recent = (
            db.execute(
                text("""
            SELECT status FROM archive_enrichment_jobs j WHERE model=:model AND prompt=:prompt
            AND (status='completed' OR (status IN ('retry','parked') AND reason='failed'))
            AND NOT EXISTS (SELECT 1 FROM archive_extraction_runs r
                WHERE r.id=j.last_run_id AND r.video_id=j.video_id
                  AND r.model_name=j.model AND r.prompt_version=j.prompt
                  AND r.status='failed' AND r.error=ANY(:quality_errors))
            AND updated_at >= COALESCE((SELECT max(created_at) FROM archive_enrichment_recoveries
                WHERE model=:model AND prompt=:prompt),'-infinity'::timestamptz)
            ORDER BY updated_at DESC,video_id LIMIT 3
        """),
                {**params(model), "quality_errors": list(HANDLED_QUALITY_ERRORS)},
            )
            .scalars()
            .all()
        )
        if len(recent) == 3 and all(outcome != "completed" for outcome in recent):
            pause_queue(db, model, "consecutive_failures")
            return
        db.commit()


def requeue_run(db: Any, model: str, run_id: str) -> dict[str, Any]:
    """Explicit technical requeue, retaining full candidate snapshots.

    Caller holds OWNER_LOCK. Never interpret an editorial rejection as a
    technical failure. Repeating this command does not reset an attempt budget.
    """
    values = {**params(model), "run_id": run_id}
    run = (
        db.execute(
            text("""
        SELECT video_id,status,metrics FROM archive_extraction_runs
        WHERE id=:run_id AND model_name=:model AND prompt_version=:prompt
        FOR UPDATE
    """),
            values,
        )
        .mappings()
        .one_or_none()
    )
    if not run:
        raise ValueError("requeue requires a run from the pinned model and prompt")
    existing = db.execute(
        text("SELECT 1 FROM archive_enrichment_supersessions WHERE run_id=:run_id"), values
    ).scalar_one_or_none()
    if existing:
        return {"status": "already_requeued", "run_id": run_id}
    metrics = run["metrics"] or {}
    overlap = metrics.get(
        "evidence_overlap_violations", metrics.get("repairs", {}).get("evidence_overlap_violations", 0)
    )
    if run["status"] != "failed" and not (run["status"] == "completed" and overlap > 0):
        raise ValueError("only failed runs or recorded automated evidence rejections may be requeued")
    values["video_id"] = str(run["video_id"])
    db.execute(text("SELECT id FROM videos WHERE id=:video_id FOR UPDATE"), values)
    active = db.execute(
        text("""
        SELECT EXISTS (SELECT 1 FROM archive_extraction_runs WHERE video_id=:video_id AND status='running')
            OR EXISTS (SELECT 1 FROM archive_enrichment_jobs WHERE video_id=:video_id AND status IN ('running','completed'))
            OR EXISTS (SELECT 1 FROM archive_enrichment_jobs WHERE video_id=:video_id
                       AND model=:model AND prompt=:prompt AND attempts>=:max_attempts)
    """),
        values,
    ).scalar_one()
    if active:
        raise ValueError("active, completed, or exhausted queue work prevents requeue")
    attempts = db.execute(
        text("""
        SELECT count(*) FROM archive_extraction_runs WHERE video_id=:video_id
        AND model_name=:model AND prompt_version=:prompt AND status IN ('completed','failed')
    """),
        values,
    ).scalar_one()
    if attempts >= MAX_ATTEMPTS:
        raise ValueError("technical retry attempt allowance is exhausted")
    if db.execute(
        text("SELECT EXISTS (SELECT 1 FROM archive_chapter_feedback WHERE video_id=:video_id)"), values
    ).scalar_one():
        raise ValueError("editorial feedback prevents automatic supersession")
    chapters = (
        db.execute(text("SELECT * FROM archive_video_chapters WHERE video_id=:video_id FOR UPDATE"), values)
        .mappings()
        .all()
    )
    assignments = (
        db.execute(
            text("SELECT * FROM archive_label_assignments WHERE video_id=:video_id AND source='llm' FOR UPDATE"), values
        )
        .mappings()
        .all()
    )
    for row in [*chapters, *assignments]:
        if str(row["run_id"]) != run_id or row["status"] != "candidate" or row["created_at"] != row["updated_at"]:
            raise ValueError("existing or edited review work prevents supersession")
    if any(row["source"] != "automatic" for row in chapters):
        raise ValueError("curated chapters prevent supersession")
    if db.execute(
        text("""
        SELECT EXISTS (SELECT 1 FROM archive_label_assignments a
                       JOIN archive_video_chapters c ON c.id=a.chapter_id
                       WHERE c.video_id=:video_id AND a.source<>'llm')
    """),
        values,
    ).scalar_one():
        raise ValueError("non-LLM chapter assignments prevent supersession")
    snapshot = {"chapters": [dict(row) for row in chapters], "assignments": [dict(row) for row in assignments]}
    db.execute(
        text("""
        INSERT INTO archive_enrichment_supersessions(run_id,video_id,reason,candidates)
        VALUES (:run_id,:video_id,'explicit_technical_requeue',CAST(:snapshot AS jsonb))
    """),
        {**values, "snapshot": json.dumps(snapshot, default=str)},
    )
    # Only rows just locked and verified above; their complete original values,
    # IDs and provenance remain in the append-only supersession record.
    db.execute(
        text("DELETE FROM archive_label_assignments WHERE video_id=:video_id AND run_id=:run_id AND source='llm'"),
        values,
    )
    db.execute(text("DELETE FROM archive_video_chapters WHERE video_id=:video_id AND run_id=:run_id"), values)
    db.execute(
        text("""
        INSERT INTO archive_enrichment_jobs(video_id,model,prompt,status,attempts,reason)
        SELECT :video_id,:model,:prompt,
               CASE WHEN count(*)>=:max_attempts THEN 'parked' ELSE 'retry' END,
               count(*)::integer,'explicit_technical_requeue'
        FROM archive_extraction_runs WHERE video_id=:video_id AND model_name=:model
          AND prompt_version=:prompt AND status IN ('completed','failed')
        ON CONFLICT (video_id,model,prompt) DO UPDATE
            SET status='retry',available_at=now(),reason='explicit_technical_requeue',updated_at=now()
            WHERE archive_enrichment_jobs.status IN ('pending','retry','parked')
              AND archive_enrichment_jobs.attempts<:max_attempts
    """),
        values,
    )
    db.commit()
    return {
        "status": "requeued",
        "run_id": run_id,
        "video_id": values["video_id"],
        "preserved_chapters": len(chapters),
        "preserved_assignments": len(assignments),
    }


__all__ = ["MAX_ATTEMPTS", "OWNER_LOCK", "discover_jobs", "finish_job", "next_job", "pause_queue", "requeue_run"]
