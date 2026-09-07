from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import text

from app.settings import settings

from .enrichment_exporter import export_enrichment_input
from .enrichment_preflight import validate_enrichment_input
from .enrichment_queue import OWNER_LOCK
from .enrichment_runner import EpisodeInput
from .labeling.normalization import slugify_label
from .labeling.repository import (
    create_extraction_run,
    finish_extraction_run,
    insert_assignment,
    upsert_label_candidate,
)
from .openrouter_enrichment import (
    CATEGORY_LABELS,
    PROMPT_VERSION,
    OpenRouterEpisodeResult,
    generate_hierarchical_openrouter_enrichment,
    generate_openrouter_episode_enrichment,
)


@dataclass(frozen=True)
class EnrichmentPersistenceDependencies:
    upsert_label: Callable[..., str] = upsert_label_candidate
    insert_assignment: Callable[..., str] = insert_assignment


@dataclass(frozen=True)
class EnrichmentRuntimeDependencies:
    export_input: Callable[..., Any] = export_enrichment_input
    create_run: Callable[..., str] = create_extraction_run
    finish_run: Callable[..., None] = finish_extraction_run
    generate_episode: Callable[[EpisodeInput, Any], OpenRouterEpisodeResult] | None = None
    persist_candidates: Callable[..., dict[str, int]] | None = None


def validate_generated_candidates(episode: EpisodeInput, result: OpenRouterEpisodeResult, config: Any) -> None:
    """Acceptance is a transaction gate, not an optional wrapper audit."""
    if result.evidence_overlap_violations:
        raise RuntimeError("archive enrichment chapter evidence does not overlap its chapter")
    if not result.candidate.categories:
        raise RuntimeError("archive enrichment quality gate: no sustained categories")
    chapters = result.candidate.chapters
    starts = [chapter.start_ms for chapter in chapters]
    windows = max(
        1, math.ceil(episode.duration_ms / (getattr(config, "ARCHIVE_ENRICHMENT_MAX_WINDOW_MINUTES", 90) * 60_000))
    )
    expected = {round(index * episode.duration_ms / windows) for index in range(windows)}
    if result.window_count != windows or not expected <= set(starts) or starts != sorted(set(starts)):
        raise RuntimeError("archive enrichment quality gate: incomplete chapter coverage")
    blocks = {block.block_index: block for block in episode.blocks}
    for index, chapter in enumerate(chapters):
        end = starts[index + 1] if index + 1 < len(starts) else episode.duration_ms
        citations = chapter.evidence_block_indexes
        if not 0 <= chapter.start_ms < end <= episode.duration_ms or not citations:
            raise RuntimeError("archive enrichment quality gate: invalid chapter interval or evidence")
        if any(citation not in blocks for citation in citations) or not any(
            blocks[citation].end_ms > chapter.start_ms and blocks[citation].start_ms < end for citation in citations
        ):
            raise RuntimeError("archive enrichment quality gate: unsupported chapter evidence")
    if not math.isfinite(result.cost_usd) or result.cost_usd < 0:
        raise RuntimeError("archive enrichment quality gate: invalid measured cost")


def require_pristine_video(db: Any, video_id: str) -> None:
    # The chapter-review API also locks this video row. Recheck under that lock
    # after HTTP generation, so a review action during a paid request wins.
    db.execute(text("SELECT id FROM videos WHERE id=:video_id FOR UPDATE"), {"video_id": video_id})
    conflict = db.execute(
        text("""
        SELECT EXISTS (SELECT 1 FROM archive_video_chapters WHERE video_id=:video_id)
            OR EXISTS (SELECT 1 FROM archive_label_assignments WHERE video_id=:video_id AND source='llm')
            OR EXISTS (SELECT 1 FROM archive_chapter_feedback WHERE video_id=:video_id)
    """),
        {"video_id": video_id},
    ).scalar_one()
    if conflict:
        raise ValueError("video is no longer pristine; existing review work is protected")


def validate_stored_candidates(db: Any, video_id: str, run_id: str, metrics: dict[str, Any]) -> None:
    stored = (
        db.execute(
            text("""
        SELECT
          (SELECT count(*) FROM archive_video_chapters WHERE video_id=:video AND run_id=:run) chapters,
          (SELECT count(*) FROM archive_label_assignments WHERE video_id=:video AND run_id=:run) assignments,
          (SELECT count(DISTINCT label_id) FROM archive_label_assignments WHERE video_id=:video AND run_id=:run) labels,
          (SELECT count(*) FROM archive_label_assignments WHERE video_id=:video AND run_id=:run
            AND evidence->0->>'extractor'='llm_category'
            AND (component_scores->>'controlled_taxonomy')::numeric=1) categories,
          NOT EXISTS (SELECT 1 FROM archive_video_chapters WHERE video_id=:video AND run_id=:run
                       AND (status<>'candidate' OR source<>'automatic'))
          AND NOT EXISTS (SELECT 1 FROM archive_label_assignments WHERE video_id=:video AND run_id=:run
                       AND (status<>'candidate' OR source<>'llm' OR publish_tier<>'bronze')) review_only
    """),
            {"video": video_id, "run": run_id},
        )
        .mappings()
        .one()
    )
    if (
        not stored["review_only"]
        or not stored["categories"]
        or any(stored[key] != metrics[key] for key in ("chapters", "assignments", "labels", "categories"))
    ):
        raise RuntimeError("archive enrichment quality gate: stored candidates do not match generation metrics")


_LABEL_STOPWORDS = {"a", "an", "and", "for", "from", "in", "of", "on", "the", "to", "with"}


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9'-]+", value.casefold()) if token not in _LABEL_STOPWORDS}


def _grounded_label_evidence(
    label: str,
    episode: EpisodeInput,
    result: OpenRouterEpisodeResult,
) -> list[dict[str, Any]]:
    label_tokens = _tokens(label)
    if not label_tokens:
        return []
    cited_indexes = list(
        dict.fromkeys(
            block_index for chapter in result.candidate.chapters for block_index in chapter.evidence_block_indexes
        )
    )
    block_by_index = {block.block_index: block for block in episode.blocks}
    evidence = []
    for block_index in cited_indexes:
        block = block_by_index.get(block_index)
        if block is None or not label_tokens <= _tokens(block.text):
            continue
        evidence.append(
            {
                "extractor": "llm",
                "video_id": episode.video_id,
                "block_index": block.block_index,
                "start_ms": block.start_ms,
                "end_ms": block.end_ms,
                "text": block.text[:500],
                "model": result.model,
                "prompt_version": result.prompt_version,
            }
        )
        if len(evidence) == 3:
            break
    return evidence


def _extract_id(row: Any) -> str:
    if row is None:
        raise RuntimeError("chapter insert did not return an id")
    if hasattr(row, "_mapping") and "id" in row._mapping:
        return str(row._mapping["id"])
    if isinstance(row, dict) and "id" in row:
        return str(row["id"])
    return str(row[0])


def persist_enrichment_candidates(
    db: Any,
    episode: EpisodeInput,
    result: OpenRouterEpisodeResult,
    *,
    run_id: str,
    dependencies: EnrichmentPersistenceDependencies | None = None,
) -> dict[str, int]:
    """Replace automatic review candidates without touching curated chapters."""
    deps = dependencies or EnrichmentPersistenceDependencies()
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:video_id))"),
        {"video_id": episode.video_id},
    )
    db.execute(text("SELECT id FROM videos WHERE id=:video_id FOR UPDATE"), {"video_id": episode.video_id})
    conflicts = db.execute(
        text("""
            SELECT COUNT(*)
            FROM archive_video_chapters
            WHERE video_id = :video_id
              AND (source <> 'automatic' OR status IN ('published', 'hidden', 'rejected'))
            """),
        {"video_id": episode.video_id},
    ).scalar_one()
    if int(conflicts or 0) > 0:
        raise ValueError("video already has curated or moderated chapters")

    db.execute(
        text("""
            DELETE FROM archive_video_chapters
            WHERE video_id = :video_id
              AND source = 'automatic'
              AND status = 'candidate'
            """),
        {"video_id": episode.video_id},
    )
    for index, chapter in enumerate(result.candidate.chapters):
        end_ms = (
            result.candidate.chapters[index + 1].start_ms
            if index + 1 < len(result.candidate.chapters)
            else episode.duration_ms
        )
        block_by_index = {block.block_index: block for block in episode.blocks}
        chapter_evidence = [
            {
                "block_index": block.block_index,
                "start_ms": block.start_ms,
                "end_ms": block.end_ms,
                "text": block.text[:500],
            }
            for block_index in chapter.evidence_block_indexes
            if (block := block_by_index.get(block_index)) is not None
        ]
        _extract_id(
            db.execute(
                text("""
                    INSERT INTO archive_video_chapters (
                        video_id, chapter_index, start_ms, end_ms, title, summary,
                        confidence_score, status, source, run_id, evidence,
                        pipeline_version, model_name, prompt_version, transcript_source,
                        created_at, updated_at
                    ) VALUES (
                        :video_id, :chapter_index, :start_ms, :end_ms, :title, :summary,
                        :confidence_score, :status, :source, :run_id, CAST(:evidence AS jsonb),
                        :pipeline_version, :model_name, :prompt_version, :transcript_source,
                        now(), now()
                    )
                    RETURNING id
                    """),
                {
                    "video_id": episode.video_id,
                    "chapter_index": index,
                    "start_ms": chapter.start_ms,
                    "end_ms": end_ms,
                    "title": chapter.title,
                    "summary": chapter.summary,
                    "confidence_score": 0.75,
                    "status": "candidate",
                    "source": "automatic",
                    "run_id": run_id,
                    "evidence": json.dumps(chapter_evidence),
                    "pipeline_version": f"grounded-episode-enrichment:{result.prompt_version}",
                    "model_name": result.model,
                    "prompt_version": result.prompt_version,
                    "transcript_source": episode.transcript_source,
                },
            ).first()
        )

    metrics = {
        "chapters": len(result.candidate.chapters),
        "categories": 0,
        "labels": 0,
        "assignments": 0,
        "skipped_ungrounded_labels": 0,
        "skipped_duplicate_labels": 0,
    }
    assigned_slugs: set[str] = set()
    block_by_index = {block.block_index: block for block in episode.blocks}
    for category in result.candidate.categories:
        evidence = [
            {
                "extractor": "llm_category",
                "video_id": episode.video_id,
                "block_index": block.block_index,
                "start_ms": block.start_ms,
                "end_ms": block.end_ms,
                "text": block.text[:500],
                "model": result.model,
                "prompt_version": result.prompt_version,
            }
            for block_index in category.evidence_block_indexes
            if (block := block_by_index.get(block_index)) is not None
        ]
        label_id = deps.upsert_label(
            db,
            label=CATEGORY_LABELS[category.slug],
            kind="category",
            aliases=[],
            confidence_score=0.75,
            source="automatic",
            publish_tier="bronze",
            status="candidate",
            run_id=run_id,
        )
        deps.insert_assignment(
            db,
            label_id=label_id,
            video_id=episode.video_id,
            unit_type="vod",
            status="candidate",
            publish_tier="bronze",
            confidence_score=0.75,
            evidence=evidence,
            source="llm",
            run_id=run_id,
            component_scores={"controlled_taxonomy": 1.0, "llm_grounded": 1.0},
        )
        metrics["categories"] += 1
        metrics["labels"] += 1
        metrics["assignments"] += 1
        assigned_slugs.add(slugify_label(CATEGORY_LABELS[category.slug]))
    labels = [*result.candidate.subjects, *result.candidate.keywords]
    for label in labels:
        slug = slugify_label(label)
        if slug in assigned_slugs:
            # Categories own their assignment identity. Do not even upsert the
            # label: that could demote an automatic category to kind='topic'.
            # Use the repository's slug normalization, not display-string equality.
            metrics["skipped_duplicate_labels"] += 1
            continue
        evidence = _grounded_label_evidence(label, episode, result)
        if not evidence:
            metrics["skipped_ungrounded_labels"] += 1
            continue
        label_id = deps.upsert_label(
            db,
            label=label,
            kind="topic",
            aliases=[],
            confidence_score=0.75,
            source="automatic",
            publish_tier="bronze",
            status="candidate",
            run_id=run_id,
        )
        deps.insert_assignment(
            db,
            label_id=label_id,
            video_id=episode.video_id,
            unit_type="vod",
            status="candidate",
            publish_tier="bronze",
            confidence_score=0.75,
            evidence=evidence,
            source="llm",
            run_id=run_id,
            component_scores={"llm_grounded": 1.0},
        )
        metrics["labels"] += 1
        metrics["assignments"] += 1
        assigned_slugs.add(slug)
    return metrics


def _generate_configured_episode(episode: EpisodeInput, config: Any) -> OpenRouterEpisodeResult:
    def generate_window(window: EpisodeInput) -> OpenRouterEpisodeResult:
        return generate_openrouter_episode_enrichment(
            window,
            api_key=config.OPENROUTER_API_KEY,
            model=config.ARCHIVE_ENRICHMENT_MODEL,
            timeout_seconds=config.ARCHIVE_ENRICHMENT_TIMEOUT_SECONDS,
            allow_provider_fallbacks=False,
            defer_category_sustained_validation=True,
        )

    return generate_hierarchical_openrouter_enrichment(
        episode,
        generate_window=generate_window,
        max_window_ms=int(config.ARCHIVE_ENRICHMENT_MAX_WINDOW_MINUTES * 60_000),
        max_cost_usd=float(config.ARCHIVE_ENRICHMENT_MAX_COST_USD_PER_VIDEO),
    )


def _validate_runtime_config(config: Any) -> None:
    if not config.ARCHIVE_ENRICHMENT_ENABLED:
        raise ValueError("archive enrichment is disabled")
    if config.ARCHIVE_ENRICHMENT_PROVIDER != "openrouter":
        raise ValueError("archive enrichment provider must be openrouter")
    if config.ARCHIVE_ENRICHMENT_PUBLISH:
        raise ValueError("model enrichment may only write review candidates")
    if not str(config.ARCHIVE_ENRICHMENT_MODEL).strip():
        raise ValueError("archive enrichment model is required")
    if not str(getattr(config, "OPENROUTER_API_KEY", "")).strip():
        raise ValueError("OpenRouter API key is required")


def enrich_video_candidates(
    db: Any,
    video_id: str,
    *,
    config: Any = settings,
    dependencies: EnrichmentRuntimeDependencies | None = None,
) -> dict[str, Any]:
    """Generate and persist review-only enrichment candidates for one video."""
    _validate_runtime_config(config)
    deps = dependencies or EnrichmentRuntimeDependencies()
    generate_episode = deps.generate_episode or _generate_configured_episode
    persist_candidates = deps.persist_candidates or persist_enrichment_candidates
    if dependencies is None:
        owner = db.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:owner))"), {"owner": OWNER_LOCK}
        ).scalar_one()
        running = db.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM archive_extraction_runs WHERE status='running' AND model_name IS NOT NULL)"
            )
        ).scalar_one()
        if not owner or running:
            raise ValueError("another enrichment owner or extraction run is active")
        require_pristine_video(db, video_id)
    packet = deps.export_input(
        db,
        pipeline_version=f"openrouter:{config.ARCHIVE_ENRICHMENT_MODEL}",
        sample_size=1,
        candidate_limit=1,
        video_ids=[video_id],
    )
    if len(packet.episodes) != 1:
        raise ValueError("expected exactly one enrichment episode")
    episode = packet.episodes[0]
    validate_enrichment_input(episode, int(getattr(config, "ARCHIVE_ENRICHMENT_MAX_WINDOW_MINUTES", 90) * 60_000))
    run_id = deps.create_run(
        db,
        scope="video",
        extraction_tier="premium",
        video_id=video_id,
        model_name=config.ARCHIVE_ENRICHMENT_MODEL,
        prompt_version=PROMPT_VERSION,
    )
    db.commit()

    try:
        result = generate_episode(episode, config)
        validate_generated_candidates(episode, result, config)
        if result.cost_usd > config.ARCHIVE_ENRICHMENT_MAX_COST_USD_PER_VIDEO:
            raise RuntimeError(
                "archive enrichment cost exceeded the configured per-video limit "
                f"({result.cost_usd:.6f} > {config.ARCHIVE_ENRICHMENT_MAX_COST_USD_PER_VIDEO:.6f})"
            )
        if dependencies is None:
            require_pristine_video(db, video_id)
        metrics: dict[str, Any] = persist_candidates(db, episode, result, run_id=run_id)
        if dependencies is None:
            validate_stored_candidates(db, video_id, run_id, metrics)
        metrics.update(
            {
                "run_id": run_id,
                "model": result.model,
                "provider": result.provider,
                "prompt_version": result.prompt_version,
                "window_count": result.window_count,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "cost_usd": result.cost_usd,
                "elapsed_seconds": result.elapsed_seconds,
                "repairs": {
                    "first_boundary_normalized": result.first_boundary_normalized,
                    "summaries_truncated": result.summaries_truncated,
                    "label_values_trimmed": result.label_values_trimmed,
                    "evidence_citations_trimmed": result.evidence_citations_trimmed,
                    "chapter_boundaries_reordered": result.chapter_boundaries_reordered,
                    "chapter_boundaries_deduplicated": result.chapter_boundaries_deduplicated,
                    "chapter_boundaries_realigned": result.chapter_boundaries_realigned,
                    "categories_dropped": result.categories_dropped,
                    "category_rejections": result.category_rejections,
                    "evidence_overlap_violations": result.evidence_overlap_violations,
                },
            }
        )
        deps.finish_run(db, run_id, "completed", metrics)
        db.commit()
        return metrics
    except Exception as exc:
        db.rollback()
        failure_metrics: dict[str, Any] = {
            "run_id": run_id,
            "model": config.ARCHIVE_ENRICHMENT_MODEL,
            "prompt_version": PROMPT_VERSION,
        }
        usage_source: Any = result if "result" in locals() else exc
        for field in (
            "provider",
            "prompt_tokens",
            "completion_tokens",
            "cost_usd",
            "elapsed_seconds",
            "window_count",
            "attempted_window_count",
            "evidence_overlap_violations",
            "chapter_boundaries_realigned",
        ):
            value = getattr(usage_source, field, None)
            if value is not None:
                failure_metrics[field] = value
        deps.finish_run(
            db,
            run_id,
            "failed",
            failure_metrics,
            error=str(exc)[:1_000],
        )
        db.commit()
        exc.__dict__["archive_enrichment_failure_metrics"] = failure_metrics
        raise


__all__ = [
    "EnrichmentPersistenceDependencies",
    "EnrichmentRuntimeDependencies",
    "enrich_video_candidates",
    "persist_enrichment_candidates",
]
