from __future__ import annotations

import inspect
import json

import pytest
from sqlalchemy import text

from app.archive.labeling.repository import (
    assignment_key,
    create_extraction_run,
    finish_extraction_run,
    insert_assignment,
    upsert_label_candidate,
)


def _compact_sql(sql) -> str:
    return " ".join(str(sql).split())


class _FakeResult:
    def __init__(self, first=None):
        self._first = first

    def first(self):
        return self._first


class _FakeDb:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        sql_text = str(sql)
        for predicate, result in self.responses:
            if predicate(sql_text, params):
                return result
        raise AssertionError(f"Unexpected query: {sql_text}")


def test_create_and_finish_run_use_text_clause_and_json_metrics():
    metrics = {"labels": 3, "windows": 7}
    db = _FakeDb(
        [
            (lambda sql, params: "INSERT INTO archive_extraction_runs" in sql, _FakeResult(first={"id": "run-1"})),
            (lambda sql, params: "UPDATE archive_extraction_runs" in sql, _FakeResult()),
        ]
    )

    run_id = create_extraction_run(db, "video", "cheap", video_id="video-1", model_name="whisper")
    finish_extraction_run(db, run_id, "completed", metrics, error=None)

    insert_sql, insert_params = db.calls[0]
    update_sql, update_params = db.calls[1]
    assert insert_sql.__class__.__name__ == "TextClause"
    assert update_sql.__class__.__name__ == "TextClause"
    assert insert_params == {
        "scope": "video",
        "extraction_tier": "cheap",
        "video_id": "video-1",
        "model_name": "whisper",
        "prompt_version": None,
    }
    assert json.loads(update_params["metrics"]) == metrics


def test_upsert_candidate_inserts_normalized_aliases_and_guards_protected_conflicts():
    db = _FakeDb(
        [
            (lambda sql, params: "pg_advisory_xact_lock" in sql, _FakeResult()),
            (lambda sql, params: "INSERT INTO archive_labels" in sql, _FakeResult(first=("label-1",))),
            (lambda sql, params: "INSERT INTO archive_label_aliases" in sql, _FakeResult()),
        ]
    )

    label_id = upsert_label_candidate(
        db,
        label="New Jersey",
        kind="topic",
        aliases=["New Jersey", "", "uh", "New   Jersey"],
        confidence_score=0.91,
        source="automatic",
        publish_tier="gold",
        status="candidate",
        run_id="run-1",
    )

    assert label_id == "label-1"
    lock_sql, lock_params = db.calls[0]
    insert_sql, insert_params = db.calls[1]
    alias_sql, alias_params = db.calls[2]
    assert "pg_advisory_xact_lock" in str(lock_sql)
    assert lock_params == {"slug": "new-jersey"}
    compact_insert_sql = _compact_sql(insert_sql)
    assert "THEN archive_labels.status ELSE EXCLUDED.status END" in compact_insert_sql
    assert "GREATEST(archive_labels.confidence_score, EXCLUDED.confidence_score)" in compact_insert_sql
    assert "THEN archive_labels.kind ELSE EXCLUDED.kind" in compact_insert_sql
    assert "archive_labels.source IN ('admin', 'seed', 'hybrid')" in compact_insert_sql
    assert "WHERE archive_labels.status NOT IN ('published', 'rejected', 'merged', 'hidden')" in compact_insert_sql
    assert "AND archive_labels.source NOT IN ('admin', 'seed', 'hybrid')" in compact_insert_sql
    assert "ON CONFLICT (label_id, normalized_alias) DO NOTHING" in str(alias_sql)
    assert alias_params["normalized_alias"] == "new jersey"
    assert alias_params["alias"] == "New Jersey"
    assert len(db.calls) == 3


def test_protected_conflict_returns_existing_id_without_alias_writes():
    db = _FakeDb(
        [
            (lambda sql, params: "pg_advisory_xact_lock" in sql, _FakeResult()),
            (lambda sql, params: "INSERT INTO archive_labels" in sql, _FakeResult()),
            (lambda sql, params: "SELECT id FROM archive_labels" in sql, _FakeResult(first=("protected-id",))),
        ]
    )
    assert (
        upsert_label_candidate(
            db,
            label="Politics",
            kind="category",
            aliases=["New alias"],
            confidence_score=0.99,
            source="automatic",
            publish_tier="bronze",
            status="candidate",
            run_id=None,
        )
        == "protected-id"
    )
    assert len(db.calls) == 3
    assert db.calls[-1][1] == {"slug": "politics"}


@pytest.mark.parametrize(
    "status,source",
    [(status, "automatic") for status in ("published", "rejected", "merged", "hidden")]
    + [("candidate", source) for source in ("admin", "seed", "hybrid")],
)
def test_protected_label_is_a_database_noop(db_session, status, source):
    label_id = db_session.execute(
        text("""
        INSERT INTO archive_labels (slug, label, kind, status, source, publish_tier, confidence_score,
                                   created_at, updated_at)
        VALUES ('protected-regression', 'Original label', 'topic', :status, :source, 'silver', 0.42,
                '2020-01-01'::timestamptz, '2020-01-02'::timestamptz) RETURNING id
        """),
        {"status": status, "source": source},
    ).scalar_one()
    snapshot_sql = text("SELECT to_jsonb(l), xmin::text FROM archive_labels l WHERE id = :id")
    before = db_session.execute(snapshot_sql, {"id": label_id}).one()
    result = upsert_label_candidate(
        db_session,
        label="Protected Regression",
        kind="category",
        aliases=["New alias"],
        confidence_score=0.99,
        source="automatic",
        publish_tier="gold",
        status="candidate",
        run_id=None,
    )
    assert result == str(label_id)
    assert db_session.execute(snapshot_sql, {"id": label_id}).one() == before
    assert (
        db_session.execute(
            text("SELECT count(*) FROM archive_label_aliases WHERE label_id = :id"),
            {"id": label_id},
        ).scalar_one()
        == 0
    )


def test_automatic_candidate_still_updates_and_adds_aliases(db_session):
    arguments = dict(
        label="Mutable Regression",
        kind="topic",
        aliases=[],
        confidence_score=0.42,
        source="automatic",
        publish_tier="bronze",
        status="candidate",
        run_id=None,
    )
    label_id = upsert_label_candidate(db_session, **arguments)
    arguments.update(kind="category", confidence_score=0.99, aliases=["New alias"], publish_tier="gold")
    assert upsert_label_candidate(db_session, **arguments) == label_id
    row = db_session.execute(
        text("SELECT kind, confidence_score, publish_tier FROM archive_labels WHERE id = :id"),
        {"id": label_id},
    ).one()
    assert row.kind == "category"
    assert float(row.confidence_score) == 0.99
    assert row.publish_tier == "gold"
    assert (
        db_session.execute(
            text("SELECT count(*) FROM archive_label_aliases WHERE label_id = :id"),
            {"id": label_id},
        ).scalar_one()
        == 1
    )


def test_assignment_key_is_deterministic_and_sensitive_to_dimensions():
    base = assignment_key("label", "video", "window", "search", 100, 200, "window-1", "chapter-1")
    assert base == assignment_key("label", "video", "window", "search", 100, 200, "window-1", "chapter-1")
    assert base != assignment_key("label", "video", "window", "alias", 100, 200, "window-1", "chapter-1")
    assert base != assignment_key("label", "video", "window", "search", 101, 200, "window-1", "chapter-1")
    assert base != assignment_key("label", "video", "window", "search", 100, 200, "window-2", "chapter-1")


def test_insert_assignment_validates_source_and_serializes_json_payloads():
    db = _FakeDb(
        [
            (lambda sql, params: "INSERT INTO archive_label_assignments" in sql, _FakeResult()),
        ]
    )

    key = insert_assignment(
        db,
        label_id="label-1",
        video_id="video-1",
        unit_type="window",
        status="candidate",
        publish_tier="bronze",
        confidence_score=0.77,
        evidence=[{"kind": "alias", "text": "New Jersey"}],
        source="search",
        run_id="run-1",
        start_ms=100,
        end_ms=200,
        window_id="window-1",
        chapter_id=None,
        component_scores={"alias": 0.7},
    )

    sql, params = db.calls[0]
    assert key == "label-1|video-1|window|search|100|200|window-1|"
    assert "ON CONFLICT (assignment_key) DO UPDATE SET" in str(sql)
    assert "archive_label_assignments.status = 'rejected'" in str(sql)
    assert params["source"] == "search"
    assert params["assignment_key"] == key
    assert json.loads(params["evidence"]) == [{"kind": "alias", "text": "New Jersey"}]
    assert json.loads(params["component_scores"]) == {"alias": 0.7}


def test_insert_assignment_rejects_invalid_source_and_has_no_automatic_default():
    assert inspect.signature(insert_assignment).parameters["source"].default is inspect._empty
    with pytest.raises(ValueError):
        insert_assignment(
            _FakeDb([]),
            label_id="label-1",
            video_id="video-1",
            unit_type="window",
            status="candidate",
            publish_tier="bronze",
            confidence_score=0.77,
            evidence=[],
            source="automatic",
            run_id=None,
        )
