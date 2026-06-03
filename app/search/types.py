from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SearchRequest:
    q: str
    source: str
    limit: int
    offset: int
    video_id: str | None = None
    sort_by: str = "relevance"
    filters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchResult:
    id: int
    video_id: str
    start_ms: int
    end_ms: int
    snippet: str
    rank: float | None = None


@dataclass(frozen=True)
class SearchRequestContext:
    user_id: str | None
    session_token: str | None
    is_admin: bool
