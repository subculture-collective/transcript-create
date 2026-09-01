from __future__ import annotations

import json

import pytest

from app.archive.enrichment_runner import EnrichmentInput, EpisodeInput
from app.archive.enrichment_service import (
    EnrichmentPersistenceDependencies,
    EnrichmentRuntimeDependencies,
    enrich_video_candidates,
    persist_enrichment_candidates,
)
from app.archive.openrouter_enrichment import EpisodeEnrichmentCandidate, OpenRouterEpisodeResult


class _Result:
    def __init__(self, *, scalar=0, first=None):
        self._scalar = scalar
        self._first = first

    def scalar_one(self):
        return self._scalar

    def first(self):
        return self._first


class _Db:
    def __init__(self):
        self.calls = []
        self.chapter_id = 0

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        if "SELECT COUNT(*)" in sql:
            return _Result(scalar=0)
        if "INSERT INTO archive_video_chapters" in sql:
            self.chapter_id += 1
            return _Result(first=(f"chapter-{self.chapter_id}",))
        return _Result()

    def commit(self):
        self.calls.append(("COMMIT", None))

    def rollback(self):
        self.calls.append(("ROLLBACK", None))


def test_persist_enrichment_writes_review_candidates_with_grounded_labels():
    episode = EpisodeInput(
        video_id="video-1",
        duration_ms=1_200_000,
        blocks=[
            {
                "block_index": 0,
                "start_ms": 0,
                "end_ms": 600_000,
                "text": "Workers discuss labor organizing and a union vote.",
            },
            {
                "block_index": 1,
                "start_ms": 600_000,
                "end_ms": 1_200_000,
                "text": "Tenants discuss housing costs and tenant protections.",
            },
        ],
    )
    result = OpenRouterEpisodeResult(
        video_id="video-1",
        model="deepseek/deepseek-v4-pro",
        provider="provider",
        prompt_version="prompt-v1",
        candidate=EpisodeEnrichmentCandidate(
            subjects=["labor organizing", "housing costs", "unsupported invention"],
            keywords=["union vote", "tenant protections"],
            categories=[{"slug": "politics", "evidence_block_indexes": [0]}],
            chapters=[
                {
                    "start_ms": 0,
                    "title": "Labor Organizing and a Union Vote",
                    "summary": "Workers discuss labor organizing and an upcoming union vote.",
                    "evidence_block_indexes": [0],
                },
                {
                    "start_ms": 600_000,
                    "title": "Housing Costs and Tenant Protections",
                    "summary": "Tenants discuss housing costs and tenant protections.",
                    "evidence_block_indexes": [1],
                },
            ],
        ),
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.01,
        elapsed_seconds=1.0,
    )
    labels = []
    assignments = []

    def upsert_label(_db, **kwargs):
        labels.append(kwargs)
        return f"label-{len(labels)}"

    def insert_assignment(_db, **kwargs):
        assignments.append(kwargs)
        return "assignment"

    db = _Db()
    metrics = persist_enrichment_candidates(
        db,
        episode,
        result,
        run_id="run-1",
        dependencies=EnrichmentPersistenceDependencies(
            upsert_label=upsert_label,
            insert_assignment=insert_assignment,
        ),
    )

    chapter_inserts = [call for call in db.calls if "INSERT INTO archive_video_chapters" in call[0]]
    conflict_query = next(sql for sql, _params in db.calls if "SELECT COUNT(*)" in sql)
    candidate_delete = next(sql for sql, _params in db.calls if "DELETE FROM archive_video_chapters" in sql)
    assert len(chapter_inserts) == 2
    assert "source <> 'automatic'" in conflict_query
    assert "status IN ('published', 'hidden')" in conflict_query
    assert "status IN ('candidate', 'rejected')" in candidate_delete
    assert all(call[1]["status"] == "candidate" for call in chapter_inserts)
    assert all(call[1]["source"] == "automatic" for call in chapter_inserts)
    assert all(call[1]["model_name"] == "deepseek/deepseek-v4-pro" for call in chapter_inserts)
    assert all(call[1]["prompt_version"] == "prompt-v1" for call in chapter_inserts)
    assert json.loads(chapter_inserts[0][1]["evidence"])[0]["block_index"] == 0
    assert {label["label"] for label in labels} == {
        "Politics",
        "labor organizing",
        "housing costs",
        "union vote",
        "tenant protections",
    }
    assert all(label["status"] == "candidate" and label["publish_tier"] == "bronze" for label in labels)
    assert all(item["status"] == "candidate" and item["source"] == "llm" for item in assignments)
    assert all(item["evidence"] for item in assignments)
    category = next(label for label in labels if label["kind"] == "category")
    assert category["status"] == "candidate" and category["publish_tier"] == "bronze"
    assert metrics == {
        "chapters": 2,
        "categories": 1,
        "labels": 5,
        "assignments": 5,
        "skipped_ungrounded_labels": 1,
    }


def test_enrich_video_generates_v4_pro_candidates_and_records_run():
    episode = EpisodeInput(
        video_id="video-1",
        duration_ms=600_000,
        blocks=[
            {
                "block_index": 0,
                "start_ms": 0,
                "end_ms": 600_000,
                "text": "Workers discuss labor organizing and a union vote.",
            }
        ],
    )
    result = OpenRouterEpisodeResult(
        video_id="video-1",
        model="deepseek/deepseek-v4-pro",
        provider="provider",
        prompt_version="prompt-v1",
        candidate=EpisodeEnrichmentCandidate(
            subjects=["labor organizing"],
            keywords=["union vote"],
            categories=[{"slug": "politics", "evidence_block_indexes": [0]}],
            chapters=[
                {
                    "start_ms": 0,
                    "title": "Labor Organizing and Union Voting",
                    "summary": "Workers discuss labor organizing and a union vote.",
                    "evidence_block_indexes": [0],
                },
                {
                    "start_ms": 300_000,
                    "title": "Organizing Strategy and Next Steps",
                    "summary": "The discussion continues with organizing strategy.",
                    "evidence_block_indexes": [0],
                },
            ],
        ),
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.01,
        elapsed_seconds=1.0,
        window_count=1,
    )
    finished = []
    persisted = []

    class Config:
        ARCHIVE_ENRICHMENT_ENABLED = True
        ARCHIVE_ENRICHMENT_PROVIDER = "openrouter"
        ARCHIVE_ENRICHMENT_MODEL = "deepseek/deepseek-v4-pro"
        ARCHIVE_ENRICHMENT_PUBLISH = False
        ARCHIVE_ENRICHMENT_MAX_COST_USD_PER_VIDEO = 1.0
        OPENROUTER_API_KEY = "test-key"

    dependencies = EnrichmentRuntimeDependencies(
        export_input=lambda db, **kwargs: EnrichmentInput(
            schema_version="1", pipeline_version=kwargs["pipeline_version"], episodes=[episode]
        ),
        create_run=lambda db, **kwargs: "run-1",
        finish_run=lambda db, run_id, status, metrics, error=None: finished.append(
            {"run_id": run_id, "status": status, "metrics": metrics, "error": error}
        ),
        generate_episode=lambda episode, config: result,
        persist_candidates=lambda db, episode, result, **kwargs: persisted.append(kwargs)
        or {
            "chapters": 2,
            "labels": 2,
            "assignments": 2,
            "skipped_ungrounded_labels": 0,
        },
    )
    db = _Db()

    metrics = enrich_video_candidates(db, "video-1", config=Config(), dependencies=dependencies)

    assert metrics["model"] == "deepseek/deepseek-v4-pro"
    assert metrics["cost_usd"] == 0.01
    assert persisted == [{"run_id": "run-1"}]
    assert finished[0]["status"] == "completed"
    assert [call[0] for call in db.calls].count("COMMIT") == 2


def test_enrich_video_rejects_results_over_the_cost_limit_before_persistence():
    episode = EpisodeInput(
        video_id="video-1",
        duration_ms=600_000,
        blocks=[
            {
                "block_index": 0,
                "start_ms": 0,
                "end_ms": 600_000,
                "text": "Workers discuss labor organizing and a union vote.",
            }
        ],
    )
    result = OpenRouterEpisodeResult(
        video_id="video-1",
        model="deepseek/deepseek-v4-pro",
        provider="provider",
        prompt_version="prompt-v1",
        candidate=EpisodeEnrichmentCandidate(
            subjects=["labor organizing"],
            keywords=["union vote"],
            categories=[{"slug": "politics", "evidence_block_indexes": [0]}],
            chapters=[
                {
                    "start_ms": 0,
                    "title": "Labor Organizing and Union Voting",
                    "summary": "Workers discuss labor organizing and a union vote.",
                    "evidence_block_indexes": [0],
                },
                {
                    "start_ms": 300_000,
                    "title": "Organizing Strategy and Next Steps",
                    "summary": "The discussion continues with organizing strategy.",
                    "evidence_block_indexes": [0],
                },
            ],
        ),
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.01,
        elapsed_seconds=1.0,
    )
    finished = []
    persisted = []

    class Config:
        ARCHIVE_ENRICHMENT_ENABLED = True
        ARCHIVE_ENRICHMENT_PROVIDER = "openrouter"
        ARCHIVE_ENRICHMENT_MODEL = "deepseek/deepseek-v4-pro"
        ARCHIVE_ENRICHMENT_PUBLISH = False
        ARCHIVE_ENRICHMENT_MAX_COST_USD_PER_VIDEO = 0.005
        OPENROUTER_API_KEY = "test-key"

    dependencies = EnrichmentRuntimeDependencies(
        export_input=lambda db, **kwargs: EnrichmentInput(
            schema_version="1", pipeline_version=kwargs["pipeline_version"], episodes=[episode]
        ),
        create_run=lambda db, **kwargs: "run-1",
        finish_run=lambda db, run_id, status, metrics, error=None: finished.append(
            {"run_id": run_id, "status": status, "metrics": metrics, "error": error}
        ),
        generate_episode=lambda episode, config: result,
        persist_candidates=lambda *args, **kwargs: persisted.append(kwargs) or {},
    )
    db = _Db()

    with pytest.raises(RuntimeError, match="per-video limit"):
        enrich_video_candidates(db, "video-1", config=Config(), dependencies=dependencies)

    assert persisted == []
    assert finished[0]["status"] == "failed"
    assert "per-video limit" in finished[0]["error"]
    assert [call[0] for call in db.calls].count("ROLLBACK") == 1
    assert [call[0] for call in db.calls].count("COMMIT") == 2
