from __future__ import annotations

import json
from types import SimpleNamespace

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


@pytest.mark.parametrize("reported", [False, True])
def test_provider_failure_persists_usage_provenance_and_separate_reservation(reported):
    from app.archive.openrouter_enrichment import OpenRouterResponseValidationError

    episode = EpisodeInput(
        video_id="video-1",
        duration_ms=1200000,
        blocks=[
            {"block_index": 0, "start_ms": 0, "end_ms": 600000, "text": "News and politics discussion."},
            {"block_index": 1, "start_ms": 600000, "end_ms": 1200000, "text": "More news and politics."},
        ],
    )
    config = SimpleNamespace(
        ARCHIVE_ENRICHMENT_ENABLED=True,
        ARCHIVE_ENRICHMENT_PROVIDER="openrouter",
        ARCHIVE_ENRICHMENT_MODEL="deepseek/deepseek-v4-pro",
        ARCHIVE_ENRICHMENT_PUBLISH=False,
        ARCHIVE_ENRICHMENT_MAX_COST_USD_PER_VIDEO=1.0,
        OPENROUTER_API_KEY="test",
    )
    failure = OpenRouterResponseValidationError(
        "OpenRouter request failed: response error code 502",
        provider="Alibaba",
        prompt_tokens=10,
        completion_tokens=0,
        cost_usd=0.01,
        elapsed_seconds=10,
        failure_details={"error_code": "502", "transient": True, "usage_reported": reported},
    )
    finished = []
    persisted = []

    def generate(*args):
        raise failure

    deps = EnrichmentRuntimeDependencies(
        export_input=lambda db, **kwargs: EnrichmentInput(
            schema_version="1", pipeline_version="test", episodes=[episode]
        ),
        create_run=lambda *args, **kwargs: "run-1",
        finish_run=lambda db, run_id, status, metrics, error=None: finished.append((status, metrics)),
        generate_episode=generate,
        persist_candidates=lambda *args, **kwargs: persisted.append(True),
    )
    with pytest.raises(OpenRouterResponseValidationError):
        enrich_video_candidates(_Db(), "video-1", config=config, dependencies=deps)
    assert not persisted
    status, metrics = finished[0]
    assert status == "failed" and metrics["cost_usd"] == 0.01
    assert metrics["provider_failure"]["usage_reported"] is reported
    assert metrics.get("cost_reservation_usd", 0) == (0 if reported else 1.0)


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
    assert "status IN ('published', 'hidden', 'rejected')" in conflict_query
    assert "status = 'candidate'" in candidate_delete
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
        "skipped_duplicate_labels": 0,
    }


@pytest.mark.parametrize("auto_approve", [False, True])
def test_enrich_video_generates_v4_pro_candidates_and_records_run(monkeypatch, auto_approve):
    episode = EpisodeInput(
        video_id="video-1",
        duration_ms=600_000,
        blocks=[
            {
                "block_index": 0,
                "start_ms": 0,
                "end_ms": 600_000,
                "text": "Workers discuss labor organizing and a union vote.",
            },
            {"block_index": 1, "start_ms": 300_000, "end_ms": 600_000, "text": "Further organizing discussion."},
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
        category_rejections=[{"slug": "gaming", "reason": "insufficient_evidence_span"}],
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

    approvals = []
    invalidations = []

    def invalidate(video_id):
        assert [call[0] for call in db.calls].count("COMMIT") == 2
        invalidations.append(video_id)
        return True

    def approve(db, run):
        assert persisted and finished[-1]["status"] == "completed"
        approvals.append(run)
        return {"status": "approved", "run_id": run}

    monkeypatch.setattr("app.archive.enrichment_publication.approve_run", approve)
    monkeypatch.setattr("app.archive.enrichment_publication.invalidate_enrichment_views", invalidate)
    config = Config()
    config.ARCHIVE_ENRICHMENT_AUTO_APPROVE = auto_approve
    metrics = enrich_video_candidates(db, "video-1", config=config, dependencies=dependencies)
    assert approvals == (["run-1"] if auto_approve else [])
    assert invalidations == (["video-1"] if auto_approve else [])

    assert metrics["model"] == "deepseek/deepseek-v4-pro"
    assert metrics["cost_usd"] == 0.01
    assert metrics["run_id"] == "run-1"
    assert metrics["repairs"]["category_rejections"] == [{"slug": "gaming", "reason": "insufficient_evidence_span"}]
    assert persisted == [{"run_id": "run-1"}]
    assert finished[0]["status"] == "completed"
    assert [call[0] for call in db.calls].count("COMMIT") == 2


@pytest.mark.parametrize(
    "overlap_violations,error_message",
    [
        (0, "per-video limit"),
        (1, "does not overlap"),
        (0, "no sustained categories"),
        (0, "incomplete chapter coverage"),
        (0, "unsupported chapter evidence"),
    ],
)
def test_enrich_video_rejects_invalid_results_before_persistence(overlap_violations, error_message):
    episode = EpisodeInput(
        video_id="video-1",
        duration_ms=600_000,
        blocks=[
            {
                "block_index": 0,
                "start_ms": 0,
                "end_ms": 600_000,
                "text": "Workers discuss labor organizing and a union vote.",
            },
            {"block_index": 1, "start_ms": 300_000, "end_ms": 600_000, "text": "Further organizing discussion."},
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
    result = result.model_copy(update={"evidence_overlap_violations": overlap_violations})
    if error_message == "no sustained categories":
        result = result.model_copy(update={"candidate": result.candidate.model_copy(update={"categories": []})})
    if error_message == "incomplete chapter coverage":
        result = result.model_copy(update={"window_count": 2})
    if error_message == "unsupported chapter evidence":
        chapters = [
            result.candidate.chapters[0].model_copy(update={"evidence_block_indexes": [999]}),
            result.candidate.chapters[1],
        ]
        result = result.model_copy(update={"candidate": result.candidate.model_copy(update={"chapters": chapters})})

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

    with pytest.raises(RuntimeError, match=error_message) as raised:
        enrich_video_candidates(db, "video-1", config=Config(), dependencies=dependencies)

    assert persisted == []
    assert finished[0]["status"] == "failed"
    assert error_message in finished[0]["error"]
    assert finished[0]["metrics"]["evidence_overlap_violations"] == overlap_violations
    assert finished[0]["metrics"]["cost_usd"] == 0.01
    assert finished[0]["metrics"]["run_id"] == "run-1"
    assert raised.value.archive_enrichment_failure_metrics["run_id"] == "run-1"
    assert finished[0]["metrics"]["prompt_version"] == "archive-episode-enrichment-v7"
    assert [call[0] for call in db.calls].count("ROLLBACK") == 1
    assert [call[0] for call in db.calls].count("COMMIT") == 2
