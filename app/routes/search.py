import uuid
from typing import Any, Dict

import requests
from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy import text as _text

from ..common.session import get_session_token as _get_session_token
from ..common.session import get_user_from_session as _get_user_from_session
from ..common.session import is_admin as _is_admin
from ..db import get_db
from ..exceptions import ExternalServiceError, QuotaExceededError, ValidationError
from ..schemas import SearchHit, SearchResponse
from ..settings import settings

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
def search(
    request: Request,
    q: str,
    source: str = "native",
    video_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    db=Depends(get_db),
):
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
