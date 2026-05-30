from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Any

from app.transcripts.types import TranscriptSegment

_TOKEN_RE = re.compile(r"[\w']+")


def normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(normalize_text(text))


def bucket_segments(segments: Sequence[TranscriptSegment], bucket_ms: int) -> dict[int, str]:
    buckets: dict[int, list[str]] = defaultdict(list)
    for segment in segments:
        if not segment.text or not segment.text.strip():
            continue
        start_bucket = max(0, int(segment.start_ms) // bucket_ms)
        end_bucket = max(start_bucket, int(math.ceil(max(segment.end_ms, segment.start_ms + 1) / bucket_ms) - 1))
        for bucket in range(start_bucket, end_bucket + 1):
            buckets[bucket].append(segment.text.strip())
    return {bucket: " ".join(parts).strip() for bucket, parts in sorted(buckets.items())}


def jaccard_tokens(left: str, right: str) -> float:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _length_ratio(left: str, right: str) -> float:
    left_count = len(tokenize(left))
    right_count = len(tokenize(right))
    if not left_count and not right_count:
        return 1.0
    if not left_count or not right_count:
        return 0.0
    return min(left_count, right_count) / max(left_count, right_count)


def _source_stats(source_buckets: dict[int, str], total_buckets: int) -> dict[str, Any]:
    non_empty = sum(1 for text in source_buckets.values() if text.strip())
    token_count = sum(len(tokenize(text)) for text in source_buckets.values())
    return {
        "coverage_ratio": (non_empty / total_buckets) if total_buckets else 0.0,
        "non_empty_bucket_count": non_empty,
        "token_count": token_count,
    }


def _compare_bucket_maps(whisper_buckets: dict[int, str], youtube_buckets: dict[int, str]) -> dict[str, Any]:
    all_buckets = sorted(set(whisper_buckets) | set(youtube_buckets))
    total_buckets = len(all_buckets)
    missing_bucket_count = 0
    pairwise_similarity: list[float] = []
    pairwise_length_ratio: list[float] = []

    for bucket in all_buckets:
        whisper_text = whisper_buckets.get(bucket, "")
        youtube_text = youtube_buckets.get(bucket, "")
        if bool(whisper_text.strip()) != bool(youtube_text.strip()):
            missing_bucket_count += 1
        if whisper_text.strip() and youtube_text.strip():
            pairwise_similarity.append(jaccard_tokens(whisper_text, youtube_text))
            pairwise_length_ratio.append(_length_ratio(whisper_text, youtube_text))

    return {
        "total_bucket_count": total_buckets,
        "missing_bucket_count": missing_bucket_count,
        "average_similarity": sum(pairwise_similarity) / len(pairwise_similarity) if pairwise_similarity else 0.0,
        "average_length_ratio": sum(pairwise_length_ratio) / len(pairwise_length_ratio) if pairwise_length_ratio else 0.0,
        "buckets": [
            {"bucket": bucket, "whisper_text": whisper_buckets.get(bucket, ""), "youtube_text": youtube_buckets.get(bucket, "")}
            for bucket in all_buckets
        ],
    }


def compare_sources(video_id: str, whisper_segments: Sequence[TranscriptSegment], youtube_segments: Sequence[TranscriptSegment], bucket_ms: int = 10000) -> dict[str, Any]:
    whisper_buckets = bucket_segments(whisper_segments, bucket_ms)
    youtube_buckets = bucket_segments(youtube_segments, bucket_ms)
    bucket_metrics = _compare_bucket_maps(whisper_buckets, youtube_buckets)
    total_buckets = bucket_metrics["total_bucket_count"]
    whisper_stats = _source_stats(whisper_buckets, total_buckets)
    youtube_stats = _source_stats(youtube_buckets, total_buckets)

    whisper_only_bucket_count = sum(1 for row in bucket_metrics["buckets"] if row["whisper_text"].strip() and not row["youtube_text"].strip())
    youtube_only_bucket_count = sum(1 for row in bucket_metrics["buckets"] if row["youtube_text"].strip() and not row["whisper_text"].strip())

    whisper_coverage = whisper_stats["coverage_ratio"]
    youtube_coverage = youtube_stats["coverage_ratio"]
    avg_similarity = bucket_metrics["average_similarity"]

    if whisper_only_bucket_count > 0 and youtube_only_bucket_count > 0:
        recommendation = "hybrid"
    elif youtube_coverage >= whisper_coverage + 0.1 and (avg_similarity >= 0.55 or whisper_coverage < 0.6):
        recommendation = "youtube_first"
    elif whisper_coverage >= youtube_coverage + 0.1 and avg_similarity >= 0.55:
        recommendation = "whisper_first"
    else:
        recommendation = "needs_review"

    return {
        "video_id": video_id,
        "bucket_ms": bucket_ms,
        "total_bucket_count": total_buckets,
        "aligned_bucket_count": sum(
            1 for row in bucket_metrics["buckets"] if row["whisper_text"].strip() and row["youtube_text"].strip()
        ),
        "whisper": {
            **whisper_stats,
            "missing_bucket_count": youtube_only_bucket_count,
            "average_similarity": avg_similarity,
            "average_length_ratio": bucket_metrics["average_length_ratio"],
        },
        "youtube": {
            **youtube_stats,
            "missing_bucket_count": whisper_only_bucket_count,
            "average_similarity": avg_similarity,
            "average_length_ratio": bucket_metrics["average_length_ratio"],
        },
        "paired_missing_bucket_count": bucket_metrics["missing_bucket_count"],
        "whisper_only_bucket_count": whisper_only_bucket_count,
        "youtube_only_bucket_count": youtube_only_bucket_count,
        "recommendation": recommendation,
        "buckets": bucket_metrics["buckets"],
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Transcript Source Comparison",
        "",
        f"- Videos: {summary.get('video_count', 0)}",
        f"- Bucket size: {summary.get('bucket_ms', 'unknown')} ms",
        f"- Average Whisper coverage: {summary.get('average_whisper_coverage', 0):.2%}",
        f"- Average YouTube coverage: {summary.get('average_youtube_coverage', 0):.2%}",
        f"- Average aligned similarity: {summary.get('average_similarity', 0):.2%}",
    ]
    recommendations = summary.get("recommendations", {})
    for key in sorted(recommendations):
        lines.append(f"- {key}: {recommendations[key]}")
    lines.append("")
    lines.append("| Video | Title | Recommendation | Whisper coverage | YouTube coverage | Similarity |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: |")
    for video in report.get("videos", []):
        metrics = video.get("metrics", {})
        whisper = metrics.get("whisper", {})
        youtube = metrics.get("youtube", {})
        lines.append(
            "| {video_id} | {title} | {recommendation} | {whisper_cov:.1%} | {youtube_cov:.1%} | {similarity:.1%} |".format(
                video_id=video.get("video_id", ""),
                title=str(video.get("title") or "").replace("|", "\\|"),
                recommendation=video.get("recommendation", ""),
                whisper_cov=whisper.get("coverage_ratio", 0),
                youtube_cov=youtube.get("coverage_ratio", 0),
                similarity=metrics.get("whisper", {}).get("average_similarity", 0),
            )
        )
    return "\n".join(lines) + "\n"


def render_json_report(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True)
