from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path


OUTPUT_DIR = Path(__file__).resolve().parent


def csv_rows(name: str) -> list[dict[str, str]]:
    with (OUTPUT_DIR / name).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


summary = json.loads((OUTPUT_DIR / "summary.json").read_text(encoding="utf-8"))
flags = csv_rows("flagged_sections.csv")
issues = csv_rows("issue_counts.csv")
names = csv_rows("name_candidates.csv")
name_leads = csv_rows("possible_name_mistranscriptions.csv")
generated_at = datetime.now(timezone.utc).isoformat()
query_sql = (OUTPUT_DIR / "sampling_query.sql").read_text(encoding="utf-8")

for row in flags:
    row["review_priority"] = int(row["review_priority"])
    row["agreement_score"] = float(row["agreement_score"]) if row["agreement_score"] else None
    row["native_segment_count"] = int(row["native_segment_count"])
    row["youtube_segment_count"] = int(row["youtube_segment_count"])
for row in issues:
    row["flagged_sections"] = int(row["flagged_sections"])
    row["sampled_sections"] = int(row["sampled_sections"])
    row["share"] = float(row["share"])
for row in names:
    row["sample_occurrences"] = int(row["sample_occurrences"])
    row["reference_similarity"] = float(row["reference_similarity"]) if row["reference_similarity"] else None
for row in name_leads:
    row["similarity"] = float(row["similarity"])

summary_rows = [
    {
        key: value
        for key, value in summary.items()
        if value is None or isinstance(value, (str, int, float, bool))
    }
]
source = {
    "id": "transcript_sampling",
    "label": "HasanAra production transcript and YouTube-caption sample",
    "query": {
        "engine": "PostgreSQL 16",
        "language": "sql",
        "executed_at": generated_at,
        "description": "Deterministic chronological sample of paired native Whisper and YouTube-caption windows.",
        "sql": query_sql,
        "tables_used": [
            "public.videos",
            "public.segments",
            "public.youtube_transcripts",
            "public.youtube_segments",
            "public.archive_people",
        ],
        "filters": [
            "Completed videos with both native Whisper segments and YouTube captions",
            "Duration at least 10 minutes",
            "One deterministic video from each of 40 chronological buckets",
            "One-minute windows centered at 5%, 27%, 50%, 73%, and 95% of duration",
            "Snapshot generated August 11, 2026",
        ],
        "metric_definitions": [
            "Flagged section: sampled window meeting at least one screening rule; it is not a confirmed error.",
            "Agreement score: SequenceMatcher ratio over normalized Whisper and YouTube-caption word tokens.",
            "Name candidate: canonical archive-person match or a multi-token capitalized phrase in Whisper text.",
            "Possible name mistranscription: observed candidate with a fuzzy reference-name match of at least 0.82.",
        ],
    },
}

artifact = {
    "surface": "report",
    "manifest": {
        "version": 1,
        "surface": "report",
        "title": "Transcript Sampling Audit",
        "description": "Manual-review timestamps and proper-name candidates from a stratified HasanAra transcript sample.",
        "generatedAt": generated_at,
        "sources": [source],
        "cards": [
            {
                "id": "sampled_videos",
                "description": "Videos distributed chronologically across the paired-caption archive.",
                "dataset": "summary",
                "sourceId": "transcript_sampling",
                "metrics": [{"label": "Sampled videos", "field": "sampled_videos", "format": "number"}],
            },
            {
                "id": "sampled_sections",
                "description": "One-minute windows at five positions in every sampled video.",
                "dataset": "summary",
                "sourceId": "transcript_sampling",
                "metrics": [{"label": "Sampled sections", "field": "sampled_sections", "format": "number"}],
            },
            {
                "id": "flagged_sections",
                "description": "Screening leads requiring listening; not a measured error rate.",
                "dataset": "summary",
                "sourceId": "transcript_sampling",
                "metrics": [
                    {"label": "Flagged sections", "field": "flagged_sections", "format": "number"},
                    {"label": "Share sampled", "field": "flagged_share", "format": "percent"},
                ],
            },
            {
                "id": "name_candidates",
                "description": "Broad proper-name candidates retained for manual triage.",
                "dataset": "summary",
                "sourceId": "transcript_sampling",
                "metrics": [
                    {"label": "Name candidates", "field": "name_rows", "format": "number"},
                    {
                        "label": "Fuzzy spelling leads",
                        "field": "possible_name_mistranscriptions",
                        "format": "number",
                    },
                ],
            },
        ],
        "charts": [
            {
                "id": "issue_counts",
                "title": "Manual-review flags",
                "subtitle": "Counts across 200 sampled one-minute sections; a section can carry multiple flags",
                "type": "bar",
                "intent": "comparison",
                "question": "Which screening signals produced the most manual-review sections?",
                "rationale": "Sorted horizontal bars support comparison across long issue labels while preserving exact counts.",
                "comparisonContext": {
                    "denominator": "200 sampled one-minute sections",
                    "grain": "screening issue type",
                    "unit": "flagged sections",
                },
                "dataset": "issue_counts",
                "sourceId": "transcript_sampling",
                "encodings": {
                    "x": {"field": "issue_type", "type": "nominal", "label": "Screening signal"},
                    "y": {"field": "flagged_sections", "type": "quantitative", "label": "Sections"},
                    "tooltip": [
                        {"field": "flagged_sections", "type": "quantitative", "label": "Sections"},
                        {"field": "share", "type": "quantitative", "format": "percent", "label": "Share sampled"},
                    ],
                },
                "valueFormat": "number",
                "layout": "full",
                "labels": {"values": "all"},
                "options": {"orientation": "horizontal", "grouping": "grouped"},
                "surface": {"surface": "card", "showControls": False, "viewMode": "both"},
            }
        ],
        "tables": [
            {
                "id": "flagged_sections",
                "title": "Sections to check manually",
                "subtitle": "37 timestamped windows ranked by screening priority; use the YouTube URL to listen",
                "dataset": "flagged_sections",
                "sourceId": "transcript_sampling",
                "defaultSort": {"field": "review_priority", "direction": "desc"},
                "density": "dense",
                "layout": "full",
                "columns": [
                    {"field": "review_priority", "label": "Priority", "format": "number"},
                    {"field": "uploaded_date", "label": "Date", "type": "date"},
                    {"field": "video_title", "label": "Video"},
                    {"field": "timestamp", "label": "Timestamp"},
                    {"field": "sample_position", "label": "Position"},
                    {"field": "issues", "label": "Why flagged"},
                    {"field": "possible_word_or_name_differences", "label": "Possible differences"},
                    {"field": "native_text", "label": "Whisper context"},
                    {"field": "youtube_caption_text", "label": "Caption context"},
                    {"field": "youtube_url", "label": "Listen"},
                ],
            },
            {
                "id": "name_leads",
                "title": "Possible name spellings and aliases",
                "subtitle": "Fuzzy matches are hypotheses; the assessment column separates likely errors from obvious false matches",
                "dataset": "name_leads",
                "sourceId": "transcript_sampling",
                "defaultSort": {"field": "similarity", "direction": "desc"},
                "density": "spacious",
                "layout": "full",
                "columns": [
                    {"field": "observed_form", "label": "Observed"},
                    {"field": "possible_correction", "label": "Possible correction"},
                    {"field": "assessment", "label": "Assessment"},
                    {"field": "similarity", "label": "Similarity", "format": "number"},
                    {"field": "video_title", "label": "Video"},
                    {"field": "timestamp", "label": "Timestamp"},
                    {"field": "context", "label": "Context"},
                    {"field": "youtube_url", "label": "Listen"},
                ],
            },
            {
                "id": "all_name_candidates",
                "title": "All proper-name candidates in the sample",
                "subtitle": "347 candidates with confidence, source, recurrence, first timestamp, and context",
                "dataset": "name_candidates",
                "sourceId": "transcript_sampling",
                "defaultSort": {"field": "sample_occurrences", "direction": "desc"},
                "density": "dense",
                "layout": "full",
                "columns": [
                    {"field": "canonical_or_candidate", "label": "Name candidate"},
                    {"field": "observed_form", "label": "Observed form"},
                    {"field": "confidence", "label": "Confidence"},
                    {"field": "suggested_reference_name", "label": "Reference match"},
                    {"field": "sources", "label": "Sources"},
                    {"field": "sample_occurrences", "label": "Occurrences", "format": "number"},
                    {"field": "first_video", "label": "First sampled video"},
                    {"field": "first_timestamp", "label": "Timestamp"},
                    {"field": "first_context", "label": "Context"},
                    {"field": "first_youtube_url", "label": "Listen"},
                ],
            },
        ],
        "blocks": [
            {"id": "title", "type": "markdown", "body": "# Transcript Sampling Audit"},
            {
                "id": "technical_summary",
                "type": "markdown",
                "sourceId": "transcript_sampling",
                "body": (
                    "## Technical summary\n\n"
                    "A stratified audit of **40 videos and 200 one-minute sections** produced **37 manual-review leads**. "
                    "That 18.5% is a screening rate, not a confirmed transcription-error rate. The sample also produced "
                    "**347 broad proper-name candidates** and **11 fuzzy spelling/alias leads**. Five name leads look "
                    "plausible after context review—Emma Vigland, Bradley Martin, Carl Marx, Aiden Ross, and Alex Prey—but "
                    "none should enter the correction dictionary until someone listens at the linked timestamp."
                ),
            },
            {
                "id": "metrics",
                "type": "metric-strip",
                "cardIds": ["sampled_videos", "sampled_sections", "flagged_sections", "name_candidates"],
            },
            {
                "id": "key_findings",
                "type": "markdown",
                "sourceId": "transcript_sampling",
                "body": (
                    "## Most leads are comparison differences, not obvious hallucinations\n\n"
                    "The audit found one strongest caption disagreement, one heavy-repetition window, five windows where "
                    "Whisper was empty while captions contained words, and 29 lower-to-moderate disagreement windows. "
                    "The latter group can include timing drift, censorship tokens, or caption errors, so the chart is a review workload map—not a quality score."
                ),
            },
            {"id": "issue_chart", "type": "chart", "chartId": "issue_counts", "layout": "full"},
            {
                "id": "manual_checks_heading",
                "type": "markdown",
                "body": (
                    "## Exact sections for listening\n\n"
                    "Start at the highest priority. Each row includes the timestamp, direct YouTube seek URL, both text sources, "
                    "and short token replacements that may reveal a word or name error."
                ),
            },
            {"id": "manual_checks", "type": "table", "tableId": "flagged_sections", "layout": "full"},
            {
                "id": "name_findings",
                "type": "markdown",
                "body": (
                    "## Name leads need two-stage review\n\n"
                    "The short table contains fuzzy spelling leads and an initial assessment. The full table deliberately keeps "
                    "low-confidence proper nouns, organizations, and places because they may still belong in the eventual vocabulary. "
                    "Capitalization alone is noisy, so verify pronunciation and identity before promoting a candidate."
                ),
            },
            {"id": "name_leads_table", "type": "table", "tableId": "name_leads", "layout": "full"},
            {"id": "all_names_table", "type": "table", "tableId": "all_name_candidates", "layout": "full"},
            {
                "id": "scope",
                "type": "markdown",
                "body": (
                    "## Scope and definitions\n\n"
                    "The comparison population is completed videos with both native Whisper segments and YouTube captions. "
                    "The paired corpus contains 1,078 videos; this audit samples 40 of them across the archive's chronology. "
                    "A section is a 60-second window centered at one of five relative positions. A flag means a rule fired, not that Whisper was wrong."
                ),
            },
            {
                "id": "methodology",
                "type": "markdown",
                "body": (
                    "## Sampling and screening method\n\n"
                    "Videos were divided into 40 chronological buckets and one deterministic video was selected from each. "
                    "Token agreement used case-folded word sequences. Additional checks covered missing native text, repetition, "
                    "non-Latin output, existing hallucination flags, dense windows, and fuzzy reference-name matches. "
                    "Name extraction combined the archive's 170 canonical people with multi-token capitalization candidates."
                ),
            },
            {
                "id": "limitations",
                "type": "markdown",
                "body": (
                    "## Limitations and robustness\n\n"
                    "YouTube captions are not ground truth and are frequently lowercase, censored, delayed, or wrong. Relative-position "
                    "sampling can miss errors between windows. Proper-name detection undercounts lowercase unknown names and overcounts "
                    "capitalized non-person entities. Validation confirmed 200 unique video-position rows, exactly 40 rows at every position, "
                    "valid timestamp bounds, and no duplicate sample grain. Results are suitable for manual triage with these caveats."
                ),
            },
            {
                "id": "next_steps",
                "type": "markdown",
                "body": (
                    "## Recommended next steps\n\n"
                    "1. Listen to the 37 flagged sections and mark each proposed difference as confirmed, rejected, or uncertain.\n"
                    "2. Review the 11 fuzzy name leads before working through the complete candidate table.\n"
                    "3. Add only confirmed spellings to the decoder prompt and contextual correction rules.\n"
                    "4. Repeat this stratified sample after VAD and vocabulary changes to measure whether the review workload falls."
                ),
            },
            {
                "id": "questions",
                "type": "markdown",
                "body": (
                    "## Further questions\n\n"
                    "- Should the next batch emphasize recent feeds, historically poor model runs, or videos without YouTube captions?\n"
                    "- Do you want the verified list to distinguish people, places, organizations, games, and recurring phrases?\n"
                    "- Should rejected candidates be retained as negative examples so they are not suggested again?"
                ),
            },
        ],
    },
    "snapshot": {
        "version": 1,
        "generatedAt": generated_at,
        "status": "ready",
        "datasets": {
            "summary": summary_rows,
            "issue_counts": issues,
            "flagged_sections": flags,
            "name_leads": name_leads,
            "name_candidates": names,
        },
    },
    "sources": [source],
}

(OUTPUT_DIR / "artifact.json").write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
print(OUTPUT_DIR / "artifact.json")
