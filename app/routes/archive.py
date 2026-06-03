from fastapi import APIRouter, Depends, Query

from .. import crud
from ..archive.repository import archive_repository
from ..db import get_db
from ..schemas import ArchiveSummary, ArchiveTimelineResponse

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
