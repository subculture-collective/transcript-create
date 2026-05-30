from app.search.repositories import PostgresSearchBackend
from app.search.service import SearchService
from app.search.types import SearchRequest, SearchResult


class FakeSearchBackend:
    def __init__(self):
        self.requests = []

    def search(self, request: SearchRequest):
        self.requests.append(request)
        return [SearchResult(id=1, video_id="v1", start_ms=1000, end_ms=2000, snippet="hello", rank=0.9)]


def test_search_service_delegates_to_backend():
    backend = FakeSearchBackend()
    service = SearchService(backend=backend)
    results = service.search(SearchRequest(q="hello", source="native", limit=10, offset=0))
    assert results[0].video_id == "v1"
    assert backend.requests[0].q == "hello"


def test_search_service_blank_query_returns_empty():
    backend = FakeSearchBackend()
    service = SearchService(backend=backend)
    assert service.search(SearchRequest(q="   ", source="native", limit=10, offset=0)) == []
    assert backend.requests == []


def test_postgres_backend_maps_rows(monkeypatch):
    captured = {}

    def fake_search_segments_advanced(db, **kwargs):
        captured["db"] = db
        captured["kwargs"] = kwargs
        return [
            {"id": 7, "video_id": "v2", "start_ms": 10, "end_ms": 20, "snippet": "snip", "rank": 1.5}
        ]

    monkeypatch.setattr("app.search.repositories.crud.search_segments_advanced", fake_search_segments_advanced)
    backend = PostgresSearchBackend(db=object())
    results = backend.search(
        SearchRequest(
            q="hello",
            source="native",
            limit=5,
            offset=2,
            video_id="vid",
            sort_by="date_desc",
            filters={"channel": "x"},
        )
    )
    assert captured["db"] is backend.db
    assert captured["kwargs"]["q"] == "hello"
    assert captured["kwargs"]["video_id"] == "vid"
    assert captured["kwargs"]["limit"] == 5
    assert captured["kwargs"]["offset"] == 2
    assert captured["kwargs"]["sort_by"] == "date_desc"
    assert captured["kwargs"]["filters"] == {"channel": "x"}
    assert results[0].id == 7
    assert results[0].video_id == "v2"
    assert results[0].snippet == "snip"
    assert results[0].rank == 1.5
