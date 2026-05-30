from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
import re
from collections.abc import Sequence

from app.transcripts.blocks import TranscriptBlock, build_transcript_blocks
from app.transcripts.types import TranscriptSegment


_TOKEN_RE = re.compile(r"[\w']+")


@dataclass(frozen=True)
class MergedSegment:
    start_ms: int
    end_ms: int
    text: str
    speaker_label: str | None


@dataclass(frozen=True)
class MergedBlock:
    block_index: int
    start_ms: int
    end_ms: int
    speaker_label: str | None
    text: str
    segment_ids: list[int]
    kind: str
    primary_source: str
    supporting_sources: list[str]
    needs_review: bool = False
    merge_reason: str | None = None
    similarity: float | None = None


@dataclass(frozen=True)
class MergedTranscript:
    video_id: str
    segments: list[MergedSegment]
    blocks: list[MergedBlock]


def normalize_for_merge(text: str) -> str:
    return " ".join(text.lower().split())


def token_similarity(left: str, right: str) -> float:
    left_tokens = set(_TOKEN_RE.findall(normalize_for_merge(left)))
    right_tokens = set(_TOKEN_RE.findall(normalize_for_merge(right)))
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def bucket_by_time(segments: Sequence[TranscriptSegment], bucket_ms: int) -> dict[int, list[TranscriptSegment]]:
    buckets: dict[int, list[TranscriptSegment]] = defaultdict(list)
    for segment in segments:
        if not segment.text.strip():
            continue
        bucket = max(0, int(segment.start_ms) // bucket_ms)
        buckets[bucket].append(segment)
    return dict(sorted(buckets.items()))


def _join_segments(segments: Sequence[TranscriptSegment]) -> tuple[int, int, str, str | None]:
    ordered = sorted(segments, key=lambda s: (s.start_ms, s.end_ms))
    start_ms = ordered[0].start_ms
    end_ms = ordered[-1].end_ms
    text = " ".join(segment.text.strip() for segment in ordered if segment.text.strip()).strip()
    speaker_label = next((segment.speaker_label for segment in ordered if segment.speaker_label), None)
    return start_ms, end_ms, text, speaker_label


def build_merged_transcript(
    video_id: str,
    whisper_segments: Sequence[TranscriptSegment],
    youtube_segments: Sequence[TranscriptSegment],
    bucket_ms: int = 10000,
) -> MergedTranscript:
    whisper_buckets = bucket_by_time(whisper_segments, bucket_ms)
    youtube_buckets = bucket_by_time(youtube_segments, bucket_ms)
    all_buckets = sorted(set(whisper_buckets) | set(youtube_buckets))

    chosen: list[TranscriptSegment] = []
    segment_meta: list[tuple[str, list[str], bool, str | None, float | None]] = []

    for bucket in all_buckets:
        whisper_bucket = whisper_buckets.get(bucket, [])
        youtube_bucket = youtube_buckets.get(bucket, [])
        if whisper_bucket and not youtube_bucket:
            start_ms, end_ms, text, speaker_label = _join_segments(whisper_bucket)
            chosen.append(TranscriptSegment(start_ms=start_ms, end_ms=end_ms, text=text, speaker_label=speaker_label))
            segment_meta.append(("whisper", [], False, None, None))
            continue
        if youtube_bucket and not whisper_bucket:
            start_ms, end_ms, text, speaker_label = _join_segments(youtube_bucket)
            chosen.append(TranscriptSegment(start_ms=start_ms, end_ms=end_ms, text=text, speaker_label=speaker_label))
            segment_meta.append(("youtube", [], False, None, None))
            continue

        whisper_start, whisper_end, whisper_text, whisper_speaker = _join_segments(whisper_bucket)
        youtube_start, youtube_end, youtube_text, _ = _join_segments(youtube_bucket)
        similarity = token_similarity(whisper_text, youtube_text)
        needs_review = similarity < 0.35
        reason = "heavy_disagreement_prefer_whisper" if needs_review else "whisper_with_youtube_support"
        chosen.append(
            TranscriptSegment(
                start_ms=min(whisper_start, youtube_start),
                end_ms=max(whisper_end, youtube_end),
                text=whisper_text,
                speaker_label=whisper_speaker,
            )
        )
        segment_meta.append(("whisper", ["youtube"], needs_review, reason, similarity))

    blocks: list[MergedBlock] = []
    for block in build_transcript_blocks(chosen):
        block_meta = [segment_meta[idx] for idx in block.segment_ids if idx < len(segment_meta)]
        primary_sources = [meta[0] for meta in block_meta]
        primary_source = primary_sources[0] if primary_sources and len(set(primary_sources)) == 1 else "merged"
        supporting_sources = sorted({source for meta in block_meta for source in meta[1]})
        if primary_source == "merged":
            supporting_sources = sorted(set(primary_sources) | set(supporting_sources))
        needs_review = any(meta[2] for meta in block_meta)
        reasons = [meta[3] for meta in block_meta if meta[3]]
        merge_reason = "mixed_source_block" if primary_source == "merged" else (reasons[0] if reasons else None)
        similarities = [meta[4] for meta in block_meta if meta[4] is not None]
        similarity = sum(similarities) / len(similarities) if similarities else None
        blocks.append(
            MergedBlock(
                block_index=block.block_index,
                start_ms=block.start_ms,
                end_ms=block.end_ms,
                speaker_label=block.speaker_label,
                text=block.text,
                segment_ids=block.segment_ids,
                kind=block.kind,
                primary_source=primary_source,
                supporting_sources=supporting_sources,
                needs_review=needs_review,
                merge_reason=merge_reason,
                similarity=similarity,
            )
        )

    merged_segments = [MergedSegment(s.start_ms, s.end_ms, s.text, s.speaker_label) for s in chosen]
    return MergedTranscript(video_id=video_id, segments=merged_segments, blocks=blocks)
