import json

from app.archive.openrouter_enrichment import EpisodeEnrichmentCandidate, OpenRouterEpisodeResult
from scripts.run_topic_enrichment_bakeoff import main


def _input_packet() -> dict:
    return {
        "schema_version": "1",
        "pipeline_version": "pilot-v1",
        "episodes": [
            {
                "video_id": "video-1",
                "duration_ms": 1_200_000,
                "blocks": [
                    {
                        "block_index": 0,
                        "start_ms": 0,
                        "end_ms": 600_000,
                        "text": "Labor organizing and a union vote are discussed.",
                    },
                    {
                        "block_index": 1,
                        "start_ms": 600_000,
                        "end_ms": 1_200_000,
                        "text": "Housing costs and tenant protections are discussed.",
                    },
                ],
            }
        ],
    }


def _result(model: str) -> OpenRouterEpisodeResult:
    return OpenRouterEpisodeResult(
        video_id="video-1",
        model=model,
        provider="provider",
        prompt_version="prompt-v1",
        candidate=EpisodeEnrichmentCandidate(
            subjects=["Labor organizing", "Housing costs"],
            keywords=["union vote", "tenant protections"],
            categories=[{"slug": "politics", "evidence_block_indexes": [0]}],
            chapters=[
                {
                    "start_ms": 0,
                    "title": "Labor Organizing and Union Voting",
                    "summary": "A discussion of labor organizing and union voting.",
                    "evidence_block_indexes": [0],
                },
                {
                    "start_ms": 600_000,
                    "title": "Housing Costs and Tenant Protections",
                    "summary": "A discussion of housing costs and tenant protections.",
                    "evidence_block_indexes": [1],
                },
            ],
        ),
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.01,
        elapsed_seconds=2.0,
        first_boundary_normalized=True,
        summaries_truncated=1,
        label_values_trimmed=2,
        evidence_overlap_violations=0,
    )


def test_bakeoff_cli_writes_predictions_metrics_and_blind_review(tmp_path, monkeypatch):
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(_input_packet()))
    output_dir = tmp_path / "results"
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    monkeypatch.setattr(
        "scripts.run_topic_enrichment_bakeoff.generate_openrouter_episode_enrichment",
        lambda episode, *, model, **_kwargs: _result(model),
    )

    exit_code = main(
        [
            str(input_path),
            str(output_dir),
            "--model",
            "model/one",
            "--model",
            "model/two",
        ]
    )

    assert exit_code == 0
    report = json.loads((output_dir / "comparison-report.json").read_text())
    assert report["observed_cost_usd"] == 0.02
    assert report["blind_model_key"] == {"Model A": "model/one", "Model B": "model/two"}
    assert report["models"]["model/one"]["chapter_evidence_overlap_rate"] == 1.0
    assert report["models"]["model/one"]["categories_total"] == 1
    assert report["models"]["model/one"]["first_boundary_normalizations"] == 1
    assert report["models"]["model/one"]["summaries_truncated"] == 1
    assert report["models"]["model/one"]["label_values_trimmed"] == 2
    assert report["models"]["model/one"]["evidence_overlap_violations"] == 0
    assert report["models"]["model/one"]["categories_dropped"] == 0
    predictions = json.loads((output_dir / "predictions-model-one.json").read_text())
    assert predictions["episodes"][0]["chapters"][-1]["end_ms"] == 1_200_000
    review = (output_dir / "blind-editorial-review.md").read_text()
    assert "model/one" not in review
    assert "Model A" in review
    assert "Categories: politics" in review


def test_bakeoff_cli_resumes_without_api_calls(tmp_path, monkeypatch):
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(_input_packet()))
    output_dir = tmp_path / "results"
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    monkeypatch.setattr(
        "scripts.run_topic_enrichment_bakeoff.generate_openrouter_episode_enrichment",
        lambda episode, *, model, **_kwargs: _result(model),
    )
    args = [str(input_path), str(output_dir), "--model", "model/one", "--model", "model/two"]
    assert main(args) == 0

    monkeypatch.setattr(
        "scripts.run_topic_enrichment_bakeoff.generate_openrouter_episode_enrichment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected API call")),
    )

    assert main([*args, "--resume"]) == 0
