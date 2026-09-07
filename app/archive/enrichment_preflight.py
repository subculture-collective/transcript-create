"""Read-only input checks, shared by queue claims and exact-video enrichment."""

from __future__ import annotations

from typing import Any

from .enrichment_exporter import export_enrichment_input
from .enrichment_runner import EpisodeInput
from .openrouter_enrichment import _balanced_episode_windows


class IneligibleEnrichmentInputError(ValueError):
    """Known source-data defect; never a provider attempt or systemic error."""


def validate_enrichment_input(episode: EpisodeInput, max_window_ms: int) -> None:
    # Use the generation path itself, including clipping at balanced boundaries.
    # Do not catch configuration errors as data defects.
    if max_window_ms <= 0:
        raise ValueError("max enrichment window must be positive")
    if not episode.blocks or any(not block.text.strip() for block in episode.blocks):
        raise IneligibleEnrichmentInputError("empty_transcript")
    try:
        _balanced_episode_windows(episode, max_window_ms)
    except ValueError as exc:
        if str(exc) != "enrichment window contains no transcript blocks":
            raise
        raise IneligibleEnrichmentInputError("empty_balanced_window") from exc
    # A title alone must not make a nearly empty transcript worth a paid attempt.
    # Require the evidence spread used by ordinary sustained-category validation,
    # even for categories whose output validation permits a title/marker shortcut.
    starts = {block.start_ms for block in episode.blocks}
    if len(starts) < 2 or max(starts) - min(starts) < episode.duration_ms * 0.2:
        raise IneligibleEnrichmentInputError("insufficient_category_evidence")


def preflight_video(db: Any, video_id: str, max_window_ms: int) -> None:
    try:
        packet = export_enrichment_input(
            db, pipeline_version="enrichment-input-preflight", sample_size=1, candidate_limit=1, video_ids=[video_id]
        )
    except ValueError as exc:
        if str(exc) != "no exportable transcript blocks were found":
            raise
        raise IneligibleEnrichmentInputError("empty_transcript") from exc
    if len(packet.episodes) != 1:
        raise RuntimeError("expected exactly one preflight episode")
    validate_enrichment_input(packet.episodes[0], max_window_ms)
