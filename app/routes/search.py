from fastapi import APIRouter, Depends, Query, Request

from ..common.session import get_session_token as _get_session_token
from ..common.session import get_user_from_session as _get_user_from_session
from ..common.session import is_admin as _is_admin
from ..db import get_db
from ..exceptions import ExternalServiceError, QuotaExceededError, ValidationError
from ..schemas import ErrorResponse, SearchHit, SearchResponse
from ..settings import settings

router = APIRouter(prefix="", tags=["Search"])


import uuid
from typing import Any, Dict

import requests
from sqlalchemy import text
from sqlalchemy import text as _text


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
    db=Depends(get_db),
):
    """Search across transcripts with full-text search."""
    if not q or not q.strip():
        raise ValidationError("Search query cannot be empty", field="q")
    if source not in ("native", "youtube"):
        raise ValidationError("Invalid source. Must be 'native' or 'youtube'", field="source")
    if limit < 1 or limit > 200:
        raise ValidationError("Limit must be between 1 and 200", field="limit")

    user = _get_user_from_session(db, _get_session_token(request))
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
            raise ExternalServiceError(
                "OpenSearch",
                f"HTTP error {status_code}: {content or str(e)}"
            )
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
        return SearchResponse(total=total, hits=hits)
    from .. import crud

    if source == "native":
        rows = crud.search_segments(db, q=q, video_id=str(video_id) if video_id else None, limit=limit, offset=offset)
    else:
        rows = crud.search_youtube_segments(
            db, q=q, video_id=str(video_id) if video_id else None, limit=limit, offset=offset
        )
    hits = [
        SearchHit(
            id=r["id"], video_id=r["video_id"], start_ms=r["start_ms"], end_ms=r["end_ms"], snippet=r["snippet"] or ""
        )
        for r in rows
    ]
    return SearchResponse(hits=hits)
