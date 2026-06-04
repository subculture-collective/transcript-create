from fastapi import APIRouter, Depends, Query
from datetime import date

from .. import crud
from ..archive.repository import archive_repository
from ..db import get_db
from ..archive.intelligence import get_archive_intelligence
from ..schemas import ArchiveIntelligenceResponse, ArchiveSummary, ArchiveTimelineResponse

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
    db=Depends(get_db),
):
    return get_archive_intelligence(
        db,
        topic_limit=topic_limit,
        period_limit=period_limit,
        granularity=granularity,
        date_from=date_from,
        date_to=date_to,
    )
