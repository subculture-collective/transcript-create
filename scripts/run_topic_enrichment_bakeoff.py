#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.enrichment_runner import EnrichmentInput, EpisodeInput
from app.archive.labeling.benchmark import PredictionSet
from app.archive.openrouter_enrichment import (
    OpenRouterEpisodeResult,
    OpenRouterResponseValidationError,
    generate_openrouter_episode_enrichment,
)

DEFAULT_MODELS = (
    "google/gemini-2.5-flash",
    "deepseek/deepseek-v4-pro",
    "deepseek/deepseek-v4-flash",
)


def _safe_model_name(model: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", model.casefold()).strip("-")


def _result_from_dict(payload: dict[str, Any]) -> OpenRouterEpisodeResult:
    raw_usage = payload.get("usage")
    usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
    raw_normalizations = payload.get("normalizations")
    normalizations: dict[str, Any] = raw_normalizations if isinstance(raw_normalizations, dict) else {}
    raw_validation = payload.get("validation")
    validation: dict[str, Any] = raw_validation if isinstance(raw_validation, dict) else {}
    return OpenRouterEpisodeResult(
        video_id=str(payload["video_id"]),
        model=str(payload["model"]),
        provider=str(payload.get("provider") or "unknown"),
        prompt_version=str(payload["prompt_version"]),
        candidate=payload["candidate"],
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        cost_usd=float(usage.get("cost_usd") or 0.0),
        elapsed_seconds=float(usage.get("elapsed_seconds") or 0.0),
        first_boundary_normalized=bool(normalizations.get("first_boundary_to_zero", False)),
        summaries_truncated=int(normalizations.get("summaries_truncated") or 0),
        label_values_trimmed=int(normalizations.get("label_values_trimmed") or 0),
        evidence_citations_trimmed=int(normalizations.get("evidence_citations_trimmed") or 0),
        categories_dropped=int(normalizations.get("categories_dropped") or 0),
        evidence_overlap_violations=int(validation.get("evidence_overlap_violations") or 0),
    )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalized_tokens(value: str) -> set[str]:
    stopwords = {"a", "an", "and", "for", "from", "in", "of", "on", "the", "to", "with"}
    return {token for token in re.findall(r"[a-z0-9'-]+", value.casefold()) if token not in stopwords}


def _grounded_rate(labels: list[str], transcript: str) -> float:
    transcript_tokens = _normalized_tokens(transcript)
    if not labels:
        return 0.0
    grounded = sum(bool(tokens := _normalized_tokens(label)) and tokens <= transcript_tokens for label in labels)
    return round(grounded / len(labels), 4)


def _model_metrics(results: list[OpenRouterEpisodeResult], episodes: dict[str, EpisodeInput]) -> dict[str, Any]:
    durations: list[float] = []
    chapter_counts: list[int] = []
    subject_grounding: list[float] = []
    keyword_grounding: list[float] = []
    cited_overlap = 0
    cited_total = 0
    for result in results:
        episode = episodes[result.video_id]
        chapter_counts.append(len(result.candidate.chapters))
        transcript = " ".join(block.text for block in episode.blocks)
        subject_grounding.append(_grounded_rate(result.candidate.subjects, transcript))
        keyword_grounding.append(_grounded_rate(result.candidate.keywords, transcript))
        block_by_index = {block.block_index: block for block in episode.blocks}
        for index, chapter in enumerate(result.candidate.chapters):
            end_ms = (
                result.candidate.chapters[index + 1].start_ms
                if index + 1 < len(result.candidate.chapters)
                else episode.duration_ms
            )
            durations.append((end_ms - chapter.start_ms) / 60_000)
            cited_total += 1
            if any(
                block_by_index[block_index].end_ms > chapter.start_ms and block_by_index[block_index].start_ms < end_ms
                for block_index in chapter.evidence_block_indexes
            ):
                cited_overlap += 1
    elapsed = [result.elapsed_seconds for result in results]
    return {
        "episodes_completed": len(results),
        "chapters_total": sum(chapter_counts),
        "categories_total": sum(len(result.candidate.categories) for result in results),
        "median_chapters_per_episode": statistics.median(chapter_counts) if chapter_counts else 0,
        "median_chapter_minutes": round(statistics.median(durations), 2) if durations else 0.0,
        "subject_lexical_grounding_rate": round(statistics.mean(subject_grounding), 4) if subject_grounding else 0.0,
        "keyword_lexical_grounding_rate": round(statistics.mean(keyword_grounding), 4) if keyword_grounding else 0.0,
        "chapter_evidence_overlap_rate": round(cited_overlap / cited_total, 4) if cited_total else 0.0,
        "prompt_tokens": sum(result.prompt_tokens for result in results),
        "completion_tokens": sum(result.completion_tokens for result in results),
        "cost_usd": round(sum(result.cost_usd for result in results), 6),
        "mean_latency_seconds": round(statistics.mean(elapsed), 2) if elapsed else 0.0,
        "first_boundary_normalizations": sum(result.first_boundary_normalized for result in results),
        "summaries_truncated": sum(result.summaries_truncated for result in results),
        "label_values_trimmed": sum(result.label_values_trimmed for result in results),
        "evidence_citations_trimmed": sum(result.evidence_citations_trimmed for result in results),
        "categories_dropped": sum(result.categories_dropped for result in results),
        "evidence_overlap_violations": sum(result.evidence_overlap_violations for result in results),
    }


def _format_time(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|")


def _build_blind_review(
    models: Sequence[str],
    results_by_model: dict[str, list[OpenRouterEpisodeResult]],
) -> str:
    aliases = {model: f"Model {chr(65 + index)}" for index, model in enumerate(models)}
    lines = [
        "# Topic enrichment model bake-off: blind review",
        "",
        "Model identities are intentionally omitted. Judge useful boundaries, editorial titles, grounded topics, and search terms.",
        "For each model and episode, mark `best`, `acceptable`, or `reject`, then note any hallucination or unsafe title.",
        "",
    ]
    video_ids = list(dict.fromkeys(result.video_id for results in results_by_model.values() for result in results))
    indexed = {model: {result.video_id: result for result in results} for model, results in results_by_model.items()}
    for video_id in video_ids:
        lines.extend([f"## Video `{video_id}`", ""])
        for model in models:
            result = indexed.get(model, {}).get(video_id)
            if result is None:
                lines.extend([f"### {aliases[model]}", "", "Run failed or was not completed.", ""])
                continue
            lines.extend(
                [
                    f"### {aliases[model]}",
                    "",
                    "Verdict: ____",
                    "",
                    f"Categories: {'; '.join(category.slug for category in result.candidate.categories)}",
                    "",
                    f"Subjects: {'; '.join(result.candidate.subjects)}",
                    "",
                    f"Keywords: {'; '.join(result.candidate.keywords)}",
                    "",
                    "| Start | Chapter title |",
                    "| --- | --- |",
                ]
            )
            lines.extend(
                f"| `{_format_time(chapter.start_ms)}` | {_markdown_cell(chapter.title)} |"
                for chapter in result.candidate.chapters
            )
            lines.extend(["", "Notes: ____", ""])
    lines.extend(
        [
            "## Overall ranking",
            "",
            "1. ____",
            "2. ____",
            "3. ____",
            "",
            "Best boundaries: ____",
            "Best titles: ____",
            "Best subjects and keywords: ____",
            "Hallucination or safety concerns: ____",
            "",
        ]
    )
    return "\n".join(lines)


def _select_episodes(packet: EnrichmentInput, video_ids: list[str]) -> list[EpisodeInput]:
    if not video_ids:
        return packet.episodes
    selected = [episode for episode in packet.episodes if episode.video_id in set(video_ids)]
    missing = sorted(set(video_ids) - {episode.video_id for episode in selected})
    if missing:
        raise ValueError(f"unknown requested video IDs: {missing}")
    return selected


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare OpenRouter models on full-episode chapter, subject, and keyword enrichment."
    )
    parser.add_argument("input", type=Path, help="Versioned transcript input JSON")
    parser.add_argument("output_dir", type=Path, help="New directory for evaluation artifacts")
    parser.add_argument("--model", action="append", dest="models", help="OpenRouter model ID; repeat to compare")
    parser.add_argument("--video-id", action="append", default=[], help="Limit the comparison to selected videos")
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--max-observed-cost-usd", type=float, default=10.0)
    parser.add_argument("--allow-provider-fallbacks", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Reuse completed per-episode result files")
    args = parser.parse_args(argv)

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        load_dotenv(REPO_ROOT / ".env")
        api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        parser.error("OPENROUTER_API_KEY must be set in the process environment")
    if args.max_observed_cost_usd <= 0:
        parser.error("--max-observed-cost-usd must be positive")

    with args.input.open(encoding="utf-8") as handle:
        packet = EnrichmentInput.model_validate(json.load(handle))
    episodes = _select_episodes(packet, args.video_id)
    episodes_by_id = {episode.video_id: episode for episode in episodes}
    models = tuple(args.models or DEFAULT_MODELS)
    if len(models) < 2 or len(models) != len(set(models)):
        parser.error("provide at least two unique models")

    if args.output_dir.exists() and not args.resume:
        parser.error("output directory already exists; use --resume or choose a new directory")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    results_by_model: dict[str, list[OpenRouterEpisodeResult]] = {model: [] for model in models}
    errors: list[dict[str, str]] = []
    observed_cost = 0.0

    for episode_index, episode in enumerate(episodes):
        rotated_models = models[episode_index % len(models) :] + models[: episode_index % len(models)]
        for model in rotated_models:
            model_dir = args.output_dir / _safe_model_name(model)
            model_dir.mkdir(exist_ok=True)
            result_path = model_dir / f"{episode.video_id}.json"
            if args.resume and result_path.exists():
                result = _result_from_dict(json.loads(result_path.read_text(encoding="utf-8")))
            else:
                if observed_cost >= args.max_observed_cost_usd:
                    errors.append(
                        {"video_id": episode.video_id, "model": model, "error": "observed cost limit reached"}
                    )
                    continue
                try:
                    result = generate_openrouter_episode_enrichment(
                        episode,
                        api_key=api_key,
                        model=model,
                        timeout_seconds=args.timeout_seconds,
                        allow_provider_fallbacks=args.allow_provider_fallbacks,
                        max_retries=args.max_retries,
                    )
                except OpenRouterResponseValidationError as exc:
                    observed_cost += exc.cost_usd
                    errors.append(
                        {
                            "video_id": episode.video_id,
                            "model": model,
                            "provider": exc.provider,
                            "prompt_tokens": str(exc.prompt_tokens),
                            "completion_tokens": str(exc.completion_tokens),
                            "cost_usd": str(exc.cost_usd),
                            "error": str(exc),
                        }
                    )
                    continue
                except (RuntimeError, ValueError) as exc:
                    errors.append({"video_id": episode.video_id, "model": model, "error": str(exc)})
                    continue
                _write_json(result_path, result.as_dict())
            results_by_model[model].append(result)
            observed_cost += result.cost_usd

    for model, results in results_by_model.items():
        if len(results) != len(episodes):
            continue
        predictions = PredictionSet(
            schema_version=packet.schema_version,
            pipeline_version=f"openrouter-{_safe_model_name(model)}-{results[0].prompt_version}",
            episodes=[result.prediction(episodes_by_id[result.video_id].duration_ms) for result in results],
        )
        _write_json(
            args.output_dir / f"predictions-{_safe_model_name(model)}.json", predictions.model_dump(mode="json")
        )

    aliases = {f"Model {chr(65 + index)}": model for index, model in enumerate(models)}
    report = {
        "schema_version": "1",
        "input": str(args.input),
        "prompt_control": {
            "temperature": 0,
            "reasoning_enabled": False,
            "provider_fallbacks": args.allow_provider_fallbacks,
            "model_order_rotated_by_episode": True,
        },
        "blind_model_key": aliases,
        "models": {model: _model_metrics(results, episodes_by_id) for model, results in results_by_model.items()},
        "errors": errors,
        "observed_cost_usd": round(observed_cost, 6),
    }
    _write_json(args.output_dir / "comparison-report.json", report)
    (args.output_dir / "blind-editorial-review.md").write_text(
        _build_blind_review(models, results_by_model), encoding="utf-8"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
