from __future__ import annotations

import time
import uuid
from typing import Any, Dict

import requests
from fastapi import Request
from sqlalchemy import text as _text

from app import crud
from app.exceptions import ExternalServiceError, ValidationError
from app.schemas import GroupedSearchResponse, MentionMap, SearchHit, SearchResponse
from app.search import analytics as search_analytics
from app.search.repositories import PostgresSearchBackend
from app.search.service import SearchService
from app.search.types import SearchRequest, SearchRequestContext
from app.settings import settings


class SearchOrchestrator:
    def search(
        self,
        db,
        request: Request,
        *,
        q: str,
        source: str,
        video_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
        date_from: str | None = None,
        date_to: str | None = None,
        min_duration: int | None = None,
        max_duration: int | None = None,
        channel: str | None = None,
        language: str | None = None,
        has_speaker_labels: bool | None = None,
        category: str | None = None,
        sort_by: str = "relevance",
    ) -> SearchResponse:
        start_time = time.time()

        context = search_analytics.record_search_request(request, db, q, source)
        requires_relational_filters = any(
            [date_from, date_to, min_duration is not None, max_duration is not None, channel, category, language, has_speaker_labels is not None]
        ) or sort_by != "relevance"
        filters = search_analytics.build_search_filters(date_from, date_to, min_duration, max_duration, channel, language, has_speaker_labels, category)

        if settings.SEARCH_BACKEND == "opensearch" and not requires_relational_filters:
            effective_source = "native" if source == "best" else source
            index = settings.OPENSEARCH_INDEX_NATIVE if effective_source == "native" else settings.OPENSEARCH_INDEX_YOUTUBE
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
            bool_query = query["query"]["bool"]  # type: ignore[assignment]
            opensearch_filters = bool_query.setdefault("filter", [])
            if category:
                opensearch_filters.append({"term": {"category.keyword": category}})
            if channel:
                opensearch_filters.append({"match_phrase": {"channel_name": channel}})
            if language:
                opensearch_filters.append({"term": {"language.keyword": language}})
            if date_from or date_to:
                uploaded_range: Dict[str, Any] = {}
                if date_from:
                    uploaded_range["gte"] = date_from
                if date_to:
                    uploaded_range["lte"] = date_to
                opensearch_filters.append({"range": {"uploaded_at": uploaded_range}})
            if min_duration is not None or max_duration is not None:
                duration_range: Dict[str, Any] = {}
                if min_duration is not None:
                    duration_range["gte"] = min_duration
                if max_duration is not None:
                    duration_range["lte"] = max_duration
                opensearch_filters.append({"range": {"duration_seconds": duration_range}})
            if has_speaker_labels is not None:
                opensearch_filters.append({"term": {"has_speaker_labels": has_speaker_labels}})
            if sort_by == "date_desc":
                query["sort"] = [{"uploaded_at": {"order": "desc", "missing": "_last"}}, "_score"]
            elif sort_by == "date_asc":
                query["sort"] = [{"uploaded_at": {"order": "asc", "missing": "_last"}}, "_score"]
            elif sort_by == "duration_desc":
                query["sort"] = [{"duration_seconds": {"order": "desc", "missing": "_last"}}, "_score"]
            elif sort_by == "duration_asc":
                query["sort"] = [{"duration_seconds": {"order": "asc", "missing": "_last"}}, "_score"]
            try:
                r = requests.post(f"{settings.OPENSEARCH_URL}/{index}/_search", json=query, timeout=10)
                r.raise_for_status()
                data = r.json()
            except requests.exceptions.Timeout:
                raise ExternalServiceError("OpenSearch", "Request timeout")
            except requests.exceptions.HTTPError as e:
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
                        source="whisper" if effective_source == "native" else "youtube",
                    )
                )
            total = (
                data.get("hits", {}).get("total", {}).get("value")
                if isinstance(data.get("hits", {}).get("total"), dict)
                else None
            )
            query_time_ms = int((time.time() - start_time) * 1000)
            if context.user_id:
                search_analytics.save_search_history(
                    db,
                    context.user_id,
                    q,
                    {"source": source, "video_id": str(video_id) if video_id else None, **filters, "sort_by": sort_by},
                    total or len(hits),
                    query_time_ms,
                )
            return SearchResponse(total=total, hits=hits, query_time_ms=query_time_ms)

        if source == "best":
            rows = crud.search_best_segments_advanced(
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
                    id=r["id"],
                    video_id=r["video_id"],
                    start_ms=r["start_ms"],
                    end_ms=r["end_ms"],
                    snippet=r["snippet"] or "",
                    source=r["source"],
                    video_title=r.get("video_title"),
                    channel_name=r.get("channel_name"),
                    uploaded_at=r.get("uploaded_at"),
                    duration_seconds=r.get("duration_seconds"),
                )
                for r in rows
            ]
        elif source == "native":
            service = SearchService(backend=PostgresSearchBackend(db))
            native_results = service.search(
                SearchRequest(
                    q=q,
                    source=source,
                    video_id=str(video_id) if video_id else None,
                    limit=limit,
                    offset=offset,
                    sort_by=sort_by,
                    filters=filters,
                )
            )
            hits = [
                SearchHit(
                    id=r.id,
                    video_id=uuid.UUID(r.video_id),
                    start_ms=r.start_ms,
                    end_ms=r.end_ms,
                    snippet=r.snippet,
                    source="whisper",
                )
                for r in native_results
            ]
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
                    id=r["id"],
                    video_id=r["video_id"],
                    start_ms=r["start_ms"],
                    end_ms=r["end_ms"],
                    snippet=r["snippet"] or "",
                    source="youtube",
                    video_title=r.get("video_title"),
                    channel_name=r.get("channel_name"),
                    uploaded_at=r.get("uploaded_at"),
                    duration_seconds=r.get("duration_seconds"),
                )
                for r in rows
            ]

        query_time_ms = int((time.time() - start_time) * 1000)
        if context.user_id:
            search_analytics.save_search_history(
                db,
                context.user_id,
                q,
                {"source": source, "video_id": str(video_id) if video_id else None, **filters, "sort_by": sort_by},
                len(hits),
                query_time_ms,
            )
        return SearchResponse(hits=hits, query_time_ms=query_time_ms)

    def grouped_search(
        self,
        db,
        request: Request,
        *,
        q: str,
        source: str,
        video_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
        date_from: str | None = None,
        date_to: str | None = None,
        min_duration: int | None = None,
        max_duration: int | None = None,
        channel: str | None = None,
        language: str | None = None,
        has_speaker_labels: bool | None = None,
        category: str | None = None,
        sort_by: str = "relevance",
    ) -> GroupedSearchResponse:
        filters = search_analytics.build_search_filters(date_from, date_to, min_duration, max_duration, channel, language, has_speaker_labels, category)
        context = search_analytics.record_search_request(request, db, q, source)
        result = crud.get_grouped_search(
            db,
            q=q,
            source=source,
            video_id=str(video_id) if video_id else None,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            filters=filters,
        )
        if context.user_id:
            search_analytics.save_search_history(
                db,
                context.user_id,
                q,
                {"source": source, "video_id": str(video_id) if video_id else None, **filters, "sort_by": sort_by},
                result.total_moments,
                result.query_time_ms or 0,
            )
        return result

    def mention_map(
        self,
        db,
        request: Request,
        *,
        q: str,
        source: str,
        video_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
        date_from: str | None = None,
        date_to: str | None = None,
        min_duration: int | None = None,
        max_duration: int | None = None,
        channel: str | None = None,
        language: str | None = None,
        has_speaker_labels: bool | None = None,
        category: str | None = None,
        sort_by: str = "relevance",
        top_limit: int = 5,
    ) -> MentionMap:
        filters = search_analytics.build_search_filters(date_from, date_to, min_duration, max_duration, channel, language, has_speaker_labels, category)
        context = search_analytics.record_search_request(request, db, q, source)
        result = crud.get_mention_map(
            db,
            q=q,
            source=source,
            video_id=str(video_id) if video_id else None,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            filters=filters,
            top_limit=top_limit,
        )
        if context.user_id:
            search_analytics.save_search_history(
                db,
                context.user_id,
                q,
                {"source": source, "video_id": str(video_id) if video_id else None, **filters, "sort_by": sort_by},
                result.total_moments,
                result.query_time_ms or 0,
            )
        return result

    def prepare_export_rows(
        self,
        db,
        *,
        q: str,
        format: str,
        source: str,
        video_id: uuid.UUID | None = None,
        limit: int = 500,
        date_from: str | None = None,
        date_to: str | None = None,
        min_duration: int | None = None,
        max_duration: int | None = None,
        channel: str | None = None,
        language: str | None = None,
        has_speaker_labels: bool | None = None,
        sort_by: str = "relevance",
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        if not q or not q.strip():
            raise ValidationError("Search query cannot be empty", field="q")
        if source not in ("best", "native", "youtube"):
            raise ValidationError("Invalid source. Must be 'best', 'native', or 'youtube'", field="source")
        if format not in ("csv", "json"):
            raise ValidationError("Invalid format. Must be 'csv' or 'json'", field="format")

        filters = search_analytics.build_search_filters(date_from, date_to, min_duration, max_duration, channel, language, has_speaker_labels)
        if source == "best":
            rows = crud.search_best_segments_advanced(
                db,
                q=q,
                video_id=str(video_id) if video_id else None,
                limit=limit,
                offset=0,
                sort_by=sort_by,
                filters=filters,
            )
        elif source == "native":
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

        video_details: dict[str, dict[str, Any]] = {}
        for r in rows:
            vid = str(r["video_id"])
            if vid not in video_details:
                video_row = (
                    db.execute(_text("SELECT youtube_id, title, duration_seconds FROM videos WHERE id = :vid"), {"vid": vid})
                    .mappings()
                    .first()
                )
                if video_row:
                    video_details[vid] = video_row
        return rows, video_details
