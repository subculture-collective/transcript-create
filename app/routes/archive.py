from fastapi import APIRouter, Depends, Query
from datetime import date
import uuid

from sqlalchemy.exc import OperationalError, ProgrammingError

from .. import crud
from ..cache import invalidate_cache, invalidate_cache_pattern
from ..archive.repository import archive_repository
from ..archive.intelligence import get_archive_intelligence, get_archive_period_options
from ..archive.video_metadata_repository import (
    create_person,
    create_tag,
    get_video_metadata_map,
    list_people_admin,
    list_tags_admin,
    search_videos_for_admin,
    seed_default_tags,
    set_video_metadata,
    update_person,
    update_tag,
)
from ..archive.intelligence_repository import (
    create_named_period,
    list_named_periods_admin,
    refresh_named_period_stats,
    refresh_named_period_stats_for_slug,
    seed_named_periods,
    update_named_period,
)
from ..db import get_db
from ..exceptions import NotFoundError
from ..schemas import (
    ArchiveIntelligenceResponse,
    ArchivePersonAdmin,
    ArchivePersonAdminListResponse,
    ArchivePersonCreate,
    ArchivePersonUpdate,
    ArchiveNamedPeriodAdminListResponse,
    ArchiveNamedPeriodAdminResponse,
    ArchiveNamedPeriodCreate,
    ArchiveNamedPeriodUpdate,
    ArchivePeriodOptionsResponse,
    ArchiveSummary,
    ArchiveTimelineResponse,
    ArchiveVideoMetadataAdminListResponse,
    ArchiveVideoMetadataAdminVideo,
    ArchiveVideoMetadataUpdate,
    ArchiveVideoTagAdmin,
    ArchiveVideoTagAdminListResponse,
    ArchiveVideoTagCreate,
    ArchiveVideoTagUpdate,
)
from ..security import ROLE_ADMIN, require_role

router = APIRouter(prefix="", tags=["Archive"])


def _admin_video_metadata_response(db, video_id: uuid.UUID) -> ArchiveVideoMetadataAdminVideo | None:
    video = crud.get_video(db, video_id)
    if not video:
        return None
    try:
        metadata_map = get_video_metadata_map(db, [video_id], published_only=False)
    except (OperationalError, ProgrammingError):
        db.rollback()
        metadata_map = {str(video_id): {"people": [], "tags": []}}
    payload = dict(video)
    metadata = metadata_map.get(str(video_id), {"people": [], "tags": []})
    payload["people"] = metadata.get("people", [])
    payload["tags"] = metadata.get("tags", [])
    return ArchiveVideoMetadataAdminVideo(**payload)


@router.get(
    "/archive/summary",
    response_model=ArchiveSummary,
    summary="Get archive summary",
    description="Summary statistics for HasanAra based on real VOD and transcript data.",
)
def archive_summary(
    recent_limit: int = Query(6, ge=0, le=20, description="Number of recent videos to include"),
    popular_limit: int = Query(8, ge=0, le=20, description="Number of popular searches to include"),
    db=Depends(get_db),
):
    return archive_repository.get_summary(db, recent_limit=recent_limit, popular_limit=popular_limit)


@router.get(
    "/archive/timeline",
    response_model=ArchiveTimelineResponse,
    summary="Get archive timeline",
    description="Chronological archive timeline grouped by month or year from real uploaded videos.",
)
def archive_timeline(
    granularity: str = Query("month", pattern="^(month|year)$", description="Bucket videos by month or year"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of videos to include"),
    db=Depends(get_db),
):
    return crud.get_archive_timeline(db, limit=limit, granularity=granularity)


@router.get(
    "/archive/intelligence",
    response_model=ArchiveIntelligenceResponse,
    summary="Get archive intelligence",
    description="Composed archive exploration response with timeline, topics, trending searches, and cited evidence.",
)
def archive_intelligence(
    topic_limit: int = Query(8, ge=1, le=20, description="Maximum number of topic cards to include"),
    period_limit: int = Query(24, ge=1, le=120, description="Maximum number of periods to include"),
    granularity: str = Query("month", pattern="^(month|week)$", description="Period granularity for cached intelligence"),
    date_from: date | None = Query(None, description="Lower bound for cached intelligence periods"),
    date_to: date | None = Query(None, description="Upper bound for cached intelligence periods"),
    period: str | None = Query(None, description="Predefined archive period slug"),
    db=Depends(get_db),
):
    return get_archive_intelligence(
        db,
        topic_limit=topic_limit,
        period_limit=period_limit,
        granularity=granularity,
        date_from=date_from,
        date_to=date_to,
        period=period,
    )


@router.get(
    "/archive/intelligence/periods",
    response_model=ArchivePeriodOptionsResponse,
    summary="List archive intelligence periods",
    description="Return predefined archive periods and cached counts for the archive intelligence UI.",
)
def archive_intelligence_periods(
    kind: str | None = Query(None, description="Optional period kind filter"),
    limit: int = Query(120, ge=1, le=500, description="Maximum number of periods to include"),
    db=Depends(get_db),
):
    return get_archive_period_options(db, kind=kind, limit=limit)


@router.get(
    "/admin/archive/periods",
    response_model=ArchiveNamedPeriodAdminListResponse,
    summary="List archive periods (Admin)",
    description="List all predefined archive intelligence periods, including hidden drafts.",
)
def admin_archive_periods(
    kind: str | None = Query(None, description="Optional period kind filter"),
    status: str | None = Query(None, description="Optional period status filter"),
    q: str | None = Query(None, description="Search slug, label, or description"),
    limit: int = Query(200, ge=1, le=500, description="Maximum number of periods to include"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    return list_named_periods_admin(db, kind=kind, status=status, q=q, limit=limit, offset=offset)


@router.post(
    "/admin/archive/periods",
    response_model=ArchiveNamedPeriodAdminResponse,
    summary="Create archive period (Admin)",
    description="Create a predefined archive intelligence period.",
)
def admin_create_archive_period(
    payload: ArchiveNamedPeriodCreate,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    period = create_named_period(db, payload)
    if period is None:
        raise NotFoundError("Archive period could not be created", resource_type="archive_named_period")
    db.commit()
    refreshed = refresh_named_period_stats_for_slug(db, period.slug)
    db.commit()
    return refreshed or period


@router.patch(
    "/admin/archive/periods/{slug}",
    response_model=ArchiveNamedPeriodAdminResponse,
    summary="Update archive period (Admin)",
    description="Update a predefined archive intelligence period.",
)
def admin_update_archive_period(
    slug: str,
    payload: ArchiveNamedPeriodUpdate,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    period = update_named_period(db, slug, payload)
    if period is None:
        raise NotFoundError(f"Archive period {slug} not found", resource_type="archive_named_period")
    db.commit()
    refreshed = refresh_named_period_stats_for_slug(db, slug)
    db.commit()
    return refreshed or period


@router.post(
    "/admin/archive/periods/{slug}/refresh",
    response_model=ArchiveNamedPeriodAdminResponse,
    summary="Refresh archive period stats (Admin)",
    description="Recalculate cached stats for a predefined archive intelligence period.",
)
def admin_refresh_archive_period(
    slug: str,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    refreshed = refresh_named_period_stats_for_slug(db, slug)
    if refreshed is None:
        raise NotFoundError(f"Archive period {slug} not found", resource_type="archive_named_period")
    db.commit()
    return refreshed


@router.post(
    "/admin/archive/periods/seed",
    summary="Seed archive periods (Admin)",
    description="Seed curated archive periods and refresh cached stats.",
)
def admin_seed_archive_periods(
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    seeded = seed_named_periods(db)
    db.commit()
    refreshed = refresh_named_period_stats(db)
    db.commit()
    return {"seeded": seeded.get("periods", 0), "refreshed": refreshed.get("rows", 0)}


@router.get(
    "/admin/archive/metadata/people",
    response_model=ArchivePersonAdminListResponse,
    summary="List archive people (Admin)",
)
def admin_list_archive_people(
    q: str | None = Query(None, description="Search slug, display name, aliases, or description"),
    status: str | None = Query(None, description="Optional person status filter"),
    limit: int = Query(200, ge=1, le=500, description="Maximum number of people to include"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    return ArchivePersonAdminListResponse(items=list_people_admin(db, q=q, status=status, limit=limit, offset=offset))


@router.post(
    "/admin/archive/metadata/people",
    response_model=ArchivePersonAdmin,
    summary="Create archive person (Admin)",
)
def admin_create_archive_person(
    payload: ArchivePersonCreate,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    person = create_person(db, payload.model_dump(exclude_none=True))
    db.commit()
    return ArchivePersonAdmin(**person)


@router.patch(
    "/admin/archive/metadata/people/{slug}",
    response_model=ArchivePersonAdmin,
    summary="Update archive person (Admin)",
)
def admin_update_archive_person(
    slug: str,
    payload: ArchivePersonUpdate,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    person = update_person(db, slug, payload.model_dump(exclude_none=True))
    if person is None:
        raise NotFoundError(f"Archive person {slug} not found", resource_type="archive_person")
    db.commit()
    invalidate_cache_pattern("video:*")
    return ArchivePersonAdmin(**person)


@router.get(
    "/admin/archive/metadata/tags",
    response_model=ArchiveVideoTagAdminListResponse,
    summary="List archive tags (Admin)",
)
def admin_list_archive_tags(
    q: str | None = Query(None, description="Search slug, label, or description"),
    status: str | None = Query(None, description="Optional tag status filter"),
    kind: str | None = Query(None, description="Optional tag kind filter"),
    limit: int = Query(200, ge=1, le=500, description="Maximum number of tags to include"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    return ArchiveVideoTagAdminListResponse(items=list_tags_admin(db, q=q, status=status, kind=kind, limit=limit, offset=offset))


@router.post(
    "/admin/archive/metadata/tags",
    response_model=ArchiveVideoTagAdmin,
    summary="Create archive tag (Admin)",
)
def admin_create_archive_tag(
    payload: ArchiveVideoTagCreate,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    tag = create_tag(db, payload.model_dump(exclude_none=True))
    db.commit()
    return ArchiveVideoTagAdmin(**tag)


@router.patch(
    "/admin/archive/metadata/tags/{slug}",
    response_model=ArchiveVideoTagAdmin,
    summary="Update archive tag (Admin)",
)
def admin_update_archive_tag(
    slug: str,
    payload: ArchiveVideoTagUpdate,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    tag = update_tag(db, slug, payload.model_dump(exclude_none=True))
    if tag is None:
        raise NotFoundError(f"Archive tag {slug} not found", resource_type="archive_video_tag")
    db.commit()
    invalidate_cache_pattern("video:*")
    return ArchiveVideoTagAdmin(**tag)


@router.get(
    "/admin/archive/metadata/videos",
    response_model=ArchiveVideoMetadataAdminListResponse,
    summary="Search archive videos with metadata (Admin)",
)
def admin_search_archive_videos_with_metadata(
    q: str | None = Query(None, description="Search title, YouTube ID, or channel name"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of videos to include"),
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    return ArchiveVideoMetadataAdminListResponse(items=[ArchiveVideoMetadataAdminVideo(**dict(row)) for row in search_videos_for_admin(db, q=q, limit=limit)])


@router.get(
    "/admin/archive/metadata/videos/{video_id}",
    response_model=ArchiveVideoMetadataAdminVideo,
    summary="Get archive video metadata (Admin)",
)
def admin_get_archive_video_metadata(
    video_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    video = _admin_video_metadata_response(db, video_id)
    if video is None:
        raise NotFoundError(f"Video {video_id} not found", resource_type="video")
    return video


@router.put(
    "/admin/archive/metadata/videos/{video_id}",
    response_model=ArchiveVideoMetadataAdminVideo,
    summary="Set archive video metadata (Admin)",
)
def admin_set_archive_video_metadata(
    video_id: uuid.UUID,
    payload: ArchiveVideoMetadataUpdate,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    set_video_metadata(
        db,
        video_id,
        people=[item.model_dump(exclude_none=True) for item in payload.people],
        tags=[item.model_dump(exclude_none=True) for item in payload.tags],
    )
    db.commit()
    invalidate_cache("video", video_id)
    video = _admin_video_metadata_response(db, video_id)
    if video is None:
        raise NotFoundError(f"Video {video_id} not found", resource_type="video")
    return video


@router.post(
    "/admin/archive/metadata/seed-tags",
    summary="Seed archive metadata tags (Admin)",
)
def admin_seed_archive_metadata_tags(
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    seeded = seed_default_tags(db)
    db.commit()
    invalidate_cache_pattern("video:*")
    return seeded
