from __future__ import annotations

import time
from datetime import date
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from .. import crud
from ..archive.repository import archive_repository
from ..archive.video_metadata_repository import get_video_metadata_map
from .intelligence_repository import SEED_TOPICS, SeedTopic, alias_matches_text, get_durable_archive_intelligence, slugify_topic
from .intelligence_repository import list_period_options
from ..schemas import (
    ArchiveEvidenceMoment,
    ArchiveIntelligenceResponse,
    ArchivePeriodIntelligence,
    ArchivePeriodOptionsResponse,
    ArchiveTimelineResponse,
    ArchiveTopicCard,
    ArchiveTrendingSearch,
    VideoInfo,
)


def _slugify(value: str) -> str:
    return slugify_topic(value)


def _row_value(row, key: str):
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except Exception:
        return getattr(row, key)


def _safe_video_metadata_map(db, video_ids):
    try:
        return get_video_metadata_map(db, video_ids)
    except (OperationalError, ProgrammingError, AssertionError):
        db.rollback()
        return {str(video_id): {"people": [], "tags": []} for video_id in video_ids}


def _video_from_row(row) -> VideoInfo:
    return VideoInfo(
        id=_row_value(row, "video_id"),
        youtube_id=_row_value(row, "youtube_id"),
        title=_row_value(row, "title"),
        duration_seconds=_row_value(row, "duration_seconds"),
        state=_row_value(row, "state"),
        caption_ingest_state=_row_value(row, "caption_ingest_state"),
        diarization_state=_row_value(row, "diarization_state"),
        uploaded_at=_row_value(row, "uploaded_at"),
        created_at=_row_value(row, "created_at"),
        updated_at=_row_value(row, "updated_at"),
        channel_name=_row_value(row, "channel_name"),
        language=_row_value(row, "language"),
        category=_row_value(row, "category"),
        has_whisper_transcript=bool(_row_value(row, "has_whisper_transcript")),
        has_youtube_transcript=bool(_row_value(row, "has_youtube_transcript")),
        people=list(_row_value(row, "people") or []),
        tags=list(_row_value(row, "tags") or []),
    )


def _search_suggestions(db, limit: int) -> list[ArchiveTrendingSearch]:
    try:
        rows = (
            db.execute(
                text(
                    """
                    SELECT term, frequency
                    FROM search_suggestions
                    ORDER BY frequency DESC, last_used DESC NULLS LAST, term ASC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
            .mappings()
            .all()
        )
    except (OperationalError, ProgrammingError):
        db.rollback()
        rows = []

    return [
        ArchiveTrendingSearch(term=row["term"], frequency=int(row["frequency"] or 0), trend_score=float(row["frequency"] or 0), source="search")
        for row in rows
    ]


def _topic_conditions(aliases: Iterable[str]) -> tuple[str, dict[str, str]]:
    clauses = []
    params: dict[str, str] = {}
    for idx, alias in enumerate(aliases):
        key = f"pattern_{idx}"
        clauses.append(f"s.text ILIKE :{key}")
        params[key] = f"%{alias}%"
    return " OR ".join(clauses) or "FALSE", params


def _recent_evidence_for_videos(db, videos: list[VideoInfo], limit: int = 24) -> list[ArchiveEvidenceMoment]:
    """Load a bounded transcript-evidence pool from already-selected videos.

    The first implementation scanned the whole `segments` table once per topic.
    That was accurate but too slow for the live archive and exceeded the frontend
    timeout. This keeps Phase 1 request-time work bounded by querying only the
    recent/timeline videos already selected for the page; durable precomputed
    topic stats can replace this later without changing the API contract.
    """
    video_ids = [str(video.id) for video in videos if video.id]
    if not video_ids:
        return []

    id_params = {f"video_id_{idx}": video_id for idx, video_id in enumerate(video_ids[:30])}
    placeholders = ", ".join(f":{key}" for key in id_params)
    rows = (
        db.execute(
            text(
                f"""
                SELECT
                    v.id AS video_id, v.youtube_id, v.title, v.duration_seconds, v.state,
                    v.caption_ingest_state, v.diarization_state, v.uploaded_at, v.created_at,
                    v.updated_at, v.channel_name, v.language, v.category,
                    EXISTS (SELECT 1 FROM segments s2 WHERE s2.video_id = v.id) AS has_whisper_transcript,
                    EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id) AS has_youtube_transcript,
                    s.start_ms, s.end_ms, s.text AS snippet
                FROM videos v
                JOIN segments s ON s.video_id = v.id
                WHERE v.id IN ({placeholders})
                ORDER BY COALESCE(v.uploaded_at, v.created_at) DESC NULLS LAST, s.start_ms ASC
                LIMIT :limit
                """
            ),
            {**id_params, "limit": limit},
        )
        .mappings()
        .all()
    )
    metadata_map = _safe_video_metadata_map(db, [row["video_id"] for row in rows])

    return [
        ArchiveEvidenceMoment(
            video=_video_from_row({**row, **metadata_map.get(str(row["video_id"]), {"people": [], "tags": []})}),
            start_ms=int(row["start_ms"]),
            end_ms=int(row["end_ms"]),
            snippet=row["snippet"],
            topic=None,
        )
        for row in rows
    ]


def _matching_evidence(evidence_pool: list[ArchiveEvidenceMoment], aliases: Iterable[str], topic_label: str, limit: int = 2) -> list[ArchiveEvidenceMoment]:
    lowered_aliases = [alias.lower() for alias in aliases]
    matches: list[ArchiveEvidenceMoment] = []
    for moment in evidence_pool:
        snippet = moment.snippet.lower()
        if any(alias_matches_text(alias, snippet) for alias in lowered_aliases):
            matches.append(moment.model_copy(update={"topic": topic_label}))
        if len(matches) >= limit:
            break
    return matches


def _related_topics(snippets: Iterable[str], current_slug: str) -> list[str]:
    haystack = " ".join(snippets).lower()
    related: list[str] = []
    for seed in SEED_TOPICS:
        if seed.slug == current_slug:
            continue
        if any(alias_matches_text(alias, haystack) for alias in seed.aliases):
            related.append(seed.label)
    return related[:3]


def _seed_topic_card(seed: SeedTopic, evidence_pool: list[ArchiveEvidenceMoment], search_frequency: int = 0) -> ArchiveTopicCard:
    evidence = _matching_evidence(evidence_pool, seed.aliases, seed.label, limit=2)
    total_moments = len(evidence)
    total_videos = len({moment.video.id for moment in evidence})
    recent_mentions_90d = total_moments
    related_topics = _related_topics((moment.snippet for moment in evidence), seed.slug)
    trend_score = float((total_moments * 2) + recent_mentions_90d + search_frequency)
    return ArchiveTopicCard(
        slug=seed.slug,
        label=seed.label,
        source="hybrid",
        aliases=list(seed.aliases),
        total_moments=total_moments,
        total_videos=total_videos,
        recent_mentions_90d=recent_mentions_90d,
        trend_score=trend_score,
        related_topics=related_topics,
        evidence=evidence,
    )


def _automatic_topic_cards(
    popular: Iterable[ArchiveTrendingSearch], existing_slugs: set[str], evidence_pool: list[ArchiveEvidenceMoment]
) -> list[ArchiveTopicCard]:
    cards: list[ArchiveTopicCard] = []
    for item in popular:
        slug = _slugify(item.term)
        if slug in existing_slugs:
            continue
        evidence = _matching_evidence(evidence_pool, [item.term], item.term, limit=1)
        cards.append(
            ArchiveTopicCard(
                slug=slug,
                label=item.term,
                source="automatic",
                aliases=[item.term],
                total_moments=len(evidence),
                total_videos=len({moment.video.id for moment in evidence}),
                recent_mentions_90d=len(evidence),
                trend_score=item.trend_score,
                related_topics=[],
                evidence=evidence,
            )
        )
    return cards


def _suggested_searches(topic_cards: list[ArchiveTopicCard], popular: list[ArchiveTrendingSearch], limit: int) -> list[ArchiveTrendingSearch]:
    suggestions: list[ArchiveTrendingSearch] = []
    seen: set[str] = set()

    for topic in topic_cards:
        if topic.label.lower() in seen:
            continue
        suggestions.append(
            ArchiveTrendingSearch(
                term=topic.label,
                frequency=topic.total_moments,
                trend_score=topic.trend_score,
                source="hybrid",
            )
        )
        seen.add(topic.label.lower())
        if len(suggestions) >= limit:
            return suggestions[:limit]

    for item in popular:
        key = item.term.lower()
        if key in seen:
            continue
        suggestions.append(ArchiveTrendingSearch(term=item.term, frequency=item.frequency, trend_score=item.trend_score, source=item.source))
        seen.add(key)
        if len(suggestions) >= limit:
            break

    return suggestions[:limit]


def _periods(
    timeline: ArchiveTimelineResponse,
    topic_cards: list[ArchiveTopicCard],
    evidence_pool: list[ArchiveEvidenceMoment],
    limit: int,
) -> list[ArchivePeriodIntelligence]:
    periods: list[ArchivePeriodIntelligence] = []
    for bucket in timeline.buckets[:limit]:
        bucket_video_ids = {str(video.id) for video in bucket.videos}
        bucket_evidence = [moment for moment in evidence_pool if str(moment.video.id) in bucket_video_ids]
        top_topics: list[ArchiveTopicCard] = []
        evidence: list[ArchiveEvidenceMoment] = []
        for topic in topic_cards:
            topic_evidence = _matching_evidence(bucket_evidence, topic.aliases, topic.label, limit=1)
            if not topic_evidence:
                continue
            top_topics.append(
                topic.model_copy(
                    update={
                        "total_moments": len(topic_evidence),
                        "total_videos": len({moment.video.id for moment in topic_evidence}),
                        "evidence": topic_evidence,
                    }
                )
            )
            evidence.extend(topic_evidence)
            if len(top_topics) >= 3:
                break

        topic_labels = ", ".join(topic.label for topic in top_topics) if top_topics else "no highlighted topics"
        summary = f"{bucket.label} contains {bucket.video_count} archived VODs with {topic_labels}."
        periods.append(
            ArchivePeriodIntelligence(
                period=bucket.period,
                label=bucket.label,
                video_count=bucket.video_count,
                total_duration_seconds=bucket.total_duration_seconds,
                videos=bucket.videos[:3],
                top_topics=top_topics,
                summary=summary,
                evidence=evidence,
            )
        )
    return periods


def get_archive_intelligence(
    db,
    *,
    topic_limit: int = 8,
    period_limit: int = 8,
    granularity: str = "month",
    date_from: date | None = None,
    date_to: date | None = None,
    period: str | None = None,
) -> ArchiveIntelligenceResponse:
    start = time.perf_counter()

    cached = get_durable_archive_intelligence(
        db,
        topic_limit=topic_limit,
        period_limit=period_limit,
        granularity=granularity,
        date_from=date_from,
        date_to=date_to,
        period_slug=period,
    )
    if cached is not None:
        return cached.model_copy(update={"query_time_ms": int((time.perf_counter() - start) * 1000)})

    summary = archive_repository.get_summary(db, recent_limit=6, popular_limit=max(topic_limit, 8))
    timeline = crud.get_archive_timeline(db, limit=max(period_limit, 1) * 25, granularity=granularity)
    trending_searches = _search_suggestions(db, limit=max(topic_limit, 8))
    evidence_videos: list[VideoInfo] = []
    seen_video_ids: set[str] = set()
    for video in [*summary.recent_videos, *(bucket_video for bucket in timeline.buckets for bucket_video in bucket.videos[:3])]:
        key = str(video.id)
        if key in seen_video_ids:
            continue
        evidence_videos.append(video)
        seen_video_ids.add(key)
        if len(evidence_videos) >= 30:
            break
    evidence_pool = _recent_evidence_for_videos(db, evidence_videos, limit=24)
    search_frequency_by_slug = {_slugify(item.term): item.frequency for item in trending_searches}

    topic_cards: list[ArchiveTopicCard] = []
    for seed in SEED_TOPICS:
        if len(topic_cards) >= topic_limit:
            break
        topic_cards.append(_seed_topic_card(seed, evidence_pool, search_frequency_by_slug.get(seed.slug, 0)))

    if len(topic_cards) < topic_limit:
        existing_slugs = {topic.slug for topic in topic_cards}
        topic_cards.extend(_automatic_topic_cards(trending_searches, existing_slugs, evidence_pool))
        topic_cards = topic_cards[:topic_limit]

    topic_cards = sorted(topic_cards, key=lambda topic: topic.trend_score, reverse=True)[:topic_limit]

    suggested_searches = _suggested_searches(topic_cards, trending_searches, limit=max(topic_limit, len(SEED_TOPICS)))
    periods = _periods(timeline, topic_cards, evidence_pool, limit=period_limit)

    period_options = list_period_options(db).periods
    selected_period = next((option for option in period_options if option.kind == "month"), None)
    if selected_period is None and period_options:
        selected_period = period_options[0]

    return ArchiveIntelligenceResponse(
        summary=summary,
        exploration_modes=["timeline", "topics", "trending", "suggested"],
        trending_searches=trending_searches,
        suggested_searches=suggested_searches,
        topic_cards=topic_cards,
        periods=periods,
        selected_period=selected_period,
        period_options=period_options,
        query_time_ms=int((time.perf_counter() - start) * 1000),
    )


def get_archive_period_options(db, kind: str | None = None, limit: int = 120) -> ArchivePeriodOptionsResponse:
    return list_period_options(db, kind=kind, limit=limit)
