import uuid
from unittest.mock import MagicMock

from fastapi import Request

from app.schemas import MentionMap
from app.search import analytics as search_analytics
from app.search.orchestrator import SearchOrchestrator
from app.search.types import SearchRequestContext, SearchResult


class FakeDB:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((statement, params))
        return MagicMock()

    def commit(self):
        self.calls.append(("commit", None))

    def rollback(self):
        self.calls.append(("rollback", None))


def test_record_search_request_logs_event_for_authenticated_user(monkeypatch):
    db = FakeDB()
    request = MagicMock(spec=Request)
    user_id = uuid.uuid4()

    monkeypatch.setattr(search_analytics, "_get_session_token", lambda _request: "session-token")
    monkeypatch.setattr(search_analytics, "_get_user_from_session", lambda _db, _token: {"id": user_id})
    monkeypatch.setattr(search_analytics, "_is_admin", lambda _user: False)
    monkeypatch.setattr(search_analytics, "update_search_suggestion", lambda _db, _term: None)

    context = search_analytics.record_search_request(request, db, q="test search", source="native")

    assert context == SearchRequestContext(user_id=str(user_id), session_token="session-token", is_admin=False)
    assert any("search_api" in str(statement) for statement, _params in db.calls)
    assert any(call[0] == "commit" for call in db.calls)


def test_record_search_request_skips_event_for_anonymous_user(monkeypatch):
    db = FakeDB()
    request = MagicMock(spec=Request)

    monkeypatch.setattr(search_analytics, "_get_session_token", lambda _request: "session-token")
    monkeypatch.setattr(search_analytics, "_get_user_from_session", lambda _db, _token: None)
    monkeypatch.setattr(search_analytics, "_is_admin", lambda _user: False)
    monkeypatch.setattr(search_analytics, "update_search_suggestion", lambda _db, _term: None)

    context = search_analytics.record_search_request(request, db, q="test search", source="native")

    assert context == SearchRequestContext(user_id=None, session_token="session-token", is_admin=False)
    assert all("search_api" not in str(statement) for statement, _params in db.calls)


def test_search_orchestrator_anonymous_search_skips_history(monkeypatch):
    class FakeBackend:
        def search(self, request):
            return [SearchResult(id=1, video_id="11111111-1111-1111-1111-111111111111", start_ms=0, end_ms=1000, snippet="hello", rank=0.9)]

    db = FakeDB()
    request = MagicMock(spec=Request)
    save_history = MagicMock()

    monkeypatch.setattr(search_analytics, "record_search_request", lambda *_args, **_kwargs: SearchRequestContext(user_id=None, session_token=None, is_admin=False))
    monkeypatch.setattr(search_analytics, "save_search_history", save_history)
    monkeypatch.setattr("app.search.orchestrator.PostgresSearchBackend", lambda _db: FakeBackend())

    result = SearchOrchestrator().search(db, request, q="hello", source="native")

    assert result.hits[0].snippet == "hello"
    assert result.hits[0].source == "whisper"
    save_history.assert_not_called()


def test_search_orchestrator_mention_map_saves_history(monkeypatch):
    db = FakeDB()
    request = MagicMock(spec=Request)
    history = MagicMock()
    mention_map = MentionMap(
        query="hello",
        total_moments=2,
        total_videos=1,
        related_topics=[],
        top_episodes_count=0,
        top_episodes=[],
    )

    monkeypatch.setattr(search_analytics, "record_search_request", lambda *_args, **_kwargs: SearchRequestContext(user_id="user-1", session_token="token", is_admin=False))
    monkeypatch.setattr(search_analytics, "save_search_history", history)
    monkeypatch.setattr("app.search.orchestrator.crud.get_mention_map", lambda *_args, **_kwargs: mention_map)

    result = SearchOrchestrator().mention_map(db, request, q="hello", source="best")

    assert result.total_moments == 2
    history.assert_called_once()
