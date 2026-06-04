from __future__ import annotations

import inspect
import json

import pytest

from app.archive.labeling.repository import assignment_key, create_extraction_run, finish_extraction_run, insert_assignment, upsert_label_candidate


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
    db = _FakeDb([
        (lambda sql, params: "INSERT INTO archive_extraction_runs" in sql, _FakeResult(first={"id": "run-1"})),
        (lambda sql, params: "UPDATE archive_extraction_runs" in sql, _FakeResult()),
    ])

    run_id = create_extraction_run(db, "video", "cheap", video_id="video-1", model_name="whisper")
    finish_extraction_run(db, run_id, "completed", metrics, error=None)

    insert_sql, insert_params = db.calls[0]
    update_sql, update_params = db.calls[1]
    assert insert_sql.__class__.__name__ == "TextClause"
    assert update_sql.__class__.__name__ == "TextClause"
    assert insert_params == {"scope": "video", "extraction_tier": "cheap", "video_id": "video-1", "model_name": "whisper"}
    assert json.loads(update_params["metrics"]) == metrics


def test_upsert_label_preserves_rejected_and_inserts_normalized_aliases():
    db = _FakeDb([
        (lambda sql, params: "INSERT INTO archive_labels" in sql, _FakeResult(first=("label-1",))),
        (lambda sql, params: "INSERT INTO archive_label_aliases" in sql, _FakeResult()),
    ])

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
    insert_sql, insert_params = db.calls[0]
    alias_sql, alias_params = db.calls[1]
    compact_insert_sql = _compact_sql(insert_sql)
    assert "CASE WHEN archive_labels.status IN ('published', 'rejected', 'merged') THEN archive_labels.status ELSE EXCLUDED.status END" in compact_insert_sql
    assert "GREATEST(archive_labels.confidence_score, EXCLUDED.confidence_score)" in compact_insert_sql
    assert "ON CONFLICT (label_id, normalized_alias) DO NOTHING" in str(alias_sql)
    assert alias_params["normalized_alias"] == "new jersey"
    assert alias_params["alias"] == "New Jersey"
    assert len(db.calls) == 2


def test_assignment_key_is_deterministic_and_sensitive_to_dimensions():
    base = assignment_key("label", "video", "window", "search", 100, 200, "window-1", "chapter-1")
    assert base == assignment_key("label", "video", "window", "search", 100, 200, "window-1", "chapter-1")
    assert base != assignment_key("label", "video", "window", "alias", 100, 200, "window-1", "chapter-1")
    assert base != assignment_key("label", "video", "window", "search", 101, 200, "window-1", "chapter-1")
    assert base != assignment_key("label", "video", "window", "search", 100, 200, "window-2", "chapter-1")


def test_insert_assignment_validates_source_and_serializes_json_payloads():
    db = _FakeDb([
        (lambda sql, params: "INSERT INTO archive_label_assignments" in sql, _FakeResult()),
    ])

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
