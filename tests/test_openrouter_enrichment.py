import json
from urllib import error

import pytest

from app.archive.enrichment_runner import EpisodeInput, TranscriptBlockInput
from app.archive.openrouter_enrichment import (
    EPISODE_ENRICHMENT_SCHEMA,
    EpisodeEnrichmentCandidate,
    OpenRouterEpisodeResult,
    build_openrouter_episode_request,
    generate_hierarchical_openrouter_enrichment,
    generate_openrouter_episode_enrichment,
)


def _episode() -> EpisodeInput:
    return EpisodeInput(
        video_id="video-1",
        duration_ms=1_200_000,
        blocks=[
            TranscriptBlockInput(
                block_index=0,
                start_ms=0,
                end_ms=600_000,
                text="The discussion covers labor organizing and a union vote.",
            ),
            TranscriptBlockInput(
                block_index=1,
                start_ms=600_000,
                end_ms=1_200_000,
                text="The conversation turns to housing costs and tenant protections.",
            ),
        ],
    )


def _response_payload() -> dict:
    content = {
        "subjects": ["Labor organizing", "Housing costs"],
        "keywords": ["union vote", "tenant protections"],
        "categories": [{"slug": "politics", "evidence_block_indexes": [0, 1]}],
        "chapters": [
            {
                "start_ms": 0,
                "title": "Labor Organizing and the Union Vote",
                "summary": "The discussion examines labor organizing and an upcoming union vote.",
                "evidence_block_indexes": [0],
            },
            {
                "start_ms": 600_000,
                "title": "Housing Costs and Tenant Protections",
                "summary": "The conversation shifts to housing costs and protections for tenants.",
                "evidence_block_indexes": [1],
            },
        ],
    }
    return {
        "provider": "Test Provider",
        "choices": [{"message": {"content": json.dumps(content)}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.0012},
    }


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def test_build_openrouter_request_uses_identical_strict_controls():
    body = build_openrouter_episode_request(_episode(), model="deepseek/deepseek-v4-pro")

    assert body["model"] == "deepseek/deepseek-v4-pro"
    assert body["temperature"] == 0
    assert body["reasoning"] == {"enabled": False, "exclude": True}
    response_schema = body["response_format"]["json_schema"]
    assert response_schema["name"] == "hasanara_episode_enrichment"
    assert response_schema["strict"] is True
    assert response_schema["schema"] is not EPISODE_ENRICHMENT_SCHEMA
    assert response_schema["schema"]["properties"]["chapters"]["minItems"] == 4
    assert response_schema["schema"]["properties"]["chapters"]["maxItems"] == 8
    assert EPISODE_ENRICHMENT_SCHEMA["properties"]["chapters"]["minItems"] == 2
    assert EPISODE_ENRICHMENT_SCHEMA["properties"]["chapters"]["maxItems"] == 40
    assert response_schema["schema"]["properties"]["categories"]["minItems"] == 0
    evidence_items = response_schema["schema"]["properties"]["chapters"]["items"]["properties"][
        "evidence_block_indexes"
    ]["items"]
    assert evidence_items["maximum"] == 1
    assert (
        "maximum"
        not in EPISODE_ENRICHMENT_SCHEMA["properties"]["chapters"]["items"]["properties"]["evidence_block_indexes"][
            "items"
        ]
    )
    assert body["provider"] == {
        "allow_fallbacks": False,
        "data_collection": "deny",
        "require_parameters": True,
    }
    user = json.loads(body["messages"][1]["content"])
    assert user["target_chapter_count"] == 6
    assert user["category_taxonomy"]["politics"] == "Politics"
    assert "video-game" in user["category_definitions"]["gaming"]
    assert "explicitly named" in user["category_definitions"]["chadvice"]
    assert user["transcript_blocks"][1]["block_index"] == 1


def test_generate_openrouter_enrichment_tracks_usage_and_builds_prediction(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["authorization"] = req.headers["Authorization"]
        captured["timeout"] = timeout
        return _Response(_response_payload())

    monkeypatch.setattr("app.archive.openrouter_enrichment.request.urlopen", fake_urlopen)

    result = generate_openrouter_episode_enrichment(
        _episode(), api_key="secret-key", model="google/gemini-2.5-flash", timeout_seconds=12
    )

    assert captured == {"authorization": "Bearer secret-key", "timeout": 12}
    assert result.provider == "Test Provider"
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 50
    assert result.cost_usd == pytest.approx(0.0012)
    assert result.first_boundary_normalized is False
    prediction = result.prediction(1_200_000)
    assert [(chapter.start_ms, chapter.end_ms) for chapter in prediction.chapters] == [
        (0, 600_000),
        (600_000, 1_200_000),
    ]


def test_generate_openrouter_enrichment_normalizes_first_boundary_to_origin(monkeypatch):
    payload = _response_payload()
    parsed = json.loads(payload["choices"][0]["message"]["content"])
    parsed["chapters"][0]["start_ms"] = 120_000
    payload["choices"][0]["message"]["content"] = json.dumps(parsed)
    monkeypatch.setattr(
        "app.archive.openrouter_enrichment.request.urlopen",
        lambda _req, timeout: _Response(payload),
    )

    result = generate_openrouter_episode_enrichment(_episode(), api_key="key", model="model")

    assert result.first_boundary_normalized is True
    assert result.candidate.chapters[0].start_ms == 0


def test_generate_openrouter_enrichment_orders_and_deduplicates_chapter_boundaries(monkeypatch):
    payload = _response_payload()
    parsed = json.loads(payload["choices"][0]["message"]["content"])
    duplicate = dict(parsed["chapters"][1])
    duplicate["title"] = "Duplicate Boundary Is Removed"
    parsed["chapters"] = [parsed["chapters"][1], duplicate, parsed["chapters"][0]]
    payload["choices"][0]["message"]["content"] = json.dumps(parsed)
    monkeypatch.setattr(
        "app.archive.openrouter_enrichment.request.urlopen",
        lambda _req, timeout: _Response(payload),
    )

    result = generate_openrouter_episode_enrichment(_episode(), api_key="key", model="model")

    assert [chapter.start_ms for chapter in result.candidate.chapters] == [0, 600_000]
    assert result.chapter_boundaries_reordered is True
    assert result.chapter_boundaries_deduplicated == 1
    assert result.as_dict()["normalizations"]["chapter_boundaries_deduplicated"] == 1


def test_generate_openrouter_enrichment_records_nonoverlapping_evidence(monkeypatch):
    payload = _response_payload()
    parsed = json.loads(payload["choices"][0]["message"]["content"])
    parsed["chapters"][1]["evidence_block_indexes"] = [0]
    payload["choices"][0]["message"]["content"] = json.dumps(parsed)
    monkeypatch.setattr(
        "app.archive.openrouter_enrichment.request.urlopen",
        lambda _req, timeout: _Response(payload),
    )

    result = generate_openrouter_episode_enrichment(_episode(), api_key="key", model="model", max_retries=0)

    assert result.evidence_overlap_violations == 1


def test_generate_openrouter_enrichment_truncates_overlong_summaries(monkeypatch):
    payload = _response_payload()
    parsed = json.loads(payload["choices"][0]["message"]["content"])
    parsed["chapters"][0]["summary"] = "word " * 100
    payload["choices"][0]["message"]["content"] = json.dumps(parsed)
    monkeypatch.setattr(
        "app.archive.openrouter_enrichment.request.urlopen",
        lambda _req, timeout: _Response(payload),
    )

    result = generate_openrouter_episode_enrichment(_episode(), api_key="key", model="model")

    assert result.summaries_truncated == 1
    assert len(result.candidate.chapters[0].summary) <= 300


def test_generate_openrouter_enrichment_deduplicates_and_caps_label_lists(monkeypatch):
    payload = _response_payload()
    parsed = json.loads(payload["choices"][0]["message"]["content"])
    parsed["subjects"] = ["Labor", " labor ", *[f"Subject {index}" for index in range(20)]]
    parsed["keywords"] = ["Union Vote", "union   vote", *[f"Keyword {index}" for index in range(30)]]
    payload["choices"][0]["message"]["content"] = json.dumps(parsed)
    monkeypatch.setattr(
        "app.archive.openrouter_enrichment.request.urlopen",
        lambda _req, timeout: _Response(payload),
    )

    result = generate_openrouter_episode_enrichment(_episode(), api_key="key", model="model")

    assert len(result.candidate.subjects) == 12
    assert result.candidate.subjects[:2] == ["Labor", "Subject 0"]
    assert len(result.candidate.keywords) == 24
    assert result.candidate.keywords[:2] == ["Union Vote", "Keyword 0"]
    assert result.label_values_trimmed == 18
    assert result.as_dict()["normalizations"]["label_values_trimmed"] == 18


def test_generate_openrouter_enrichment_trims_excess_evidence_citations(monkeypatch):
    payload = _response_payload()
    parsed = json.loads(payload["choices"][0]["message"]["content"])
    parsed["chapters"][0]["evidence_block_indexes"] = [0, 1, 0, 1]
    payload["choices"][0]["message"]["content"] = json.dumps(parsed)
    monkeypatch.setattr(
        "app.archive.openrouter_enrichment.request.urlopen",
        lambda _req, timeout: _Response(payload),
    )

    result = generate_openrouter_episode_enrichment(_episode(), api_key="key", model="model")

    assert result.candidate.chapters[0].evidence_block_indexes == [0, 1]
    assert result.evidence_citations_trimmed == 2
    assert result.as_dict()["normalizations"]["evidence_citations_trimmed"] == 2


def test_generate_openrouter_enrichment_rejects_unknown_category_evidence(monkeypatch):
    payload = _response_payload()
    parsed = json.loads(payload["choices"][0]["message"]["content"])
    parsed["categories"][0]["evidence_block_indexes"] = [99]
    payload["choices"][0]["message"]["content"] = json.dumps(parsed)
    monkeypatch.setattr(
        "app.archive.openrouter_enrichment.request.urlopen",
        lambda _req, timeout: _Response(payload),
    )

    with pytest.raises(ValueError, match="category cites an unknown transcript block"):
        generate_openrouter_episode_enrichment(_episode(), api_key="key", model="model")


def test_generate_openrouter_enrichment_drops_category_without_sustained_evidence(monkeypatch):
    payload = _response_payload()
    parsed = json.loads(payload["choices"][0]["message"]["content"])
    parsed["categories"] = [
        {"slug": "gaming", "evidence_block_indexes": [0]},
        {"slug": "politics", "evidence_block_indexes": [0, 1]},
    ]
    payload["choices"][0]["message"]["content"] = json.dumps(parsed)
    monkeypatch.setattr(
        "app.archive.openrouter_enrichment.request.urlopen",
        lambda _req, timeout: _Response(payload),
    )

    result = generate_openrouter_episode_enrichment(_episode(), api_key="key", model="model")

    assert [category.slug for category in result.candidate.categories] == ["politics"]
    assert result.categories_dropped == 1
    assert result.as_dict()["normalizations"]["categories_dropped"] == 1


def test_generate_openrouter_enrichment_retries_transient_http_errors(monkeypatch):
    attempts = 0

    def fake_urlopen(_req, timeout):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise error.HTTPError("https://example.test", 503, "busy", {}, None)
        return _Response(_response_payload())

    monkeypatch.setattr("app.archive.openrouter_enrichment.request.urlopen", fake_urlopen)
    monkeypatch.setattr("app.archive.openrouter_enrichment.time.sleep", lambda _seconds: None)

    generate_openrouter_episode_enrichment(_episode(), api_key="key", model="model", max_retries=1)

    assert attempts == 2


def test_generate_openrouter_enrichment_requires_key():
    with pytest.raises(ValueError, match="API key"):
        generate_openrouter_episode_enrichment(_episode(), api_key="", model="model")


def test_hierarchical_enrichment_bounds_windows_and_recombines_episode():
    duration_ms = 200 * 60_000
    episode = EpisodeInput(
        video_id="long-video",
        title="A long mixed-topic VOD",
        duration_ms=duration_ms,
        transcript_source="youtube",
        transcript_coverage=0.98,
        transcript_selection_reason="youtube_higher_coverage_quality",
        blocks=[
            TranscriptBlockInput(
                block_index=index,
                start_ms=index * 10 * 60_000,
                end_ms=(index + 1) * 10 * 60_000,
                text=f"Discussion block {index} about topic {index // 4}.",
            )
            for index in range(20)
        ],
    )
    window_durations: list[int] = []

    def generate_window(window: EpisodeInput) -> OpenRouterEpisodeResult:
        window_durations.append(window.duration_ms)
        assert window.title == episode.title
        assert window.transcript_source == episode.transcript_source
        assert window.transcript_coverage == episode.transcript_coverage
        assert window.transcript_selection_reason == episode.transcript_selection_reason
        midpoint = window.duration_ms // 2
        return OpenRouterEpisodeResult(
            video_id=window.video_id,
            model="deepseek/deepseek-v4-pro",
            provider="provider",
            prompt_version="prompt-v1",
            candidate=EpisodeEnrichmentCandidate(
                subjects=["Topic"],
                keywords=["discussion topic"],
                categories=[{"slug": "politics", "evidence_block_indexes": [window.blocks[0].block_index]}],
                chapters=[
                    {
                        "start_ms": 0,
                        "title": "First Topic in This Window",
                        "summary": "The first portion discusses one sustained topic.",
                        "evidence_block_indexes": [window.blocks[0].block_index],
                    },
                    {
                        "start_ms": midpoint,
                        "title": "Second Topic in This Window",
                        "summary": "The second portion discusses another sustained topic.",
                        "evidence_block_indexes": [window.blocks[-1].block_index],
                    },
                ],
            ),
            prompt_tokens=100,
            completion_tokens=20,
            cost_usd=0.01,
            elapsed_seconds=1.0,
        )

    result = generate_hierarchical_openrouter_enrichment(
        episode,
        generate_window=generate_window,
        max_window_ms=90 * 60_000,
    )

    assert len(window_durations) == 3
    assert max(window_durations) <= 90 * 60_000
    prediction = result.prediction(duration_ms)
    assert prediction.chapters[0].start_ms == 0
    assert prediction.chapters[-1].end_ms == duration_ms
    assert all(
        chapter.end_ms == prediction.chapters[index + 1].start_ms
        for index, chapter in enumerate(prediction.chapters[:-1])
    )
    assert result.window_count == 3
    assert result.cost_usd == pytest.approx(0.03)
