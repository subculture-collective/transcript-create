from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.archive.labeling.types import LabelCandidate


class FakeResult:
    def __init__(self, rows=None):
        self._rows = list(rows or [])

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class FakeDb:
    def __init__(self):
        self.calls = []
        self.title = ""

    def execute(self, sql, params=None):
        self.calls.append((str(sql), params))
        if "SELECT title FROM videos" in str(sql):
            return FakeResult([{"title": self.title}])
        if "SELECT status, canonical_id FROM archive_labels" in str(sql):
            return FakeResult([{"status": "published", "canonical_id": None}])
        return FakeResult([])


def test_extract_labels_for_video_persists_windows_and_assignments(monkeypatch):
    from app.archive.labeling import pipeline

    db = FakeDb()
    windows_written = []
    assignments = []
    runs = []

    monkeypatch.setattr(pipeline, "create_extraction_run", lambda *args, **kwargs: "run-1")
    monkeypatch.setattr(pipeline, "finish_extraction_run", lambda *args, **kwargs: runs.append(args[2:]))
    monkeypatch.setattr(
        pipeline,
        "load_source_segments",
        lambda _db, _video_id, source: [{"id": 1, "start_ms": 0, "end_ms": 1000, "text": f"{source} segment"}],
    )
    monkeypatch.setattr(
        pipeline,
        "build_windows_from_segments",
        lambda segments, source: [
            SimpleNamespace(
                source=source,
                start_ms=0,
                end_ms=1000,
                text=f"{source} window",
                text_hash=f"{source}-hash",
                segment_ids=[1],
                token_count=2,
            )
        ]
        if segments
        else [],
    )
    monkeypatch.setattr(pipeline, "persist_windows", lambda _db, video_id, windows: windows_written.append((video_id, list(windows))) or len(windows))
    monkeypatch.setattr(
        pipeline,
        "_load_existing_aliases",
        lambda _db: [{"label_id": "label-1", "label": "Gaza", "kind": "topic", "alias": "gaza", "status": "active", "is_ambiguous": False}],
    )
    monkeypatch.setattr(
        pipeline,
        "_load_policy",
        lambda _db, label_kind, unit_type, extraction_tier: {
            "min_publish_score": 0.90,
            "min_review_score": 0.65,
            "min_evidence_count": 1,
            "min_distinct_videos": 1,
            "require_existing_canonical": True,
            "auto_publish_enabled": True,
        },
    )
    monkeypatch.setattr(
        pipeline,
        "extract_alias_candidates",
        lambda _windows, _aliases: [
            LabelCandidate(
                label="Gaza",
                kind="topic",
                aliases=("gaza",),
                confidence_score=0.95,
                component_scores={"evidence_count": 1.0, "distinct_videos": 1.0},
                evidence=(
                    {
                        "extractor": "alias",
                        "video_id": "video-1",
                        "start_ms": 0,
                        "end_ms": 1000,
                        "snippet": "gaza segment",
                        "matched_alias": "gaza",
                    },
                ),
            )
        ],
    )
    monkeypatch.setattr(pipeline, "extract_keyphrase_candidates", lambda _windows, **kwargs: [])
    monkeypatch.setattr(
        pipeline,
        "upsert_label_candidate",
        lambda _db, **kwargs: assignments.append(("upsert", kwargs)) or "label-1",
    )
    monkeypatch.setattr(
        pipeline,
        "insert_assignment",
        lambda _db, **kwargs: assignments.append(("assignment", kwargs)) or "assignment-1",
    )

    result = pipeline.extract_labels_for_video(db, video_id="video-1", extraction_tier="cheap")

    assert result["video_id"] == "video-1"
    assert result["run_id"] == "run-1"
    assert result["windows"] == 2
    assert result["candidates"] == 1
    assert result["assignments"] == 1
    assert len(windows_written) == 2
    assignment_call = next(call for kind, call in assignments if kind == "assignment")
    assert assignment_call["source"] == "alias"
    assert assignment_call["status"] == "auto_published"
    assert assignment_call["window_id"] is None
    assert runs == [("completed", {"windows": 2, "candidates": 1, "assignments": 1})]


def test_extract_labels_for_video_uses_keyphrase_assignment_source(monkeypatch):
    from app.archive.labeling import pipeline

    db = FakeDb()
    captured = []

    monkeypatch.setattr(pipeline, "create_extraction_run", lambda *args, **kwargs: "run-2")
    monkeypatch.setattr(pipeline, "finish_extraction_run", lambda *args, **kwargs: captured.append((args[2], kwargs)))
    monkeypatch.setattr(pipeline, "load_source_segments", lambda *_args, **_kwargs: [{"id": 1, "start_ms": 0, "end_ms": 1000, "text": "keyphrase segment"}])
    monkeypatch.setattr(
        pipeline,
        "build_windows_from_segments",
        lambda segments, source: [SimpleNamespace(source=source, start_ms=0, end_ms=1000, text="keyphrase window", text_hash=f"{source}-hash", segment_ids=[1], token_count=2)]
        if segments
        else [],
    )
    monkeypatch.setattr(pipeline, "persist_windows", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(pipeline, "_load_existing_aliases", lambda _db: [])
    monkeypatch.setattr(
        pipeline,
        "_load_policy",
        lambda _db, label_kind, unit_type, extraction_tier: {
            "min_publish_score": 0.90,
            "min_review_score": 0.65,
            "min_evidence_count": 1,
            "min_distinct_videos": 1,
            "require_existing_canonical": False,
            "auto_publish_enabled": True,
        },
    )
    monkeypatch.setattr(pipeline, "extract_alias_candidates", lambda _windows, _aliases: [])
    monkeypatch.setattr(
        pipeline,
        "extract_keyphrase_candidates",
        lambda _windows, min_distinct_videos, min_occurrences: [
            LabelCandidate(
                label="Okbuddy",
                kind="topic",
                aliases=("okbuddy",),
                confidence_score=0.96,
                component_scores={"occurrences": 3.0, "distinct_videos": 1.0},
                evidence=(
                    {
                        "extractor": "keyphrase",
                        "video_id": "video-2",
                        "start_ms": 0,
                        "end_ms": 1000,
                        "snippet": "okbuddy segment",
                    },
                ),
            )
        ],
    )
    monkeypatch.setattr(pipeline, "upsert_label_candidate", lambda _db, **kwargs: kwargs.get("label", "label-2") or "label-2")
    assignment_calls = []
    monkeypatch.setattr(pipeline, "insert_assignment", lambda _db, **kwargs: assignment_calls.append(kwargs) or "assignment-2")

    result = pipeline.extract_labels_for_video(db, video_id="video-2", extraction_tier="cheap")

    assert result["candidates"] == 1
    assert assignment_calls[0]["source"] == "keyphrase"
    assert assignment_calls[0]["source"] != "automatic"
    assert captured == [("completed", {})]


def test_extract_labels_for_video_uses_title_assignment_source(monkeypatch):
    from app.archive.labeling import pipeline

    db = FakeDb()
    db.title = "HasanAbi April 23, 2026 – hanging out after Chadvice"
    assignment_calls = []

    monkeypatch.setattr(pipeline, "create_extraction_run", lambda *args, **kwargs: "run-title")
    monkeypatch.setattr(pipeline, "finish_extraction_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, "load_source_segments", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(pipeline, "build_windows_from_segments", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(pipeline, "persist_windows", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        pipeline,
        "_load_existing_aliases",
        lambda _db: [
            {
                "label_id": "tag-chadvice",
                "label": "Chadvice",
                "kind": "category",
                "alias": "chadvice",
                "status": "active",
                "is_ambiguous": False,
            }
        ],
    )
    monkeypatch.setattr(
        pipeline,
        "_load_policy",
        lambda _db, label_kind, unit_type, extraction_tier: {
            "min_publish_score": 0.90,
            "min_review_score": 0.65,
            "min_evidence_count": 1,
            "min_distinct_videos": 1,
            "require_existing_canonical": True,
            "auto_publish_enabled": True,
        },
    )
    monkeypatch.setattr(pipeline, "extract_keyphrase_candidates", lambda _windows, **kwargs: [])
    monkeypatch.setattr(pipeline, "extract_alias_candidates", lambda _windows, _aliases: [])
    monkeypatch.setattr(pipeline, "upsert_label_candidate", lambda _db, **kwargs: "label-chadvice")
    monkeypatch.setattr(pipeline, "insert_assignment", lambda _db, **kwargs: assignment_calls.append(kwargs) or "assignment-title")

    result = pipeline.extract_labels_for_video(db, video_id="video-title", extraction_tier="cheap")

    assert result["candidates"] == 1
    assert result["assignments"] == 1
    assert assignment_calls[0]["source"] == "title"
    assert assignment_calls[0]["status"] == "auto_published"
    assert assignment_calls[0]["evidence"][0]["snippet"] == db.title


def test_extract_labels_for_video_marks_failed_run_and_reraises(monkeypatch):
    from app.archive.labeling import pipeline

    db = FakeDb()
    calls = []

    monkeypatch.setattr(pipeline, "create_extraction_run", lambda *args, **kwargs: "run-3")
    monkeypatch.setattr(pipeline, "finish_extraction_run", lambda _db, run_id, status, metrics, error=None: calls.append((run_id, status, metrics, error)))
    monkeypatch.setattr(pipeline, "load_source_segments", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        pipeline.extract_labels_for_video(db, video_id="video-3", extraction_tier="cheap")

    assert calls == [("run-3", "failed", {"windows": 0, "candidates": 0, "assignments": 0}, "boom")]
