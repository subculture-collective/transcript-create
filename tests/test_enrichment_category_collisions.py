from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.archive.enrichment_queue import requeue_run
from app.archive.enrichment_runner import EpisodeInput
from app.archive.enrichment_service import persist_enrichment_candidates, validate_stored_candidates
from app.archive.labeling.repository import create_extraction_run, finish_extraction_run
from app.archive.openrouter_enrichment import PROMPT_VERSION, EpisodeEnrichmentCandidate, OpenRouterEpisodeResult


@pytest.fixture
def persisted_collision(db_session):
    job_id, video_id = str(uuid.uuid4()), str(uuid.uuid4())
    db_session.execute(
        text(
            "INSERT INTO jobs (id, kind, input_url, state) VALUES (:id, 'single', 'https://example.test/vod', 'completed')"
        ),
        {"id": job_id},
    )
    db_session.execute(
        text(
            "INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state) "
            "VALUES (:id, :job, :youtube, 0, 'Debate and labor unions', 5446, 'completed')"
        ),
        {"id": video_id, "job": job_id, "youtube": uuid.uuid4().hex[:11]},
    )
    run_id = create_extraction_run(
        db_session,
        "video",
        "premium",
        video_id=video_id,
        model_name="deepseek/deepseek-v4-pro",
        prompt_version=PROMPT_VERSION,
    )
    boundaries = [0, 1_000_000, 2_723_000, 4_000_000, 5_446_000]
    episode = EpisodeInput(
        video_id=video_id,
        duration_ms=boundaries[-1],
        blocks=[
            dict(
                block_index=i,
                start_ms=start,
                end_ms=boundaries[i + 1],
                text="Debate about labor unions and labor-unions.",
            )
            for i, start in enumerate(boundaries[:-1])
        ],
    )
    result = OpenRouterEpisodeResult(
        video_id=video_id,
        model="deepseek/deepseek-v4-pro",
        provider="test",
        prompt_version=PROMPT_VERSION,
        prompt_tokens=100,
        completion_tokens=100,
        cost_usd=0.01,
        elapsed_seconds=1.0,
        candidate=EpisodeEnrichmentCandidate(
            subjects=["Debate", "labor unions"],
            keywords=["DEBATE", "Debate!", "labor-unions", "labor unions"],
            categories=[dict(slug=slug, evidence_block_indexes=[0, 2, 3]) for slug in ("debate", "politics", "react")],
            chapters=[
                dict(
                    start_ms=start,
                    title=f"Debate section {i}",
                    summary="Debate about labor unions.",
                    evidence_block_indexes=[i],
                )
                for i, start in enumerate(boundaries[:-1])
            ],
        ),
    )
    metrics = persist_enrichment_candidates(db_session, episode, result, run_id=run_id)
    metrics.update(window_count=2, cost_usd=0.01, repairs={"evidence_overlap_violations": 0})
    finish_extraction_run(db_session, run_id, "completed", metrics)
    return video_id, run_id, metrics


def test_categories_survive_exact_case_and_punctuation_collisions(db_session, persisted_collision):
    video_id, run_id, metrics = persisted_collision
    rows = (
        db_session.execute(
            text("""
        SELECT l.slug, l.kind, a.evidence, a.component_scores, a.status
        FROM archive_label_assignments a JOIN archive_labels l ON l.id=a.label_id
        WHERE a.video_id=:video AND a.run_id=:run
    """),
            {"video": video_id, "run": run_id},
        )
        .mappings()
        .all()
    )
    assert len(rows) == metrics["assignments"] == metrics["labels"] == 4
    assert metrics["categories"] == 3
    assert metrics["skipped_duplicate_labels"] == 5
    category = next(row for row in rows if row["slug"] == "debate")
    assert category["kind"] == "category"
    assert category["status"] == "candidate"
    assert category["component_scores"]["controlled_taxonomy"] == 1.0
    assert all(item["extractor"] == "llm_category" for item in category["evidence"])
    assert [item["block_index"] for item in category["evidence"]] == [0, 2, 3]


def test_worker_reconciles_persisted_counts(db_session, persisted_collision):
    video_id, run_id, metrics = persisted_collision
    validate_stored_candidates(db_session, video_id, run_id, metrics)
    with pytest.raises(RuntimeError, match="stored candidates"):
        validate_stored_candidates(db_session, video_id, run_id, {**metrics, "categories": 4})


@pytest.mark.parametrize("protected", [False, True])
def test_technical_requeue_preserves_snapshot_and_refuses_editorial_work(db_session, persisted_collision, protected):
    video_id, run_id, metrics = persisted_collision
    finish_extraction_run(db_session, run_id, "completed", {**metrics, "repairs": {"evidence_overlap_violations": 1}})
    if protected:
        db_session.execute(
            text("INSERT INTO archive_chapter_feedback(video_id,action) VALUES (:video,'reject')"), {"video": video_id}
        )
        with pytest.raises(ValueError, match="editorial feedback"):
            requeue_run(db_session, "deepseek/deepseek-v4-pro", run_id)
        assert (
            db_session.execute(
                text("SELECT count(*) FROM archive_video_chapters WHERE video_id=:video"), {"video": video_id}
            ).scalar_one()
            == metrics["chapters"]
        )
        return
    result = requeue_run(db_session, "deepseek/deepseek-v4-pro", run_id)
    assert result["preserved_chapters"] == metrics["chapters"]
    assert result["preserved_assignments"] == metrics["assignments"]
    snapshot = db_session.execute(
        text("SELECT candidates FROM archive_enrichment_supersessions WHERE run_id=:run"), {"run": run_id}
    ).scalar_one()
    assert len(snapshot["chapters"]) == metrics["chapters"]
    assert all(row["run_id"] == run_id for row in snapshot["assignments"])
    assert (
        db_session.execute(
            text("SELECT count(*) FROM archive_video_chapters WHERE video_id=:video"), {"video": video_id}
        ).scalar_one()
        == 0
    )
    assert requeue_run(db_session, "deepseek/deepseek-v4-pro", run_id)["status"] == "already_requeued"
    assert (
        db_session.execute(
            text("SELECT attempts FROM archive_enrichment_jobs WHERE video_id=:video"), {"video": video_id}
        ).scalar_one()
        == 1
    )


def _acceptance_sql():
    helper = (Path(__file__).resolve().parents[1] / "scripts/compose_prod.sh").read_text()
    sql = helper.split('acceptance=$(psql_admin_sql "', 1)[1].split('" \\\n', 1)[0]
    sql = sql.replace(":'video_id'::uuid", "CAST(:video_id AS uuid)")
    sql = sql.replace(":'started_at'::timestamptz", "CAST(:started_at AS timestamptz)")
    return text(sql.replace(":'model'", ":model").replace(":'prompt'", ":prompt"))


def test_supersession_does_not_block_source_video_deletion(db_session, persisted_collision):
    video_id, run_id, metrics = persisted_collision
    finish_extraction_run(db_session, run_id, "completed", {**metrics, "repairs": {"evidence_overlap_violations": 1}})
    requeue_run(db_session, "deepseek/deepseek-v4-pro", run_id)
    db_session.execute(text("DELETE FROM videos WHERE id=:video"), {"video": video_id})
    assert (
        db_session.execute(
            text("SELECT count(*) FROM archive_enrichment_supersessions WHERE run_id=:run"), {"run": run_id}
        ).scalar_one()
        == 0
    )
    assert (
        db_session.execute(
            text("SELECT count(*) FROM archive_enrichment_jobs WHERE video_id=:video"), {"video": video_id}
        ).scalar_one()
        == 0
    )
    assert (
        db_session.execute(
            text("SELECT video_id FROM archive_extraction_runs WHERE id=:run"), {"run": run_id}
        ).scalar_one()
        is None
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "overwrite_category",
        "missing_assignment",
        "chapter_count",
        "category_count",
        "label_count",
        "assignment_count",
        "zero_categories",
    ],
)
def test_canary_reconciles_stored_counts(db_session, persisted_collision, mutation):
    video_id, run_id, metrics = persisted_collision
    if mutation == "overwrite_category":
        db_session.execute(
            text("""
            UPDATE archive_label_assignments
              SET evidence=jsonb_build_array(jsonb_build_object('extractor', 'llm')),
              component_scores=jsonb_build_object('llm_grounded', 1.0)
            WHERE video_id=:video AND run_id=:run AND evidence->0->>'extractor'='llm_category'
              AND label_id=(SELECT id FROM archive_labels WHERE slug='debate')
        """),
            {"video": video_id, "run": run_id},
        )
    elif mutation == "missing_assignment":
        db_session.execute(
            text(
                "DELETE FROM archive_label_assignments WHERE video_id=:video AND run_id=:run "
                "AND evidence->0->>'extractor'='llm'"
            ),
            {"video": video_id, "run": run_id},
        )
    elif mutation != "none":
        field = {
            "chapter_count": "chapters",
            "category_count": "categories",
            "label_count": "labels",
            "assignment_count": "assignments",
            "zero_categories": "categories",
        }[mutation]
        metrics[field] = 0 if mutation == "zero_categories" else metrics[field] + 1
        db_session.execute(
            text("UPDATE archive_extraction_runs SET metrics=CAST(:metrics AS jsonb) WHERE id=:id"),
            {"id": run_id, "metrics": json.dumps(metrics)},
        )
    outcome = db_session.execute(
        _acceptance_sql(),
        dict(
            video_id=video_id,
            started_at="2000-01-01T00:00:00Z",
            model="deepseek/deepseek-v4-pro",
            prompt=PROMPT_VERSION,
        ),
    ).scalar_one()
    assert outcome == ("passed" if mutation == "none" else "failed")
