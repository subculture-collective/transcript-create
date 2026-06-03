import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text as _text

from ..common.session import get_session_token as _get_session_token
from ..common.session import get_user_from_session as _get_user_from_session
from ..common.session import is_admin as _is_admin
from ..db import get_db
from ..exceptions import ExternalServiceError, ValidationError
from ..schemas import (
    ErrorResponse,
    GroupedSearchResponse,
    MentionMap,
    SearchAnalytics,
    SearchHistoryResponse,
    SearchHit,
    SearchResponse,
    SearchSuggestionsResponse,
)
from ..search.analytics import get_popular_searches as _get_popular_searches
from ..search.analytics import get_search_analytics as _get_search_analytics
from ..search.analytics import get_search_suggestions as _get_search_suggestions
from ..search.orchestrator import SearchOrchestrator

router = APIRouter(prefix="", tags=["Search"])
_search_orchestrator = SearchOrchestrator()


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Search transcripts",
    description="""
    Full-text search across all transcripts with pagination and filtering.

    Search can use either PostgreSQL full-text search (default) or OpenSearch
    backend for enhanced relevance and performance.

    **Search Sources:**
    - `best`: Search Whisper where available, otherwise YouTube captions
    - `native`: Search Whisper-generated transcripts
    - `youtube`: Search YouTube's native closed captions

    **Access:**
    - Account plans are unrestricted
    - Unauthenticated search is allowed

    **Search Backend:**
    - `postgres`: Basic full-text search with tsquery
    - `opensearch`: Advanced search with relevance scoring, highlighting, and phrase matching
    """,
    responses={
        200: {
            "description": "Search results retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "total": 42,
                        "hits": [
                            {
                                "id": 12345,
                                "video_id": "123e4567-e89b-12d3-a456-426614174000",
                                "start_ms": 45000,
                                "end_ms": 48500,
                                "snippet": "This is an example of <em>search term</em> in context",
                            }
                        ],
                    }
                }
            },
        },
        400: {
            "description": "Validation error - empty query or invalid parameters",
            "model": ErrorResponse,
        },
        401: {
            "description": "Authentication required",
            "model": ErrorResponse,
        },
        503: {
            "description": "Search backend unavailable",
            "model": ErrorResponse,
        },
    },
)
def search(
    request: Request,
    q: str = Query(..., min_length=1, max_length=500, description="Search query text"),
    source: str = Query("best", description="Search source: 'best', 'native', or 'youtube'"),
    video_id: uuid.UUID | None = Query(None, description="Filter results to specific video"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip for pagination"),
    # Advanced filters
    date_from: str | None = Query(None, description="Filter videos uploaded after this date (ISO format)"),
    date_to: str | None = Query(None, description="Filter videos uploaded before this date (ISO format)"),
    min_duration: int | None = Query(None, ge=0, description="Minimum video duration in seconds"),
    max_duration: int | None = Query(None, ge=0, description="Maximum video duration in seconds"),
    channel: str | None = Query(None, description="Filter by channel name"),
    language: str | None = Query(None, description="Filter by language code (e.g., 'en', 'es')"),
    has_speaker_labels: bool | None = Query(None, description="Filter videos with speaker diarization"),
    category: str | None = Query(None, description="Filter by video category/type"),
    sort_by: str = Query(
        "relevance", description="Sort results by: relevance, date_asc, date_desc, duration_asc, duration_desc"
    ),
    db=Depends(get_db),
):
    """Search across transcripts with full-text search and advanced filters."""
    if not q or not q.strip():
        raise ValidationError("Search query cannot be empty", field="q")
    if source not in ("best", "native", "youtube"):
        raise ValidationError("Invalid source. Must be 'best', 'native', or 'youtube'", field="source")
    if limit < 1 or limit > 200:
        raise ValidationError("Limit must be between 1 and 200", field="limit")
    if sort_by not in ("relevance", "date_asc", "date_desc", "duration_asc", "duration_desc"):
        raise ValidationError("Invalid sort_by value", field="sort_by")
    return _search_orchestrator.search(
        db,
        request,
        q=q,
        source=source,
        video_id=video_id,
        limit=limit,
        offset=offset,
        date_from=date_from,
        date_to=date_to,
        min_duration=min_duration,
        max_duration=max_duration,
        channel=channel,
        language=language,
        has_speaker_labels=has_speaker_labels,
        category=category,
        sort_by=sort_by,
    )
@router.get(
    "/search/suggestions",
    response_model=SearchSuggestionsResponse,
    summary="Get search suggestions",
    description="""
    Get search suggestions for autocomplete based on:
    - Previous searches (most frequent)
    - Partial match on query prefix

    Useful for implementing autocomplete functionality.
    """,
)
def get_search_suggestions(
    q: str = Query(..., min_length=1, max_length=100, description="Query prefix to match"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of suggestions"),
    db=Depends(get_db),
):
    """Get search suggestions for autocomplete."""
    return _get_search_suggestions(db, q, limit)


@router.get(
    "/search/history",
    response_model=SearchHistoryResponse,
    summary="Get search history",
    description="""
    Get user's recent search history.

    Returns the user's most recent searches with filters and result counts.
    Requires authentication.
    """,
)
def get_search_history(
    request: Request,
    limit: int = Query(20, ge=1, le=100, description="Maximum number of history items"),
    db=Depends(get_db),
):
    """Get user's search history."""
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        return SearchHistoryResponse(items=[])

    rows = (
        db.execute(
            _text(
                """
            SELECT query, filters, result_count, created_at
            FROM user_searches
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            LIMIT :limit
        """
            ),
            {"user_id": str(user["id"]), "limit": limit},
        )
        .mappings()
        .all()
    )

    from ..schemas import SearchHistoryItem

    items = [
        SearchHistoryItem(
            query=r["query"], filters=r["filters"], result_count=r["result_count"], created_at=r["created_at"]
        )
        for r in rows
    ]

    return SearchHistoryResponse(items=items)


@router.get(
    "/search/popular",
    response_model=SearchSuggestionsResponse,
    summary="Get popular searches",
    description="""
    Get globally popular search terms.

    Returns the most frequently searched terms across all users.
    """,
)
def get_popular_searches(
    limit: int = Query(20, ge=1, le=100, description="Maximum number of popular searches"),
    db=Depends(get_db),
):
    """Get popular search terms."""
    return _get_popular_searches(db, limit)


@router.get(
    "/admin/search/analytics",
    response_model=SearchAnalytics,
    summary="Search analytics dashboard (Admin)",
    description="""
    Get search analytics and insights.

    **Admin Only:** Requires admin privileges

    Returns:
    - Popular search terms
    - Zero-result searches (to improve indexing)
    - Search volume over time
    - Average results per query
    """,
)
def get_search_analytics(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db=Depends(get_db),
):
    """Get search analytics (admin only)."""
    return _get_search_analytics(request, db, days)


@router.get(
    "/search/export",
    summary="Export search results",
    description="""
    Export search results to CSV or JSON format.

    Supports the same filters as the main search endpoint.
    Export format is determined by the `format` parameter.
    """,
    responses={
        200: {
            "description": "Search results exported successfully",
            "content": {
                "text/csv": {},
                "application/json": {},
            },
        },
    },
)
def export_search_results(
    request: Request,
    q: str = Query(..., min_length=1, max_length=500, description="Search query text"),
    format: str = Query("csv", description="Export format: 'csv' or 'json'"),
    source: str = Query("best", description="Search source: 'best', 'native', or 'youtube'"),
    video_id: uuid.UUID | None = Query(None, description="Filter results to specific video"),
    limit: int = Query(500, ge=1, le=1000, description="Maximum number of results to export"),
    # Advanced filters
    date_from: str | None = Query(None, description="Filter videos uploaded after this date (ISO format)"),
    date_to: str | None = Query(None, description="Filter videos uploaded before this date (ISO format)"),
    min_duration: int | None = Query(None, ge=0, description="Minimum video duration in seconds"),
    max_duration: int | None = Query(None, ge=0, description="Maximum video duration in seconds"),
    channel: str | None = Query(None, description="Filter by channel name"),
    language: str | None = Query(None, description="Filter by language code (e.g., 'en', 'es')"),
    has_speaker_labels: bool | None = Query(None, description="Filter videos with speaker diarization"),
    sort_by: str = Query("relevance", description="Sort results by: relevance, date_asc, date_desc"),
    db=Depends(get_db),
):
    """Export search results to CSV or JSON."""
    if not q or not q.strip():
        raise ValidationError("Search query cannot be empty", field="q")
    if source not in ("best", "native", "youtube"):
        raise ValidationError("Invalid source. Must be 'best', 'native', or 'youtube'", field="source")
    if format not in ("csv", "json"):
        raise ValidationError("Invalid format. Must be 'csv' or 'json'", field="format")

    rows, video_details = _search_orchestrator.prepare_export_rows(
        db,
        q=q,
        format=format,
        source=source,
        video_id=video_id,
        limit=limit,
        date_from=date_from,
        date_to=date_to,
        min_duration=min_duration,
        max_duration=max_duration,
        channel=channel,
        language=language,
        has_speaker_labels=has_speaker_labels,
        sort_by=sort_by,
    )

    if format == "json":
        from fastapi.responses import JSONResponse

        results = []
        for r in rows:
            vid = str(r["video_id"])
            video_info = video_details.get(vid, {})
            results.append(
                {
                    "segment_id": r["id"],
                    "video_id": vid,
                    "youtube_id": video_info.get("youtube_id"),
                    "title": video_info.get("title"),
                    "start_ms": r["start_ms"],
                    "end_ms": r["end_ms"],
                    "text": r["snippet"],
                }
            )

        return JSONResponse(content={"query": q, "source": source, "results": results, "count": len(results)})
    else:  # CSV
        from fastapi.responses import PlainTextResponse

        def esc(x):
            s = str(x) if x is not None else ""
            if any(c in s for c in [",", '"', "\n"]):
                s = '"' + s.replace('"', '""') + '"'
            return s

        # Build CSV
        header = "segment_id,video_id,youtube_id,title,start_ms,end_ms,text\n"
        body = ""
        for r in rows:
            vid = str(r["video_id"])
            video_info = video_details.get(vid, {})
            body += (
                f"{esc(r['id'])},"
                f"{esc(vid)},"
                f"{esc(video_info.get('youtube_id'))},"
                f"{esc(video_info.get('title'))},"
                f"{esc(r['start_ms'])},"
                f"{esc(r['end_ms'])},"
                f"{esc(r['snippet'])}\n"
            )

        return PlainTextResponse(content=header + body, media_type="text/csv")


@router.get(
    "/search/grouped",
    response_model=GroupedSearchResponse,
    summary="Search transcripts grouped by episode",
    description="Search transcripts and group timestamped matches by video.",
)
def search_grouped(
    request: Request,
    q: str = Query(..., min_length=1, max_length=500, description="Search query text"),
    source: str = Query("best", description="Search source: 'best', 'native', or 'youtube'"),
    video_id: uuid.UUID | None = Query(None, description="Filter results to specific video"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip for pagination"),
    date_from: str | None = Query(None, description="Filter videos uploaded after this date (ISO format)"),
    date_to: str | None = Query(None, description="Filter videos uploaded before this date (ISO format)"),
    min_duration: int | None = Query(None, ge=0, description="Minimum video duration in seconds"),
    max_duration: int | None = Query(None, ge=0, description="Maximum video duration in seconds"),
    channel: str | None = Query(None, description="Filter by channel name"),
    language: str | None = Query(None, description="Filter by language code (e.g., 'en', 'es')"),
    has_speaker_labels: bool | None = Query(None, description="Filter videos with speaker diarization"),
    category: str | None = Query(None, description="Filter by video category/type"),
    sort_by: str = Query(
        "relevance", description="Sort results by: relevance, date_asc, date_desc, duration_asc, duration_desc"
    ),
    db=Depends(get_db),
):
    if not q or not q.strip():
        raise ValidationError("Search query cannot be empty", field="q")
    if source not in ("best", "native", "youtube"):
        raise ValidationError("Invalid source. Must be 'best', 'native', or 'youtube'", field="source")
    if limit < 1 or limit > 200:
        raise ValidationError("Limit must be between 1 and 200", field="limit")
    if sort_by not in ("relevance", "date_asc", "date_desc", "duration_asc", "duration_desc"):
        raise ValidationError("Invalid sort_by value", field="sort_by")

    return _search_orchestrator.grouped_search(
        db,
        request,
        q=q,
        source=source,
        video_id=video_id,
        limit=limit,
        offset=offset,
        date_from=date_from,
        date_to=date_to,
        min_duration=min_duration,
        max_duration=max_duration,
        channel=channel,
        language=language,
        has_speaker_labels=has_speaker_labels,
        category=category,
        sort_by=sort_by,
    )


@router.get(
    "/search/mention-map",
    response_model=MentionMap,
    summary="Build a citation-backed mention map",
    description="Search transcripts and return the first, latest, and top episode mentions for a query.",
)
def search_mention_map(
    request: Request,
    q: str = Query(..., min_length=1, max_length=500, description="Search query text"),
    source: str = Query("best", description="Search source: 'best', 'native', or 'youtube'"),
    video_id: uuid.UUID | None = Query(None, description="Filter results to specific video"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results to consider"),
    offset: int = Query(0, ge=0, description="Number of results to skip for pagination"),
    date_from: str | None = Query(None, description="Filter videos uploaded after this date (ISO format)"),
    date_to: str | None = Query(None, description="Filter videos uploaded before this date (ISO format)"),
    min_duration: int | None = Query(None, ge=0, description="Minimum video duration in seconds"),
    max_duration: int | None = Query(None, ge=0, description="Maximum video duration in seconds"),
    channel: str | None = Query(None, description="Filter by channel name"),
    language: str | None = Query(None, description="Filter by language code (e.g., 'en', 'es')"),
    has_speaker_labels: bool | None = Query(None, description="Filter videos with speaker diarization"),
    category: str | None = Query(None, description="Filter by video category/type"),
    sort_by: str = Query(
        "relevance", description="Sort results by: relevance, date_asc, date_desc, duration_asc, duration_desc"
    ),
    top_limit: int = Query(5, ge=1, le=20, description="Number of top episodes to include"),
    db=Depends(get_db),
):
    if not q or not q.strip():
        raise ValidationError("Search query cannot be empty", field="q")
    if source not in ("best", "native", "youtube"):
        raise ValidationError("Invalid source. Must be 'best', 'native', or 'youtube'", field="source")
    if limit < 1 or limit > 200:
        raise ValidationError("Limit must be between 1 and 200", field="limit")
    if sort_by not in ("relevance", "date_asc", "date_desc", "duration_asc", "duration_desc"):
        raise ValidationError("Invalid sort_by value", field="sort_by")

    return _search_orchestrator.mention_map(
        db,
        request,
        q=q,
        source=source,
        video_id=video_id,
        limit=limit,
        offset=offset,
        date_from=date_from,
        date_to=date_to,
        min_duration=min_duration,
        max_duration=max_duration,
        channel=channel,
        language=language,
        has_speaker_labels=has_speaker_labels,
        category=category,
        sort_by=sort_by,
        top_limit=top_limit,
    )
