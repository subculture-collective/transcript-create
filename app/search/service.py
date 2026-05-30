from typing import Protocol

from app.search.types import SearchRequest, SearchResult


class SearchBackend(Protocol):
    def search(self, request: SearchRequest) -> list[SearchResult]:
        ...


class SearchService:
    def __init__(self, *, backend: SearchBackend):
        self.backend = backend

    def search(self, request: SearchRequest) -> list[SearchResult]:
        if not request.q.strip():
            return []
        return self.backend.search(request)
