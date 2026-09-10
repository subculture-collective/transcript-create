from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.archive.enrichment_preflight import IneligibleEnrichmentInputError, validate_enrichment_input
from app.archive.enrichment_runner import EpisodeInput
from app.archive.enrichment_service import EnrichmentRuntimeDependencies, enrich_video_candidates


def episode(duration=5_446_000, starts=(0, 2_723_000)):
    return EpisodeInput(
        video_id="video-1",
        duration_ms=duration,
        blocks=[
            dict(block_index=i, start_ms=start, end_ms=min(start + 120_000, duration), text="Political discussion")
            for i, start in enumerate(starts)
        ],
    )


def test_balanced_boundary_is_used_not_fixed_ninety_minute_chunks():
    validate_enrichment_input(episode(), 5_400_000)
    with pytest.raises(IneligibleEnrichmentInputError, match="empty_balanced_window"):
        validate_enrichment_input(episode(starts=(0, 500_000)), 5_400_000)


def test_sparse_short_input_is_rejected_even_with_category_title():
    short = episode(301_000, (690,)).model_copy(update={"title": "Politics"})
    with pytest.raises(IneligibleEnrichmentInputError, match="insufficient_category_evidence"):
        validate_enrichment_input(short, 5_400_000)


def test_configuration_error_is_not_classified_as_bad_input():
    with pytest.raises(ValueError, match="must be positive") as error:
        validate_enrichment_input(episode(), 0)
    assert not isinstance(error.value, IneligibleEnrichmentInputError)


def test_exact_video_preflight_precedes_run_and_provider():
    create, generate, persist = Mock(), Mock(), Mock()
    config = SimpleNamespace(
        ARCHIVE_ENRICHMENT_ENABLED=True,
        ARCHIVE_ENRICHMENT_PROVIDER="openrouter",
        ARCHIVE_ENRICHMENT_MODEL="deepseek/deepseek-v4-pro",
        ARCHIVE_ENRICHMENT_PUBLISH=False,
        OPENROUTER_API_KEY="test-only",
    )
    deps = EnrichmentRuntimeDependencies(
        export_input=lambda *args, **kwargs: SimpleNamespace(episodes=[episode(starts=(0,))]),
        create_run=create,
        generate_episode=generate,
        persist_candidates=persist,
    )
    with pytest.raises(IneligibleEnrichmentInputError):
        enrich_video_candidates(Mock(), "video-1", config=config, dependencies=deps)
    create.assert_not_called()
    generate.assert_not_called()
    persist.assert_not_called()
