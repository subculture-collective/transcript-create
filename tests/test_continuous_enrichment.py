from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.archive.enrichment_queue import OWNER_LOCK, discover_jobs, finish_job, next_job, resume_queue
from app.archive.openrouter_enrichment import PROMPT_VERSION


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
            VALUES (:id,0,0,5446000,'News and politics.','paragraph')
        """),
            {"id": video_id},
        )
        return video_id

    return db_session, model, video


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
        blocks=[dict(block_index=0, start_ms=0, end_ms=5_446_000, text="News and politics")],
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
