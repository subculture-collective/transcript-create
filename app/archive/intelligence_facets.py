from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas import ArchiveIntelligenceResponse, ArchivePerson, ArchiveVideoTag, VideoInfo


@dataclass
class _PersonFacet:
    person: ArchivePerson
    count: int = 0
    roles: set[str] = field(default_factory=set)


@dataclass
class _TagFacet:
    tag: ArchiveVideoTag
    count: int = 0


def _video_key(video: VideoInfo) -> str | None:
    return str(video.id) if video.id else None


def _collect_unique_videos(response: ArchiveIntelligenceResponse) -> list[VideoInfo]:
    seen: set[str] = set()
    videos: list[VideoInfo] = []

    def add(video: VideoInfo | None) -> None:
        if video is None:
            return
        key = _video_key(video)
        if key is None or key in seen:
            return
        seen.add(key)
        videos.append(video)

    scoped_count = 0
    for period in response.periods:
        for video in period.videos:
            add(video)
            scoped_count += 1
        for moment in period.evidence:
            add(moment.video)
            scoped_count += 1
        for topic in period.top_topics:
            for moment in topic.evidence:
                add(moment.video)
                scoped_count += 1

    if scoped_count > 0:
        return videos

    for video in response.summary.recent_videos:
        add(video)
    for topic in response.topic_cards:
        for moment in topic.evidence:
            add(moment.video)

    return videos


def attach_archive_facets(response: ArchiveIntelligenceResponse) -> ArchiveIntelligenceResponse:
    people_by_slug: dict[str, _PersonFacet] = {}
    tags_by_slug: dict[str, _TagFacet] = {}

    for video in _collect_unique_videos(response):
        for person in video.people:
            if not person.slug:
                continue
            entry = people_by_slug.setdefault(
                person.slug,
                _PersonFacet(person=person.model_copy(update={"role": None})),
            )
            entry.count += 1
            if person.role:
                entry.roles.add(person.role)

        for tag in video.tags:
            if not tag.slug:
                continue
            entry = tags_by_slug.setdefault(tag.slug, _TagFacet(tag=tag))
            entry.count += 1

    people = []
    for slug, entry in sorted(
        people_by_slug.items(),
        key=lambda item: (
            -item[1].count,
            item[1].person.sort_order if item[1].person.sort_order is not None else 0,
            str(item[1].person.display_name).casefold(),
            item[0],
        ),
    )[:12]:
        person = entry.person
        roles = entry.roles
        role = next(iter(roles)) if len(roles) == 1 else None
        people.append(person.model_copy(update={"role": role}))

    tags = [
        entry.tag
        for slug, entry in sorted(
            tags_by_slug.items(),
            key=lambda item: (
                -item[1].count,
                item[1].tag.sort_order if item[1].tag.sort_order is not None else 0,
                str(item[1].tag.label).casefold(),
                item[0],
            ),
        )[:12]
    ]

    return response.model_copy(update={"people": people, "tags": tags})
