from typing import Any

from app.search.segment_repository import SearchRepository
from app.search.types import SearchRequest, SearchResult


class PostgresSearchBackend:
    def __init__(self, db, repository: Any | None = None):
        self.db = db
        self.repository = repository or SearchRepository()

    def search(self, request: SearchRequest) -> list[SearchResult]:
        rows = self.repository.search_native(
            self.db,
            q=request.q,
            video_id=request.video_id,
            limit=request.limit,
            offset=request.offset,
            sort_by=request.sort_by,
            filters=request.filters,
        )
        return [
            SearchResult(
                id=int(row["id"]),
                video_id=str(row["video_id"]),
                start_ms=int(row["start_ms"]),
                end_ms=int(row["end_ms"]),
                snippet=str(row["snippet"] or ""),
                rank=float(row["rank"]) if row.get("rank") is not None else None,
            )
            for row in rows
        ]
