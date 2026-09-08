from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from app.archive.enrichment_cleanup import cleanup_legacy
from app.archive.enrichment_publication import approve_run, invalidate_enrichment_views
from app.archive.openrouter_enrichment import PROMPT_VERSION
from app.exceptions import ValidationError
from scripts.approve_archive_enrichment import main, run_maintenance


@pytest.fixture
def cohort(db_session):
    db = db_session

    def make(*, old=False, status="completed"):
        ids = {name: str(uuid.uuid4()) for name in ("job", "video", "run", "label", "assignment")}
        db.execute(
            text("INSERT INTO jobs(id,kind,input_url,state) VALUES (:job,'single','https://example.test','completed')"),
            ids,
        )
        db.execute(
            text("""INSERT INTO videos(id,job_id,youtube_id,idx,title,duration_seconds,state)
            VALUES (:video,:job,:youtube,0,'News',600,'completed')"""),
            {**ids, "youtube": uuid.uuid4().hex[:11]},
        )
        metrics = {"chapters": 2, "assignments": 1, "categories": 1, "repairs": {"evidence_overlap_violations": 0}}
        db.execute(
            text(
                """INSERT INTO archive_extraction_runs(id,scope,extraction_tier,video_id,model_name,prompt_version,status,started_at,metrics)
            VALUES (:run,'video','premium',:video,'deepseek/deepseek-v4-pro',:prompt,:status,CAST(:started AS timestamptz),CAST(:metrics AS jsonb))"""
            ),
            {
                **ids,
                "prompt": PROMPT_VERSION,
                "status": status,
                "started": "2026-09-01T00:00:00Z" if old else "2026-09-08T00:00:00Z",
                "metrics": json.dumps(metrics),
            },
        )
        db.execute(
            text("""INSERT INTO archive_labels(id,slug,label,kind,source,created_by_run_id)
            VALUES (:label,:slug,'News','category','automatic',:run)"""),
            {**ids, "slug": uuid.uuid4().hex},
        )
        db.execute(
            text(
                """INSERT INTO archive_label_assignments(id,video_id,label_id,run_id,source,status,publish_tier,unit_type,assignment_key)
            VALUES (:assignment,:video,:label,:run,'llm','candidate','bronze','vod',gen_random_uuid()::text)"""
            ),
            ids,
        )
        db.execute(
            text(
                """INSERT INTO archive_video_chapters(video_id,run_id,chapter_index,start_ms,end_ms,title,summary,source,status)
            VALUES (:video,:run,0,0,300000,'Opening','','automatic','candidate'),
                   (:video,:run,1,300000,600000,'Followup','','automatic','candidate')"""
            ),
            ids,
        )
        return ids

    return db, make


def test_approval_assignment_lookup_can_use_partial_run_index(cohort):
    db, make = cohort
    ids = make()
    db.execute(text("SET LOCAL enable_seqscan=off"))
    plan = (
        db.execute(
            text("""EXPLAIN SELECT * FROM archive_label_assignments
        WHERE run_id=:run AND source='llm' ORDER BY id FOR UPDATE"""),
            ids,
        )
        .scalars()
        .all()
    )
    assert "archive_enrichment_assignment_run_lookup" in "\n".join(plan)


def test_approval_publishes_and_audits_without_reapproval(cohort):
    db, make = cohort
    ids = make()
    assert approve_run(db, ids["run"])["status"] == "approved"
    assert (
        db.execute(text("SELECT status FROM archive_label_assignments WHERE id=:assignment"), ids).scalar_one()
        == "admin_approved"
    )
    assert db.execute(text("SELECT status FROM archive_labels WHERE id=:label"), ids).scalar_one() == "published"
    assert (
        db.execute(text("SELECT count(*) FROM archive_chapter_feedback WHERE video_id=:video"), ids).scalar_one() == 2
    )
    snapshot = db.execute(text("SELECT snapshot FROM archive_enrichment_approvals WHERE run_id=:run"), ids).scalar_one()
    assert snapshot["chapters"][0]["status"] == "candidate"
    db.execute(text("UPDATE archive_video_chapters SET status='hidden' WHERE video_id=:video"), ids)
    assert approve_run(db, ids["run"])["status"] == "already_approved"
    assert (
        db.execute(
            text("SELECT count(*) FROM archive_video_chapters WHERE video_id=:video AND status='hidden'"), ids
        ).scalar_one()
        == 2
    )


def test_approval_preserves_hidden_topic_assignments(cohort):
    db, make = cohort
    ids = make()
    hidden = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO archive_labels(id,slug,label,kind,source,status) VALUES (:id,:slug,'Suppressed topic','topic','automatic','hidden')"
        ),
        {"id": hidden, "slug": uuid.uuid4().hex},
    )
    db.execute(
        text(
            "INSERT INTO archive_label_assignments(video_id,label_id,run_id,source,status,unit_type,assignment_key) VALUES (:video,:label,:run,'llm','candidate','vod',gen_random_uuid()::text)"
        ),
        {**ids, "label": hidden},
    )
    db.execute(
        text("UPDATE archive_extraction_runs SET metrics=jsonb_set(metrics,'{assignments}','2') WHERE id=:run"), ids
    )
    result = approve_run(db, ids["run"])
    assert result["assignments"] == 1
    assert result["suppressed_assignments"] == 1
    assert db.execute(text("SELECT status FROM archive_labels WHERE id=:id"), {"id": hidden}).scalar_one() == "hidden"
    assert (
        db.execute(text("SELECT status FROM archive_label_assignments WHERE label_id=:id"), {"id": hidden}).scalar_one()
        == "candidate"
    )


@pytest.mark.parametrize(
    "defect",
    [
        "old",
        "failed",
        "edited",
        "overlap",
        "zero_categories",
        "hidden_label",
        "short_chapter",
        "feedback",
        "shared_visible_assignment",
        "admin_label",
        "seed_label",
        "hybrid_label",
        "cross_video_assignment",
    ],
)
def test_approval_refuses_unqualified_or_editorial_work(cohort, defect):
    db, make = cohort
    ids = make(old=defect == "old", status="failed" if defect == "failed" else "completed")
    if defect == "cross_video_assignment":
        other = make()
        db.execute(
            text("UPDATE archive_label_assignments SET video_id=:other WHERE id=:assignment"),
            {**ids, "other": other["video"]},
        )
    if defect == "edited":
        db.execute(
            text("UPDATE archive_video_chapters SET updated_at=created_at+interval '1 second' WHERE video_id=:video"),
            ids,
        )
    if defect in {"overlap", "zero_categories"}:
        key, value = ("{repairs,evidence_overlap_violations}", "1") if defect == "overlap" else ("{categories}", "0")
        db.execute(
            text(
                "UPDATE archive_extraction_runs SET metrics=jsonb_set(metrics,CAST(:key AS text[]),CAST(:value AS jsonb)) WHERE id=:run"
            ),
            {**ids, "key": key, "value": value},
        )
    if defect == "hidden_label":
        db.execute(text("UPDATE archive_labels SET status='hidden' WHERE id=:label"), ids)
    if defect in {"admin_label", "seed_label", "hybrid_label"}:
        db.execute(
            text("UPDATE archive_labels SET source=:source WHERE id=:label"), {**ids, "source": defect.split("_")[0]}
        )
    if defect == "short_chapter":
        db.execute(
            text("UPDATE archive_video_chapters SET start_ms=590000 WHERE video_id=:video AND chapter_index=1"), ids
        )
    if defect == "feedback":
        db.execute(text("INSERT INTO archive_chapter_feedback(video_id,action) VALUES (:video,'edit')"), ids)
    if defect == "shared_visible_assignment":
        db.execute(
            text(
                """INSERT INTO archive_label_assignments(video_id,label_id,source,status,publish_tier,unit_type,assignment_key)
            VALUES (:video,:label,'alias','auto_published','gold','vod',gen_random_uuid()::text)"""
            ),
            ids,
        )
    with pytest.raises((ValueError, ValidationError)), db.begin_nested():
        approve_run(db, ids["run"])
    assert (
        db.execute(text("SELECT count(*) FROM archive_enrichment_approvals WHERE run_id=:run"), ids).scalar_one() == 0
    )
    assert (
        db.execute(text("SELECT status FROM archive_label_assignments WHERE id=:assignment"), ids).scalar_one()
        == "candidate"
    )


def test_cleanup_snapshots_published_rows_preserves_runs_labels_feedback_and_non_llm(cohort):
    db, make = cohort
    old, newer = make(old=True), make()
    db.execute(text("UPDATE archive_video_chapters SET status='published' WHERE video_id=:video"), old)
    db.execute(
        text("""INSERT INTO archive_chapter_feedback(video_id,chapter_id,action)
        SELECT video_id,id,'publish' FROM archive_video_chapters WHERE video_id=:video"""),
        old,
    )
    db.execute(
        text("""INSERT INTO archive_label_assignments(video_id,label_id,run_id,source,status,unit_type,assignment_key)
        VALUES (:video,:label,:run,'alias','candidate','vod',gen_random_uuid()::text)"""),
        old,
    )
    outcome = cleanup_legacy(db)
    assert outcome["snapshots"]["archive_video_chapters"] == 2
    assert outcome["snapshots"]["archive_label_assignments"] == 1
    assert (
        db.execute(
            text("SELECT count(*) FROM archive_chapter_feedback WHERE video_id=:video AND chapter_id IS NULL"), old
        ).scalar_one()
        == 2
    )
    assert (
        db.execute(
            text("SELECT count(*) FROM archive_label_assignments WHERE video_id=:video AND source='alias'"), old
        ).scalar_one()
        == 1
    )
    assert db.execute(text("SELECT status FROM archive_extraction_runs WHERE id=:run"), old).scalar_one() == "completed"
    assert db.execute(text("SELECT count(*) FROM archive_labels WHERE id=:label"), old).scalar_one() == 1
    assert (
        db.execute(text("SELECT count(*) FROM archive_video_chapters WHERE video_id=:video"), newer).scalar_one() == 2
    )


def test_cleanup_refuses_out_of_scope_cascade(cohort):
    db, make = cohort
    ids = make(old=True)
    db.execute(
        text(
            """INSERT INTO archive_label_assignments(video_id,label_id,chapter_id,source,status,unit_type,assignment_key)
        SELECT :video,:label,id,'alias','candidate','vod',gen_random_uuid()::text FROM archive_video_chapters WHERE video_id=:video LIMIT 1"""
        ),
        ids,
    )
    with pytest.raises(ValueError, match="cascade"), db.begin_nested():
        cleanup_legacy(db)
    assert db.execute(text("SELECT count(*) FROM archive_video_chapters WHERE video_id=:video"), ids).scalar_one() == 2


@pytest.mark.parametrize("args", [["--apply"], ["--approved"], ["--unknown"]])
def test_cli_requires_explicit_apply_and_approval(args):
    with pytest.raises(SystemExit):
        main(args)


def test_post_commit_cache_failure_does_not_raise(monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("unavailable cache")

    monkeypatch.setattr("app.cache.invalidate_video_data", unavailable)
    assert invalidate_enrichment_views(str(uuid.uuid4())) is False


def test_bulk_invalidation_is_limited_to_enrichment_views(monkeypatch):
    prefixes = []
    monkeypatch.setattr("app.cache.invalidate_cache_pattern", prefixes.append)
    assert invalidate_enrichment_views() is True
    assert prefixes == ["video:*", "search:*", "archive:*", "aggregate:*"]


def test_maintenance_rehearsal_is_reversible_and_apply_is_atomic(cohort):
    db, make = cohort
    old, newer = make(old=True), make()
    rehearsal = db.begin_nested()
    result = run_maintenance(db)
    assert result["cleanup"]["snapshots"]["archive_video_chapters"] == 2
    assert result["approvals"][0]["status"] == "approved"
    rehearsal.rollback()
    assert db.execute(text("SELECT count(*) FROM archive_video_chapters WHERE video_id=:video"), old).scalar_one() == 2
    assert (
        db.execute(text("SELECT status FROM archive_label_assignments WHERE id=:assignment"), newer).scalar_one()
        == "candidate"
    )
    db.execute(text("UPDATE archive_labels SET status='hidden' WHERE id=:label"), newer)
    with pytest.raises(ValueError, match="hidden"), db.begin_nested():
        run_maintenance(db)
    assert db.execute(text("SELECT count(*) FROM archive_video_chapters WHERE video_id=:video"), old).scalar_one() == 2


def test_maintenance_refuses_running_extraction(cohort):
    db, make = cohort
    ids = make(status="running")
    with pytest.raises(ValueError, match="running extraction"), db.begin_nested():
        run_maintenance(db)
    assert db.execute(text("SELECT count(*) FROM archive_video_chapters WHERE video_id=:video"), ids).scalar_one() == 2
