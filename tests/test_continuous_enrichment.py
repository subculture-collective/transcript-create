from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.archive.enrichment_queue import OWNER_LOCK, discover_jobs, finish_job, next_job, resume_queue
from app.archive.openrouter_enrichment import PROMPT_VERSION


def test_uncertain_transport_quarantines_without_replay_and_keeps_breakers(queue):
    from app.archive.enrichment_queue import queue_status, requeue_run
    from app.archive.labeling.repository import create_extraction_run, finish_extraction_run
    from scripts.run_archive_enrichment_queue import load_queue_guardrail_snapshot

    db, model, video = queue
    for day in range(4):
        video(day)
    discover_jobs(db, model)
    for attempt in range(3):
        target = next_job(db, model)["video_id"]
        run = create_extraction_run(db, "video", "premium", target, model, PROMPT_VERSION)
        metrics = {
            "run_id": run,
            "cost_usd": 0.02,
            "cost_reservation_usd": 1.0,
            "provider_failure": {"transient": False, "usage_reported": False, "error_code": "transport_uncertain"},
        }
        finish_extraction_run(
            db, run, "failed", metrics, "OpenRouter request outcome uncertain: transport response unavailable"
        )
        finish_job(db, model, target, {"status": "failed", "reason": "provider_failure", "metrics": metrics})
        row = db.execute(
            text("SELECT status,attempts,reason,last_run_id FROM archive_enrichment_jobs WHERE video_id=:id"),
            {"id": target},
        ).one()
        assert tuple(row[:3]) == ("parked", 1, "transport_uncertain_quarantined")
        assert str(row.last_run_id) == run
        assert (
            db.execute(text("SELECT metrics FROM archive_extraction_runs WHERE id=:id"), {"id": run}).scalar_one()
            == metrics
        )
        with pytest.raises(ValueError, match="billing reconciliation"):
            requeue_run(db, model, run)
        db.commit()
        if attempt < 2:
            assert queue_status(db, model)["status"] == "ready"
    assert next_job(db, model) == {"status": "paused", "reason": "consecutive_failures"}
    snapshot = load_queue_guardrail_snapshot(db, model, 20, continuous=True)
    assert snapshot.attempts_24h == snapshot.recent_failures == 3
    assert snapshot.recorded_cost_usd_24h == pytest.approx(0.06)
    assert snapshot.reserved_cost_usd_24h == 3


@pytest.mark.parametrize("invalid", ["missing_reserve", "reported_usage", "wrong_error", "wrong_run"])
def test_uncertain_quarantine_requires_durable_evidence(queue, invalid):
    from app.archive.enrichment_queue import queue_status
    from app.archive.labeling.repository import create_extraction_run, finish_extraction_run

    db, model, video = queue
    target = video()
    discover_jobs(db, model)
    next_job(db, model)
    run = create_extraction_run(db, "video", "premium", target, model, PROMPT_VERSION)
    metrics = {
        "run_id": run,
        "cost_reservation_usd": 1.0,
        "provider_failure": {
            "transient": False,
            "usage_reported": invalid == "reported_usage",
            "error_code": "transport_uncertain",
        },
    }
    if invalid == "missing_reserve":
        metrics.pop("cost_reservation_usd")
    error = (
        "other error"
        if invalid == "wrong_error"
        else "OpenRouter request outcome uncertain: transport response unavailable"
    )
    finish_extraction_run(db, run, "failed", metrics, error)
    other_run = create_extraction_run(db, "video", "premium", video(2), model, PROMPT_VERSION)
    finish_extraction_run(db, other_run, "completed", {})
    reported = {**metrics, "run_id": other_run} if invalid == "wrong_run" else metrics
    finish_job(db, model, target, {"status": "failed", "reason": "provider_failure", "metrics": reported})
    assert queue_status(db, model)["reason"] == "provider_failure"


@pytest.mark.parametrize("legacy", [False, True])
def test_managed_quality_rejections_do_not_trip_systemic_breakers(queue, legacy):
    from app.archive.enrichment_queue import HANDLED_QUALITY_ERRORS
    from app.archive.labeling.repository import create_extraction_run, finish_extraction_run
    from scripts.run_archive_enrichment_queue import load_queue_guardrail_snapshot

    db, model, video = queue
    for day in range(5):
        video(day)
    discover_jobs(db, model)
    for error in HANDLED_QUALITY_ERRORS:
        target = next_job(db, model)["video_id"]
        run = create_extraction_run(db, "video", "premium", target, model, PROMPT_VERSION)
        metrics = {"run_id": run, "cost_usd": 0.1, "cost_reservation_usd": 0.2}
        finish_extraction_run(db, run, "failed", metrics, error)
        finish_job(db, model, target, {"status": "failed", "metrics": metrics})
        reason = db.execute(
            text("SELECT reason FROM archive_enrichment_jobs WHERE model=:model AND video_id=:video"),
            {"model": model, "video": target},
        ).scalar_one()
        assert reason == "quality_rejected"
        if legacy:
            db.execute(text("UPDATE archive_enrichment_jobs SET reason='failed' WHERE model=:model"), {"model": model})
            db.commit()
    strict = load_queue_guardrail_snapshot(db, model, 20)
    managed = load_queue_guardrail_snapshot(db, model, 20, continuous=True)
    assert strict.recent_failures == len(HANDLED_QUALITY_ERRORS)
    assert managed.recent_finished == managed.recent_failures == 0
    assert managed.attempts_24h == strict.attempts_24h == len(HANDLED_QUALITY_ERRORS)
    assert managed.recorded_cost_usd_24h == strict.recorded_cost_usd_24h == pytest.approx(0.4)
    assert managed.reserved_cost_usd_24h == strict.reserved_cost_usd_24h == pytest.approx(0.8)
    assert next_job(db, model)["status"] == "selected"


@pytest.mark.parametrize("error", [None, "unknown fault", "OpenRouter request failed: response error code 502"])
def test_unhandled_failures_remain_in_continuous_breaker(queue, error):
    from app.archive.labeling.repository import create_extraction_run, finish_extraction_run
    from scripts.run_archive_enrichment_queue import load_queue_guardrail_snapshot

    db, model, video = queue
    target = video()
    discover_jobs(db, model)
    next_job(db, model)
    run = create_extraction_run(db, "video", "premium", target, model, PROMPT_VERSION)
    finish_extraction_run(db, run, "failed", {"run_id": run}, error)
    finish_job(db, model, target, {"status": "failed", "metrics": {"run_id": run}})
    snapshot = load_queue_guardrail_snapshot(db, model, 20, continuous=True)
    assert snapshot.recent_finished == snapshot.recent_failures == 1


def test_quality_rejection_without_durable_job_is_not_exempt(queue):
    from app.archive.enrichment_queue import HANDLED_QUALITY_ERRORS
    from app.archive.labeling.repository import create_extraction_run, finish_extraction_run
    from scripts.run_archive_enrichment_queue import load_queue_guardrail_snapshot

    db, model, video = queue
    run = create_extraction_run(db, "video", "premium", video(), model, PROMPT_VERSION)
    finish_extraction_run(db, run, "failed", {"cost_usd": 0.1}, HANDLED_QUALITY_ERRORS[0])
    assert load_queue_guardrail_snapshot(db, model, 20, continuous=True).recent_failures == 1


def test_quality_retry_allowance_still_parks_after_three_paid_attempts(queue):
    from app.archive.enrichment_queue import HANDLED_QUALITY_ERRORS
    from app.archive.labeling.repository import create_extraction_run, finish_extraction_run

    db, model, video = queue
    target = video()
    discover_jobs(db, model)
    for attempt in range(1, 4):
        db.execute(text("UPDATE archive_enrichment_jobs SET available_at=now() WHERE model=:model"), {"model": model})
        assert next_job(db, model)["attempt"] == attempt
        run = create_extraction_run(db, "video", "premium", target, model, PROMPT_VERSION)
        metrics = {"run_id": run, "cost_usd": 0.1}
        finish_extraction_run(db, run, "failed", metrics, HANDLED_QUALITY_ERRORS[0])
        finish_job(db, model, target, {"status": "failed", "metrics": metrics})
    state = db.execute(
        text("SELECT status,attempts,reason FROM archive_enrichment_jobs WHERE model=:model"), {"model": model}
    ).one()
    assert tuple(state) == ("parked", 3, "quality_rejected")
    assert next_job(db, model)["status"] == "idle"


@pytest.mark.parametrize("paid", [False, True])
def test_historical_input_reconciliation_preserves_attempts_and_spend(queue, paid):
    from app.archive.enrichment_queue import reconcile_input_run
    from app.archive.labeling.repository import create_extraction_run, finish_extraction_run
    from scripts.run_archive_enrichment_queue import load_queue_guardrail_snapshot

    db, model, video = queue
    target = video()
    discover_jobs(db, model)
    next_job(db, model)
    run = create_extraction_run(db, "video", "premium", target, model, PROMPT_VERSION)
    metrics = {"run_id": run, "model": model, "prompt_version": PROMPT_VERSION}
    if paid:
        metrics["cost_usd"] = 0.01
    finish_extraction_run(db, run, "failed", metrics, "enrichment window contains no transcript blocks")
    finish_job(db, model, target, {"status": "failed", "metrics": metrics})
    db.execute(text("DELETE FROM transcript_blocks WHERE video_id=:id AND block_index=1"), {"id": target})
    before = load_queue_guardrail_snapshot(db, model, 20)
    assert before.recent_failures == 1
    if paid:
        with pytest.raises(ValueError, match="usage"):
            reconcile_input_run(db, model, run)
        assert load_queue_guardrail_snapshot(db, model, 20) == before
        return
    assert reconcile_input_run(db, model, run)["status"] == "input_reconciled"
    original = db.execute(text("SELECT status,metrics FROM archive_extraction_runs WHERE id=:id"), {"id": run}).one()
    assert original.status == "failed"
    assert {k: v for k, v in original.metrics.items() if k != "input_preflight_reconciliation"} == metrics
    reconcile_input_run(db, model, run)
    assert (
        db.execute(text("SELECT metrics FROM archive_extraction_runs WHERE id=:id"), {"id": run}).scalar_one()
        == original.metrics
    )
    after = load_queue_guardrail_snapshot(db, model, 20)
    assert after.recent_failures == after.recent_finished == 0
    assert after.attempts_24h == before.attempts_24h == 1
    assert after.recorded_cost_usd_24h == before.recorded_cost_usd_24h
    assert (
        db.execute(text("SELECT attempts FROM archive_enrichment_jobs WHERE video_id=:id"), {"id": target}).scalar_one()
        == 1
    )


@pytest.fixture
def queue(db_session):
    model = f"test-{uuid.uuid4()}"

    def video(day=1):
        job, video_id = str(uuid.uuid4()), str(uuid.uuid4())
        db_session.execute(
            text("INSERT INTO jobs(id,kind,input_url,state) VALUES (:id,'single','https://example.test','completed')"),
            {"id": job},
        )
        db_session.execute(
            text("""
            INSERT INTO videos(id,job_id,youtube_id,idx,title,duration_seconds,state,uploaded_at)
            VALUES (:id,:job,:youtube,0,'News and politics',5446,'completed',
                    timestamptz '2026-08-01'+make_interval(days=>:day))
        """),
            {"id": video_id, "job": job, "youtube": uuid.uuid4().hex[:11], "day": day},
        )
        db_session.execute(
            text("""
            INSERT INTO transcript_blocks(video_id,block_index,start_ms,end_ms,text,kind)
            VALUES (:id,0,0,2723000,'News and politics.','paragraph'),
                   (:id,1,2723000,5446000,'More news and politics.','paragraph')
        """),
            {"id": video_id},
        )
        return video_id

    return db_session, model, video


@pytest.mark.parametrize("probe_success", [False, True])
def test_transient_cooldown_runs_one_counted_probe_before_backlog(queue, probe_success):
    from app.archive.enrichment_queue import queue_status
    from app.archive.labeling.repository import create_extraction_run, finish_extraction_run
    from scripts.run_archive_enrichment_queue import load_queue_guardrail_snapshot

    db, model, video = queue
    target = video()
    discover_jobs(db, model)
    assert next_job(db, model)["video_id"] == target
    run = create_extraction_run(db, "video", "premium", target, model, PROMPT_VERSION)
    metrics = {
        "run_id": run,
        "cost_usd": 0.02,
        "cost_reservation_usd": 1.0,
        "provider_failure": {"transient": True, "usage_reported": False, "error_code": "502"},
    }
    finish_extraction_run(db, run, "failed", metrics, "OpenRouter request failed: response error code 502")
    finish_job(db, model, target, {"status": "failed", "reason": "provider_failure", "metrics": metrics})
    assert queue_status(db, model)["reason"] == "provider_cooldown"
    assert next_job(db, model) == {"status": "paused", "reason": "provider_cooldown"}
    arrival = video(5)
    discover_jobs(db, model)
    db.execute(text("UPDATE archive_enrichment_jobs SET available_at=now() WHERE video_id=:id"), {"id": target})
    db.commit()
    # Recovery survives commits/restarts and may not consume another video.
    assert next_job(db, model) == {"status": "selected", "video_id": target, "attempt": 2}
    before = load_queue_guardrail_snapshot(db, model, 20)
    assert before.recorded_cost_usd_24h == pytest.approx(0.02)
    assert before.reserved_cost_usd_24h == 1.0
    probe = create_extraction_run(db, "video", "premium", target, model, PROMPT_VERSION)
    probe_metrics = {"run_id": probe, "cost_usd": 0.03, "provider_failure": {"transient": True}}
    finish_extraction_run(db, probe, "completed" if probe_success else "failed", probe_metrics)
    finish_job(
        db,
        model,
        target,
        (
            {"status": "completed", "metrics": probe_metrics}
            if probe_success
            else {"status": "failed", "reason": "provider_failure", "metrics": probe_metrics}
        ),
    )
    after = load_queue_guardrail_snapshot(db, model, 20)
    assert after.attempts_24h == before.attempts_24h + 1
    assert after.recorded_cost_usd_24h == pytest.approx(0.05)
    assert after.reserved_cost_usd_24h == 1.0
    assert after.recent_failures == (1 if probe_success else 2)
    if probe_success:
        assert queue_status(db, model)["reason"] is None
        assert next_job(db, model)["video_id"] == arrival
    else:
        assert next_job(db, model) == {"status": "paused", "reason": "provider_failure"}


def test_new_arrival_precedes_newest_backfill_and_retry(queue):
    db, model, video = queue
    oldest, newest = video(1), video(3)
    discover_jobs(db, model)
    assert next_job(db, model)["video_id"] == newest
    finish_job(db, model, newest, {"status": "failed"})
    arrival = video(2)
    discover_jobs(db, model)
    assert next_job(db, model)["video_id"] == arrival
    finish_job(db, model, arrival, {"status": "completed"})
    assert next_job(db, model)["video_id"] == oldest
    finish_job(db, model, oldest, {"status": "completed"})
    assert next_job(db, model)["status"] == "idle"
    db.execute(text("UPDATE archive_enrichment_jobs SET available_at=now() WHERE model=:model"), {"model": model})
    assert next_job(db, model)["video_id"] == newest


@pytest.mark.parametrize("defect", ["empty_balanced_window", "insufficient_category_evidence"])
def test_input_defects_park_without_attempt_or_extraction(queue, defect):
    db, model, video = queue
    valid, invalid = video(1), video(2)
    if defect == "empty_balanced_window":
        db.execute(text("DELETE FROM transcript_blocks WHERE video_id=:id AND block_index=1"), {"id": invalid})
    else:
        db.execute(text("UPDATE videos SET duration_seconds=301 WHERE id=:id"), {"id": invalid})
        db.execute(text("DELETE FROM transcript_blocks WHERE video_id=:id AND block_index=1"), {"id": invalid})
        db.execute(text("UPDATE transcript_blocks SET end_ms=9640 WHERE video_id=:id"), {"id": invalid})
    discover_jobs(db, model)
    assert next_job(db, model) == {
        "status": "input_parked",
        "video_id": invalid,
        "reason": f"transcript_input:{defect}",
    }
    row = db.execute(
        text("SELECT status,attempts,last_run_id FROM archive_enrichment_jobs WHERE video_id=:id AND model=:model"),
        {"id": invalid, "model": model},
    ).one()
    assert tuple(row) == ("parked", 0, None)
    assert (
        db.execute(
            text("SELECT count(*) FROM archive_extraction_runs WHERE video_id=:id"), {"id": invalid}
        ).scalar_one()
        == 0
    )
    discover_jobs(db, model)
    assert next_job(db, model)["video_id"] == valid


def test_three_attempts_park_without_blocking_other_work(queue):
    db, model, video = queue
    target = video()
    discover_jobs(db, model)
    for attempt in range(1, 4):
        assert next_job(db, model)["attempt"] == attempt
        finish_job(db, model, target, {"status": "failed"})
        row = (
            db.execute(
                text("SELECT status,available_at>now() delayed FROM archive_enrichment_jobs WHERE model=:model"),
                {"model": model},
            )
            .mappings()
            .one()
        )
        assert row["delayed"]
        assert row["status"] == ("parked" if attempt == 3 else "retry")
        db.execute(text("UPDATE archive_enrichment_jobs SET available_at=now() WHERE model=:model"), {"model": model})
    discover_jobs(db, model)
    assert next_job(db, model)["status"] == "idle"
    fresh = video(4)
    discover_jobs(db, model)
    assert next_job(db, model)["video_id"] == fresh


@pytest.mark.parametrize("failure", ["credit_exhausted", "interrupted"])
def test_pause_survives_discovery_and_worker_restart(queue, failure):
    db, model, video = queue
    target = video()
    discover_jobs(db, model)
    next_job(db, model)
    if failure == "credit_exhausted":
        finish_job(db, model, target, {"status": "credit_exhausted"})
    discover_jobs(db, model)
    first = next_job(db, model)
    assert first["status"] == "paused"
    discover_jobs(db, model)
    assert next_job(db, model) == first


def test_superseded_feedback_allows_backfill_but_new_feedback_blocks(queue):
    db, model, video = queue
    discover_jobs(db, model)
    target = video()
    batch = db.execute(
        text(
            "INSERT INTO archive_enrichment_maintenance(operation,reason) VALUES ('pre_pr28_cleanup','test') RETURNING id"
        )
    ).scalar_one()
    feedback = db.execute(
        text("INSERT INTO archive_chapter_feedback(video_id,action) VALUES (:id,'publish') RETURNING id"),
        {"id": target},
    ).scalar_one()
    db.execute(
        text(
            "INSERT INTO archive_enrichment_maintenance_rows(batch_id,table_name,row_id,row_data) VALUES (:batch,'archive_chapter_feedback',:feedback,'{}'),(:batch,'archive_video_chapters',:video,jsonb_build_object('video_id',CAST(:video AS text)))"
        ),
        {"batch": batch, "feedback": str(feedback), "video": target},
    )
    discover_jobs(db, model)
    assert (
        db.execute(
            text("SELECT new_arrival FROM archive_enrichment_jobs WHERE model=:model AND video_id=:video"),
            {"model": model, "video": target},
        ).scalar_one()
        is False
    )
    db.execute(text("INSERT INTO archive_chapter_feedback(video_id,action) VALUES (:id,'reject')"), {"id": target})
    assert next_job(db, model)["status"] == "idle"


def test_editorial_feedback_parks_discovered_video(queue):
    db, model, video = queue
    target = video()
    discover_jobs(db, model)
    db.execute(text("INSERT INTO archive_chapter_feedback(video_id,action) VALUES (:id,'reject')"), {"id": target})
    assert next_job(db, model)["status"] == "idle"
    assert (
        db.execute(text("SELECT reason FROM archive_enrichment_jobs WHERE model=:model"), {"model": model}).scalar_one()
        == "no_longer_pristine"
    )


def test_systemic_pre_provider_failures_pause_before_consuming_the_backlog(queue):
    db, model, video = queue
    for day in range(5):
        video(day)
    discover_jobs(db, model)
    for _ in range(3):
        job = next_job(db, model)
        finish_job(db, model, job["video_id"], {"status": "failed"})
    assert next_job(db, model) == {"status": "paused", "reason": "consecutive_failures"}
    assert (
        db.execute(
            text("SELECT count(*) FROM archive_enrichment_jobs WHERE model=:model AND attempts=0"), {"model": model}
        ).scalar_one()
        == 2
    )


def test_historical_failure_counts_toward_retry_limit(queue):
    db, model, video = queue
    target = video()
    for _ in range(3):
        db.execute(
            text("""
            INSERT INTO archive_extraction_runs(scope,extraction_tier,video_id,model_name,prompt_version,status,started_at,finished_at)
            VALUES ('video','premium',:id,:model,:prompt,'failed',now()-interval '2 days',now()-interval '2 days')
        """),
            {"id": target, "model": model, "prompt": PROMPT_VERSION},
        )
    discover_jobs(db, model)
    assert next_job(db, model)["status"] == "idle"
    row = db.execute(
        text("SELECT attempts,status FROM archive_enrichment_jobs WHERE model=:model"), {"model": model}
    ).one()
    assert tuple(row) == (3, "parked")


def test_another_database_owner_prevents_provider_invocation(test_engine, monkeypatch, capsys):
    from scripts import run_archive_enrichment_queue as cli

    monkeypatch.setattr(cli, "engine", test_engine)
    with test_engine.connect() as owner:
        owner.execute(text("SELECT pg_advisory_lock(hashtext(:owner))"), {"owner": OWNER_LOCK})
        owner.commit()
        try:
            assert cli.main(["--once"], config=SimpleNamespace(ARCHIVE_ENRICHMENT_ENABLED=True)) == 1
            assert "queue_owner_busy" in capsys.readouterr().out
        finally:
            owner.execute(text("SELECT pg_advisory_unlock(hashtext(:owner))"), {"owner": OWNER_LOCK})
            owner.commit()


def test_resume_refuses_uncertain_running_job(queue):
    db, model, video = queue
    video()
    discover_jobs(db, model)
    next_job(db, model)
    with pytest.raises(ValueError, match="uncertain running"):
        resume_queue(db, model)


def test_explicit_recovery_keeps_paid_history_and_daily_limits(queue):
    from app.archive.enrichment_queue import queue_status
    from app.archive.labeling.repository import create_extraction_run, finish_extraction_run
    from scripts.run_archive_enrichment_queue import load_queue_guardrail_snapshot

    db, model, video = queue
    target = video()
    discover_jobs(db, model)
    next_job(db, model)
    run = create_extraction_run(db, "video", "premium", target, model, PROMPT_VERSION)
    metrics = {"run_id": run, "cost_usd": 0.02}
    finish_extraction_run(db, run, "failed", metrics, "OpenRouter request failed: HTTP 400")
    finish_job(db, model, target, {"status": "failed", "reason": "provider_failure", "metrics": metrics})
    assert queue_status(db, model)["reason"] == "provider_failure"
    before = load_queue_guardrail_snapshot(db, model, 20)
    assert before.recent_failures == 1
    result = resume_queue(db, model)
    assert result["recovery_id"]
    after = load_queue_guardrail_snapshot(db, model, 20)
    assert after.recent_finished == after.recent_failures == 0
    assert after.attempts_24h == before.attempts_24h == 1
    assert after.recorded_cost_usd_24h == before.recorded_cost_usd_24h == 0.02
    assert (
        db.execute(text("SELECT status FROM archive_extraction_runs WHERE id=:run"), dict(run=run)).scalar_one()
        == "failed"
    )
    with pytest.raises(ValueError, match="must be paused"):
        resume_queue(db, model)
    for day in range(3):
        fresh = video(day + 2)
        discover_jobs(db, model)
        assert next_job(db, model)["video_id"] == fresh
        finish_job(db, model, fresh, {"status": "failed"})
    assert queue_status(db, model)["status"] == "paused"


@pytest.mark.parametrize("corrupt_counts", [False, True])
def test_real_worker_transaction_reconciles_or_rolls_back_candidates(queue, monkeypatch, corrupt_counts):
    from app.archive import enrichment_service as service
    from app.archive.enrichment_runner import EnrichmentInput, EpisodeInput
    from app.archive.openrouter_enrichment import EpisodeEnrichmentCandidate, OpenRouterEpisodeResult

    db, _model, video = queue
    target = video()
    episode = EpisodeInput(
        video_id=target,
        duration_ms=5_446_000,
        blocks=[
            dict(block_index=0, start_ms=0, end_ms=5_446_000, text="News and politics"),
            dict(block_index=1, start_ms=2_723_000, end_ms=5_446_000, text="Further political discussion"),
        ],
    )
    result = OpenRouterEpisodeResult(
        video_id=target,
        model="deepseek/deepseek-v4-pro",
        provider="test",
        prompt_version=PROMPT_VERSION,
        prompt_tokens=100,
        completion_tokens=100,
        cost_usd=0.01,
        elapsed_seconds=1,
        window_count=2,
        candidate=EpisodeEnrichmentCandidate(
            subjects=["News"],
            keywords=["politics"],
            categories=[dict(slug="politics", evidence_block_indexes=[0])],
            chapters=[
                dict(
                    start_ms=start,
                    title="News and politics",
                    summary="News and politics discussion.",
                    evidence_block_indexes=[0],
                )
                for start in (0, 2_723_000)
            ],
        ),
    )
    original_persist = service.persist_enrichment_candidates

    def persist(*args, **kwargs):
        metrics = original_persist(*args, **kwargs)
        if corrupt_counts:
            metrics["categories"] += 1
        return metrics

    deps = service.EnrichmentRuntimeDependencies(
        export_input=lambda *args, **kwargs: EnrichmentInput(
            schema_version="1", pipeline_version="test", episodes=[episode]
        ),
        generate_episode=lambda *args: result,
        persist_candidates=persist,
    )
    monkeypatch.setattr(service, "EnrichmentRuntimeDependencies", lambda: deps)
    config = SimpleNamespace(
        ARCHIVE_ENRICHMENT_ENABLED=True,
        ARCHIVE_ENRICHMENT_PROVIDER="openrouter",
        ARCHIVE_ENRICHMENT_MODEL=result.model,
        ARCHIVE_ENRICHMENT_PUBLISH=False,
        OPENROUTER_API_KEY="inert",
        ARCHIVE_ENRICHMENT_MAX_COST_USD_PER_VIDEO=1.0,
        ARCHIVE_ENRICHMENT_MAX_WINDOW_MINUTES=90,
    )
    if corrupt_counts:
        # Use a SAVEPOINT-aware Session: service rollback must not erase fixture
        # setup or the separately committed attempt record.
        from sqlalchemy.orm import Session

        session = Session(bind=db.connection(), join_transaction_mode="create_savepoint")
        with pytest.raises(RuntimeError, match="stored candidates"):
            service.enrich_video_candidates(session, target, config=config)
        session.close()
        assert (
            db.execute(
                text("SELECT count(*) FROM archive_video_chapters WHERE video_id=:id"), {"id": target}
            ).scalar_one()
            == 0
        )
        row = db.execute(
            text("SELECT status,metrics->>'cost_usd' cost FROM archive_extraction_runs WHERE video_id=:id"),
            {"id": target},
        ).one()
        assert tuple(row) == ("failed", "0.01")
    else:
        metrics = service.enrich_video_candidates(db, target, config=config)
        assert metrics["chapters"] == 2
        assert metrics["categories"] == 1
        assert (
            db.execute(
                text("SELECT max(end_ms) FROM archive_video_chapters WHERE video_id=:id"), {"id": target}
            ).scalar_one()
            == 5_446_000
        )
