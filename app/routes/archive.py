from fastapi import APIRouter, Depends, Query
from datetime import date

from .. import crud
from ..archive.repository import archive_repository
from ..archive.intelligence import get_archive_intelligence, get_archive_period_options
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
    ArchiveNamedPeriodAdminListResponse,
    ArchiveNamedPeriodAdminResponse,
    ArchiveNamedPeriodCreate,
    ArchiveNamedPeriodUpdate,
    ArchivePeriodOptionsResponse,
    ArchiveSummary,
    ArchiveTimelineResponse,
)
from ..security import ROLE_ADMIN, require_role

router = APIRouter(prefix="", tags=["Archive"])


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
