from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from sqlalchemy import text as _text

from app.common.session import get_session_token as _get_session_token
from app.common.session import get_user_from_session as _get_user_from_session
from app.common.session import is_admin as _is_admin
from app.exceptions import AuthorizationError
from app.schemas import SearchAnalytics, SearchSuggestion, SearchSuggestionsResponse
from app.search.types import SearchRequestContext


def build_search_filters(
    date_from: str | None = None,
    date_to: str | None = None,
    min_duration: int | None = None,
    max_duration: int | None = None,
    channel: str | None = None,
    language: str | None = None,
    has_speaker_labels: bool | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
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
    if category:
        filters["category"] = category
    return filters


def update_search_suggestion(db, term: str) -> None:
    try:
        term_lower = term.strip().lower()
        if not term_lower or len(term_lower) < 2:
            return

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
        db.rollback()


def save_search_history(db, user_id: str, query: str, filters: dict[str, Any], result_count: int, query_time_ms: int) -> None:
    try:
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
        db.rollback()


def record_search_request(request: Request, db, q: str, source: str) -> SearchRequestContext:
    token = _get_session_token(request)
    user = _get_user_from_session(db, token)
    is_admin = _is_admin(user)

    update_search_suggestion(db, q)

    if user and not is_admin:
        db.execute(
            _text("INSERT INTO events (user_id, session_token, type, payload) VALUES (:u,:t,'search_api',:p)"),
            {"u": str(user["id"]), "t": token, "p": {"q": q, "source": source}},
        )
        db.commit()

    return SearchRequestContext(
        user_id=str(user["id"]) if user else None,
        session_token=token,
        is_admin=is_admin,
    )


def get_search_suggestions(db, q: str, limit: int) -> SearchSuggestionsResponse:
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
    return SearchSuggestionsResponse(suggestions=[SearchSuggestion(term=r["term"], frequency=r["frequency"]) for r in rows])


def get_popular_searches(db, limit: int) -> SearchSuggestionsResponse:
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
    return SearchSuggestionsResponse(suggestions=[SearchSuggestion(term=r["term"], frequency=r["frequency"]) for r in rows])


def get_search_analytics(request: Request, db, days: int) -> SearchAnalytics:
    user = _get_user_from_session(db, _get_session_token(request))
    if not _is_admin(user):
        raise AuthorizationError("Admin access required")

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

    zero_results = (
        db.execute(
            _text(
                """
            SELECT query, COUNT(*) as count
            FROM user_searches
            WHERE result_count = 0
              AND created_at >= now() - (:days * INTERVAL '1 day')
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

    search_volume = (
        db.execute(
            _text(
                """
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM user_searches
            WHERE created_at >= now() - (:days * INTERVAL '1 day')
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        """
            ),
            {"days": days},
        )
        .mappings()
        .all()
    )

    avg_results = db.execute(
        _text(
            """
            SELECT AVG(result_count) as avg_results
            FROM user_searches
            WHERE created_at >= now() - (:days * INTERVAL '1 day')
              AND result_count IS NOT NULL
        """
        ),
        {"days": days},
    ).scalar_one_or_none()
    if avg_results is not None:
        avg_results = float(avg_results)

    total = db.execute(
        _text(
            """
            SELECT COUNT(*) FROM user_searches
            WHERE created_at >= now() - (:days * INTERVAL '1 day')
        """
        ),
        {"days": days},
    ).scalar_one()

    return SearchAnalytics(
        popular_terms=[{"term": r["term"], "frequency": r["frequency"], "last_used": str(r["last_used"])} for r in popular_terms],
        zero_result_searches=[{"query": r["query"], "count": r["count"]} for r in zero_results],
        search_volume=[{"date": str(r["date"]), "count": r["count"]} for r in search_volume],
        avg_results_per_query=avg_results,
        total_searches=total,
    )
