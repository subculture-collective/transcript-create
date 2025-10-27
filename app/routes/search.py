import time
import uuid
from typing import Any, Dict

import requests
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy import text as _text

from ..common.session import get_session_token as _get_session_token
from ..common.session import get_user_from_session as _get_user_from_session
from ..common.session import is_admin as _is_admin
from ..db import get_db
from ..exceptions import ExternalServiceError, QuotaExceededError, ValidationError
from ..schemas import (
    ErrorResponse,
    SearchAnalytics,
    SearchHistoryResponse,
    SearchHit,
    SearchResponse,
    SearchSuggestionsResponse,
)
from ..settings import settings

router = APIRouter(prefix="", tags=["Search"])


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Search transcripts",
    description="""
    Full-text search across all transcripts with pagination and filtering.

    Search can use either PostgreSQL full-text search (default) or OpenSearch
    backend for enhanced relevance and performance.

    **Search Sources:**
    - `native`: Search Whisper-generated transcripts
    - `youtube`: Search YouTube's native closed captions

    **Rate Limits:**
    - Free plan: Limited daily searches (see /auth/me for your quota)
    - Pro plan: Unlimited searches
    - Unauthenticated: Not allowed

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
        429: {
            "description": "Rate limit exceeded for free plan",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "error": "quota_exceeded",
                        "message": "Daily search limit of 100 reached. Upgrade to Pro for unlimited searches.",
                        "details": {
                            "resource": "searches",
                            "limit": 100,
                            "used": 100,
                            "plan": "free",
                        },
                    }
                }
            },
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
    source: str = Query("native", description="Search source: 'native' or 'youtube'"),
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
    sort_by: str = Query(
        "relevance", description="Sort results by: relevance, date_asc, date_desc, duration_asc, duration_desc"
    ),
    db=Depends(get_db),
):
    """Search across transcripts with full-text search and advanced filters."""
    start_time = time.time()

    if not q or not q.strip():
        raise ValidationError("Search query cannot be empty", field="q")
    if source not in ("native", "youtube"):
        raise ValidationError("Invalid source. Must be 'native' or 'youtube'", field="source")
    if limit < 1 or limit > 200:
        raise ValidationError("Limit must be between 1 and 200", field="limit")
    if sort_by not in ("relevance", "date_asc", "date_desc", "duration_asc", "duration_desc"):
        raise ValidationError("Invalid sort_by value", field="sort_by")

    user = _get_user_from_session(db, _get_session_token(request))

    # Track search suggestion
    _update_search_suggestion(db, q)

    if user and not _is_admin(user):
        plan = (user.get("plan") or "free").lower()
        if plan == "free":
            used = db.execute(
                text(
                    """
                SELECT COUNT(*) FROM events
                WHERE user_id=:u AND type='search_api'
                  AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC')
            """
                ),
                {"u": str(user["id"])},
            ).scalar_one()
            if used >= settings.FREE_DAILY_SEARCH_LIMIT:
                raise QuotaExceededError(
                    resource="searches",
                    limit=settings.FREE_DAILY_SEARCH_LIMIT,
                    used=used,
                    plan=plan,
                )
            db.execute(
                _text("INSERT INTO events (user_id, session_token, type, payload) VALUES (:u,:t,'search_api',:p)"),
                {"u": str(user["id"]), "t": _get_session_token(request), "p": {"q": q, "source": source}},
            )
            db.commit()
    if settings.SEARCH_BACKEND == "opensearch":
        index = settings.OPENSEARCH_INDEX_NATIVE if source == "native" else settings.OPENSEARCH_INDEX_YOUTUBE
        query: Dict[str, Any] = {
            "from": offset,
            "size": limit,
            "query": {
                "bool": {
                    "should": [
                        {"multi_match": {"query": q, "type": "phrase", "fields": ["text^3", "text.shingle^4"]}},
                        {"multi_match": {"query": q, "fields": ["text^2", "text.ngram^0.5", "text.edge^1.5"]}},
                        {"prefix": {"text.edge": {"value": q.lower(), "boost": 1.2}}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "highlight": {"fields": {"text": {"number_of_fragments": 3, "fragment_size": 180}}},
        }
        if video_id:
            bool_query: Dict[str, Any] = query["query"]["bool"]  # type: ignore[assignment]
            bool_query.setdefault("filter", []).append({"term": {"video_id": str(video_id)}})
        try:
            r = requests.post(f"{settings.OPENSEARCH_URL}/{index}/_search", json=query, timeout=10)
            r.raise_for_status()
            data = r.json()
        except requests.exceptions.Timeout:
            raise ExternalServiceError("OpenSearch", "Request timeout")
        except requests.exceptions.HTTPError as e:
            # Provide detailed error message for HTTP errors
            status_code = e.response.status_code if e.response is not None else "Unknown"
            content = e.response.text if e.response is not None else ""
            raise ExternalServiceError("OpenSearch", f"HTTP error {status_code}: {content or str(e)}")
        except requests.exceptions.RequestException as e:
            raise ExternalServiceError("OpenSearch", f"Connection failed: {str(e)}")
        except Exception as e:
            raise ExternalServiceError("OpenSearch", str(e))

        hits = []
        for h in data.get("hits", {}).get("hits", []):
            src = h.get("_source", {})
            hl = h.get("highlight", {}).get("text", [src.get("text", "")])
            hits.append(
                SearchHit(
                    id=int(src.get("id")),
                    video_id=uuid.UUID(src.get("video_id")),
                    start_ms=int(src.get("start_ms", 0)),
                    end_ms=int(src.get("end_ms", 0)),
                    snippet=hl[0],
                )
            )
        total = (
            data.get("hits", {}).get("total", {}).get("value")
            if isinstance(data.get("hits", {}).get("total"), dict)
            else None
        )
        query_time_ms = int((time.time() - start_time) * 1000)

        # Save search history
        if user:
            _save_search_history(
                db,
                user["id"],
                q,
                {
                    "source": source,
                    "video_id": str(video_id) if video_id else None,
                    "date_from": date_from,
                    "date_to": date_to,
                    "min_duration": min_duration,
                    "max_duration": max_duration,
                    "channel": channel,
                    "language": language,
                    "has_speaker_labels": has_speaker_labels,
                    "sort_by": sort_by,
                },
                total or len(hits),
                query_time_ms,
            )

        return SearchResponse(total=total, hits=hits, query_time_ms=query_time_ms)
    from .. import crud

    # Build filter parameters
    filters = {}
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to
    if min_duration is not None:
        filters["min_duration"] = min_duration
    if max_duration is not None:
        filters["max_duration"] = max_duration
    if channel:
        filters["channel"] = channel
    if language:
        filters["language"] = language
    if has_speaker_labels is not None:
        filters["has_speaker_labels"] = has_speaker_labels

    if source == "native":
        rows = crud.search_segments_advanced(
            db,
            q=q,
            video_id=str(video_id) if video_id else None,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            filters=filters,
        )
    else:
        rows = crud.search_youtube_segments_advanced(
            db,
            q=q,
            video_id=str(video_id) if video_id else None,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            filters=filters,
        )
    hits = [
        SearchHit(
            id=r["id"], video_id=r["video_id"], start_ms=r["start_ms"], end_ms=r["end_ms"], snippet=r["snippet"] or ""
        )
        for r in rows
    ]

    query_time_ms = int((time.time() - start_time) * 1000)

    # Save search history
    if user:
        _save_search_history(
            db,
            user["id"],
            q,
            {
                "source": source,
                "video_id": str(video_id) if video_id else None,
                **filters,
                "sort_by": sort_by,
            },
            len(hits),
            query_time_ms,
        )

    return SearchResponse(hits=hits, query_time_ms=query_time_ms)


def _update_search_suggestion(db, term: str):
    """Update search suggestions table with the search term."""
    try:
        term_lower = term.strip().lower()
        if not term_lower or len(term_lower) < 2:
            return

        # Upsert: increment frequency if exists, insert if not
        db.execute(
            _text(
                """
                INSERT INTO search_suggestions (term, frequency, last_used)
                VALUES (:term, 1, now())
                ON CONFLICT ((LOWER(term)))
                DO UPDATE SET
                    frequency = search_suggestions.frequency + 1,
                    last_used = now()
            """
            ),
            {"term": term_lower},
        )
        db.commit()
    except Exception:
        # Don't fail the search if suggestion tracking fails
        db.rollback()


def _save_search_history(db, user_id: str, query: str, filters: dict, result_count: int, query_time_ms: int):
    """Save search to user history."""
    try:
        import json

        db.execute(
            _text(
                """
                INSERT INTO user_searches (user_id, query, filters, result_count, query_time_ms)
                VALUES (:user_id, :query, :filters, :result_count, :query_time_ms)
            """
            ),
            {
                "user_id": user_id,
                "query": query,
                "filters": json.dumps(filters),
                "result_count": result_count,
                "query_time_ms": query_time_ms,
            },
        )
        db.commit()
    except Exception:
        # Don't fail the search if history saving fails
        db.rollback()


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
    term_lower = q.strip().lower()

    rows = (
        db.execute(
            _text(
                """
            SELECT term, frequency
            FROM search_suggestions
            WHERE LOWER(term) LIKE :pattern
            ORDER BY frequency DESC, last_used DESC
            LIMIT :limit
        """
            ),
            {"pattern": f"{term_lower}%", "limit": limit},
        )
        .mappings()
        .all()
    )

    from ..schemas import SearchSuggestion

    suggestions = [SearchSuggestion(term=r["term"], frequency=r["frequency"]) for r in rows]

    return SearchSuggestionsResponse(suggestions=suggestions)


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
    rows = (
        db.execute(
            _text(
                """
            SELECT term, frequency
            FROM search_suggestions
            ORDER BY frequency DESC, last_used DESC
            LIMIT :limit
        """
            ),
            {"limit": limit},
        )
        .mappings()
        .all()
    )

    from ..schemas import SearchSuggestion

    suggestions = [SearchSuggestion(term=r["term"], frequency=r["frequency"]) for r in rows]

    return SearchSuggestionsResponse(suggestions=suggestions)


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
    user = _get_user_from_session(db, _get_session_token(request))
    if not _is_admin(user):
        from ..exceptions import AuthorizationError

        raise AuthorizationError("Admin access required")

    # Popular terms
    popular_terms = (
        db.execute(
            _text(
                """
            SELECT term, frequency, last_used
            FROM search_suggestions
            ORDER BY frequency DESC
            LIMIT 20
        """
            )
        )
        .mappings()
        .all()
    )

    # Zero-result searches
    zero_results = (
        db.execute(
            _text(
                """
            SELECT query, COUNT(*) as count
            FROM user_searches
            WHERE result_count = 0
              AND created_at >= now() - INTERVAL ':days days'
            GROUP BY query
            ORDER BY count DESC
            LIMIT 20
        """
            ),
            {"days": days},
        )
        .mappings()
        .all()
    )

    # Search volume over time
    search_volume = (
        db.execute(
            _text(
                """
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM user_searches
            WHERE created_at >= now() - INTERVAL ':days days'
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        """
            ),
            {"days": days},
        )
        .mappings()
        .all()
    )

    # Average results per query
    # Note: AVG() returns NULL when there are no rows, which is preserved as None
    # This distinguishes between "no data" (None) and "average of 0 results" (0.0)
    avg_results = db.execute(
        _text(
            """
            SELECT AVG(result_count) as avg_results
            -- Note: ::float cast removed; cast to float is now done in Python (see line 594) to preserve NULL as None
            FROM user_searches
            WHERE created_at >= now() - INTERVAL ':days days'
              AND result_count IS NOT NULL
        """
        ),
        {"days": days},
    ).scalar_one_or_none()
    # Convert to float only if not None
    if avg_results is not None:
        avg_results = float(avg_results)

    # Total searches
    total = db.execute(
        _text(
            """
            SELECT COUNT(*) FROM user_searches
            WHERE created_at >= now() - INTERVAL ':days days'
        """
        ),
        {"days": days},
    ).scalar_one()

    return SearchAnalytics(
        popular_terms=[
            {"term": r["term"], "frequency": r["frequency"], "last_used": str(r["last_used"])} for r in popular_terms
        ],
        zero_result_searches=[{"query": r["query"], "count": r["count"]} for r in zero_results],
        search_volume=[{"date": str(r["date"]), "count": r["count"]} for r in search_volume],
        avg_results_per_query=avg_results,
        total_searches=total,
    )


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
    source: str = Query("native", description="Search source: 'native' or 'youtube'"),
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
    if source not in ("native", "youtube"):
        raise ValidationError("Invalid source. Must be 'native' or 'youtube'", field="source")
    if format not in ("csv", "json"):
        raise ValidationError("Invalid format. Must be 'csv' or 'json'", field="format")

    _get_user_from_session(db, _get_session_token(request))

    # Build filter parameters
    filters = {}
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to
    if min_duration is not None:
        filters["min_duration"] = min_duration
    if max_duration is not None:
        filters["max_duration"] = max_duration
    if channel:
        filters["channel"] = channel
    if language:
        filters["language"] = language
    if has_speaker_labels is not None:
        filters["has_speaker_labels"] = has_speaker_labels

    from .. import crud

    if source == "native":
        rows = crud.search_segments_advanced(
            db,
            q=q,
            video_id=str(video_id) if video_id else None,
            limit=limit,
            offset=0,
            sort_by=sort_by,
            filters=filters,
        )
    else:
        rows = crud.search_youtube_segments_advanced(
            db,
            q=q,
            video_id=str(video_id) if video_id else None,
            limit=limit,
            offset=0,
            sort_by=sort_by,
            filters=filters,
        )

    # Get video details for each result
    video_details = {}
    for r in rows:
        vid = str(r["video_id"])
        if vid not in video_details:
            video_row = (
                db.execute(
                    _text("SELECT youtube_id, title, duration_seconds FROM videos WHERE id = :vid"), {"vid": vid}
                )
                .mappings()
                .first()
            )
            if video_row:
                video_details[vid] = video_row

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
