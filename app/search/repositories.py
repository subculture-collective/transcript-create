from app import crud
from app.search.types import SearchRequest, SearchResult


class PostgresSearchBackend:
    def __init__(self, db):
        self.db = db

    def search(self, request: SearchRequest) -> list[SearchResult]:
        rows = crud.search_segments_advanced(
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
