# Topic enrichment benchmark

The benchmark is an offline release gate. It does not write archive labels or chapters.

Run it from the repository root:

```bash
./.venv/bin/python scripts/evaluate_topic_enrichment.py golden-v1.json predictions.json
```

The command prints a JSON report and exits `0` when the release gates pass or `1` when they fail. Add `--output report.json` to retain the report as CI evidence.

## Golden-set contract

The top-level object uses `schema_version: "1"` and an `episodes` array. Each episode contains:

- `video_id` and `duration_ms`;
- editor-approved `subjects`;
- `acceptable_keywords`, `junk_subjects`, and `junk_keywords` error slices;
- ordered chapters beginning at zero, each with an editor title and an evidence timestamp.

Unknown fields, duplicate videos, unordered boundaries, out-of-duration evidence, and unsupported schema versions are rejected.

## Prediction contract

Predictions use `schema_version: "1"`, a reproducible `pipeline_version`, and exactly the same video IDs as the golden set. Every episode contains ranked `subjects`, ranked `keywords`, and contiguous full-origin chapters.

The report includes per-episode and macro-average subject precision/recall, keyword precision/recall and junk rate, chapter-boundary F1, duration coverage, and fragment-title rate. Publication remains disabled until the gated metrics in `app/archive/labeling/benchmark.py` pass on the representative golden set.

## Semantic chapter proposals

`app.archive.semantic_chapters.propose_semantic_chapters` accepts ordered transcript windows plus one embedding per window. It detects sustained cosine-distance changes, enforces chapter-duration constraints, covers the complete supplied duration, and returns evidence-window indexes. It deliberately does not name, persist, or publish chapters; grounded naming and persistence are later gated stages.

## Grounded naming and episode rollups

`app.archive.chapter_naming` sends one semantic span at a time to Ollama using temperature zero, thinking disabled, and a strict JSON schema. Every result is validated after generation:

- citations must resolve to transcript windows inside the span;
- subjects and keywords must be lexically grounded in the cited evidence;
- editorial chapter titles may paraphrase only through a small explicit vocabulary;
- unsupported named terms and numbers are rejected;
- invalid semantic output never becomes a prediction; offline generation substitutes a traceable transcript-extractive title with no subjects or keywords and emits a warning for quality accounting.

`app.archive.enrichment_predictions.generate_episode_prediction` joins semantic proposals to a supplied grounded naming function. Episode subjects and keywords are deduplicated and ranked by the duration of the chapters they cover, so sustained subjects outrank isolated mentions. The result uses the same `EpisodePrediction` contract consumed by the benchmark and still performs no database writes.

## Offline prediction command

Create a representative, read-only transcript packet from the application database:

```bash
./.venv/bin/python scripts/export_topic_enrichment_input.py \
  transcript-input-v1.json \
  --pipeline-version semantic-qwen-v1
```

By default the exporter selects 30 recent videos of at least 30 minutes, taking up to five from each of six formats: politics/news, interviews, gaming, reaction content, recurring segments, and long mixed streams. If a format is undersupplied, the newest remaining candidates fill the packet. Change the floor with `--minimum-duration-minutes`. To export a deliberate review set instead, repeat `--video-id`; explicit selections bypass the duration floor:

```bash
./.venv/bin/python scripts/export_topic_enrichment_input.py \
  transcript-input-v1.json \
  --pipeline-version semantic-qwen-v1 \
  --video-id VIDEO_UUID_1 \
  --video-id VIDEO_UUID_2
```

The exporter performs only `SELECT` queries and closes its database session without committing. Its output is intentionally limited to video IDs, durations, and transcript block indexes, times, and cleaned text. It does not export users, jobs, speaker labels, media paths, or session data.

Generate predictions from that packet:

```bash
./.venv/bin/python scripts/generate_topic_enrichment_predictions.py \
  transcript-input-v1.json predictions.json \
  --ollama-url http://localhost:11434
```

The versioned input contains `pipeline_version` plus episodes with `video_id`, `duration_ms`, and ordered transcript blocks (`block_index`, `start_ms`, `end_ms`, and `text`). Unknown fields, duplicate videos or block indexes, invalid ranges, and out-of-duration blocks are rejected.

The command builds overlapping two-minute windows with a one-minute stride by default. It embeds every episode in ordered batches with `qwen3-embedding:0.6b`, validates response count, dimensions, numeric values, and ordering, then names all semantic spans with `qwen3:8b`. The two-phase order avoids repeatedly loading the embedding and naming models on memory-constrained hosts. Both models and segmentation thresholds are configurable. Output is directly consumable by `evaluate_topic_enrichment.py` and no application database is imported or modified.

## OpenRouter full-episode bake-off

The OpenRouter bake-off evaluates complete enrichment behavior rather than reusing local semantic boundaries. Each model independently chooses chapter starts, titles, subjects, keywords, and zero to three categories from the fixed archive taxonomy using the same timestamped transcript packet. The command performs no database writes and does not publish its results.

Provide the key only in the command environment, then run:

```bash
OPENROUTER_API_KEY=... ./.venv/bin/python scripts/run_topic_enrichment_bakeoff.py \
  data/topic-enrichment/pilot-transcripts-v1.json \
  data/topic-enrichment/openrouter-bakeoff-v1
```

The default contenders are pinned to:

- `google/gemini-2.5-flash`;
- `deepseek/deepseek-v4-pro`;
- `deepseek/deepseek-v4-flash`.

The runner uses the same prompt, strict JSON Schema, temperature zero, and disabled reasoning for all contenders. The per-episode schema permits two chapters below or above the duration-derived target, preventing severe over-segmentation while leaving room for editorial structure. It rotates request order by episode to reduce timing bias, refuses data-collection providers, requires structured-output support, disables provider fallback by default, and stops scheduling new calls once `--max-observed-cost-usd` is reached. OpenRouter's reported provider, token counts, cost, and latency are retained with every episode result.

If `OPENROUTER_API_KEY` is not already exported, the command loads it from the repository's ignored `.env` file without shell-sourcing unrelated settings. The parser expands a model's first meaningful chapter back to timestamp zero and records that normalization. Overlong summaries are safely truncated and counted. Well-typed subject and keyword lists are deduplicated and capped at the schema limits, with removed values counted; malformed label types and lengths still reject the response. Evidence citations outside their proposed chapter remain visible as overlap violations in the comparison report; malformed timelines and unknown block citations still reject the result.

Partial runs are recoverable with `--resume`. Limit an initial smoke test by repeating `--video-id`. The output directory contains:

- one detailed result per model and episode, including cited transcript block indexes;
- one benchmark-compatible prediction file per fully completed model;
- `comparison-report.json` with structural, grounding, cost, and latency measurements;
- `blind-editorial-review.md`, which hides model identities while titles, boundaries, topics, and keywords are judged.

The blind worksheet is the quality decision. Automated grounding and shape metrics catch invalid or unsupported results, but they cannot determine whether a chapter title is genuinely useful to an editor. Reveal `blind_model_key` in the comparison report only after completing the worksheet.

## Candidate generation with V4 Pro

The production-facing enrichment path is deliberately review-only. It uses the pinned `deepseek/deepseek-v4-pro` model through OpenRouter, divides long episodes into balanced windows no longer than 90 minutes, and merges their chapter timelines and recurring labels. Categories are restricted to the existing archive allowlist, retain cited transcript evidence, and follow explicit definitions: named formats such as Chadvice and OKBuddy require that named segment, Gaming means video games rather than physical or table games, and broad categories must characterize a substantial portion of the episode. Unless supported by the video title, broad-category citations must span at least 20% of the episode timeline; filtered suggestions are counted in run metrics. This avoids the oversized tail chapters found in the whole-episode bake-off without allowing free-form category growth.

Configure the ignored `.env` file:

```dotenv
ARCHIVE_ENRICHMENT_ENABLED=true
ARCHIVE_ENRICHMENT_PROVIDER=openrouter
ARCHIVE_ENRICHMENT_MODEL=deepseek/deepseek-v4-pro
OPENROUTER_API_KEY=...
ARCHIVE_ENRICHMENT_MAX_WINDOW_MINUTES=90
ARCHIVE_ENRICHMENT_MAX_COST_USD_PER_VIDEO=1.00
ARCHIVE_ENRICHMENT_PUBLISH=false
ARCHIVE_ENRICHMENT_QUEUE_POLL_SECONDS=300
ARCHIVE_ENRICHMENT_QUEUE_FAILURE_COOLDOWN_SECONDS=86400
ARCHIVE_ENRICHMENT_QUEUE_CREDIT_COOLDOWN_SECONDS=3600
```

Production Compose runs `archive-enrichment-queue` continuously. It prioritizes
the newest completed transcript-ready video that lacks candidates from the
current model and prompt, never replaces moderated chapters, and cools down a
failed video before retrying it. An OpenRouter HTTP 402 or explicit insufficient
credits response pauses account-level work for the configured credit cooldown;
the service remains alive so adding credits resumes generation automatically.

Run an explicit pilot from the repository root, repeating `--video-id` when needed:

```bash
./.venv/bin/python scripts/enrich_archive_video.py \
  --video-id VIDEO_UUID_1 \
  --video-id VIDEO_UUID_2
```

The command processes videos sequentially, writes an auditable extraction run, and replaces only prior automatic candidates. It refuses videos with curated or moderated chapters, never publishes chapters or labels, disables OpenRouter provider fallback, rejects labels without lexical support in cited transcript blocks, and fails the run before persistence if the reported model cost exceeds the configured per-video limit. Editors must review candidates before any separate publication step.
