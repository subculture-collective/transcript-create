import uuid
from unittest.mock import MagicMock

import requests
from fastapi import Request

from app.schemas import MentionMap
from app.search import analytics as search_analytics
from app.search.highlights import HIGHLIGHT_END, HIGHLIGHT_START
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
    request.state.analytics_subject_id = "a" * 64
    user_id = uuid.uuid4()

    monkeypatch.setattr(search_analytics, "_get_session_token", lambda _request: "session-token")
    monkeypatch.setattr(search_analytics, "_get_user_from_session", lambda _db, _token: {"id": user_id})
    monkeypatch.setattr(search_analytics, "_is_admin", lambda _user: False)
    monkeypatch.setattr(search_analytics, "update_search_suggestion", lambda _db, _term: None)

    context = search_analytics.record_search_request(request, db, q="test search", source="native")

    assert context == SearchRequestContext(user_id=str(user_id), is_admin=False)
    assert any("search_api" in str(statement) for statement, _params in db.calls)
    event_params = next(params for statement, params in db.calls if "search_api" in str(statement))
    assert event_params["analytics_subject_id"] == "a" * 64
    assert "session-token" not in event_params.values()
    assert any(call[0] == "commit" for call in db.calls)


def test_record_search_request_skips_event_for_anonymous_user(monkeypatch):
    db = FakeDB()
    request = MagicMock(spec=Request)

    monkeypatch.setattr(search_analytics, "_get_session_token", lambda _request: "session-token")
    monkeypatch.setattr(search_analytics, "_get_user_from_session", lambda _db, _token: None)
    monkeypatch.setattr(search_analytics, "_is_admin", lambda _user: False)
    monkeypatch.setattr(search_analytics, "update_search_suggestion", lambda _db, _term: None)

    context = search_analytics.record_search_request(request, db, q="test search", source="native")

    assert context == SearchRequestContext(user_id=None, is_admin=False)
    assert all("search_api" not in str(statement) for statement, _params in db.calls)


def test_search_orchestrator_anonymous_search_skips_history(monkeypatch):
    class FakeBackend:
        def search(self, request):
            return [
                SearchResult(
                    id=1,
                    video_id="11111111-1111-1111-1111-111111111111",
                    start_ms=0,
                    end_ms=1000,
                    snippet="hello",
                    rank=0.9,
                )
            ]

    db = FakeDB()
    request = MagicMock(spec=Request)
    save_history = MagicMock()

    monkeypatch.setattr(
        search_analytics,
        "record_search_request",
        lambda *_args, **_kwargs: SearchRequestContext(user_id=None, is_admin=False),
    )
    monkeypatch.setattr(search_analytics, "save_search_history", save_history)
    monkeypatch.setattr("app.search.orchestrator.PostgresSearchBackend", lambda _db: FakeBackend())
    freshness = MagicMock(side_effect=RuntimeError("external index backlog is unavailable"))
    monkeypatch.setattr("app.search.orchestrator.search_freshness", freshness)

    result = SearchOrchestrator().search(db, request, q="hello", source="native")

    assert result.hits[0].snippet == "hello"
    assert result.hits[0].highlights == []
    assert result.hits[0].source == "whisper"
    assert result.indexed_at is None
    assert result.index_lag_seconds == 0
    freshness.assert_not_called()
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

    monkeypatch.setattr(
        search_analytics,
        "record_search_request",
        lambda *_args, **_kwargs: SearchRequestContext(user_id="user-1", is_admin=False),
    )
    monkeypatch.setattr(search_analytics, "save_search_history", history)
    monkeypatch.setattr("app.search.orchestrator.crud.get_mention_map", lambda *_args, **_kwargs: mention_map)

    result = SearchOrchestrator().mention_map(db, request, q="hello", source="best")

    assert result.total_moments == 2
    history.assert_called_once()


def test_opensearch_uses_private_sentinels_and_returns_plain_ranges(monkeypatch):
    video_id = "11111111-1111-1111-1111-111111111111"
    response = MagicMock()
    response.json.return_value = {
        "hits": {
            "total": {"value": 2},
            "hits": [
                {
                    "_source": {"id": 1, "video_id": video_id, "start_ms": 0, "end_ms": 10, "text": "🚀 rent"},
                    "highlight": {"text": [f"🚀 {HIGHLIGHT_START}rent{HIGHLIGHT_END}"]},
                },
                {
                    "_source": {
                        "id": 2,
                        "video_id": video_id,
                        "start_ms": 10,
                        "end_ms": 20,
                        "text": "literal <script>alert(1)</script>",
                    }
                },
            ],
        }
    }
    post = MagicMock(return_value=response)
    monkeypatch.setattr("app.search.orchestrator.settings.SEARCH_BACKEND", "opensearch")
    monkeypatch.setattr("app.search.orchestrator.settings.OPENSEARCH_USER", "")
    monkeypatch.setattr("app.search.orchestrator.settings.OPENSEARCH_PASSWORD", "")
    monkeypatch.setattr("app.search.orchestrator.settings.OPENSEARCH_VERIFY_SSL", True)
    monkeypatch.setattr("app.search.orchestrator.requests.post", post)
    monkeypatch.setattr(
        search_analytics,
        "record_search_request",
        lambda *_args, **_kwargs: SearchRequestContext(user_id=None, is_admin=False),
    )

    result = SearchOrchestrator().search(FakeDB(), MagicMock(spec=Request), q="rent", source="native")

    query = post.call_args.kwargs["json"]
    assert query["highlight"]["pre_tags"] == [HIGHLIGHT_START]
    assert query["highlight"]["post_tags"] == [HIGHLIGHT_END]
    assert "auth" not in post.call_args.kwargs
    assert post.call_args.kwargs["verify"] is True
    assert result.hits[0].snippet == "🚀 rent"
    assert [item.model_dump() for item in result.hits[0].highlights] == [{"start": 2, "end": 6}]
    assert result.hits[1].snippet == "literal <script>alert(1)</script>"
    assert result.hits[1].highlights == []


def test_opensearch_search_uses_configured_auth_and_ssl(monkeypatch):
    response = MagicMock()
    response.json.return_value = {"hits": {"total": {"value": 0}, "hits": []}}
    post = MagicMock(return_value=response)
    monkeypatch.setattr("app.search.orchestrator.settings.SEARCH_BACKEND", "opensearch")
    monkeypatch.setattr("app.search.orchestrator.settings.OPENSEARCH_URL", "https://search.example.test/base/")
    monkeypatch.setattr("app.search.orchestrator.settings.OPENSEARCH_USER", "search-user")
    monkeypatch.setattr("app.search.orchestrator.settings.OPENSEARCH_PASSWORD", "search-password")
    monkeypatch.setattr("app.search.orchestrator.settings.OPENSEARCH_VERIFY_SSL", False)
    monkeypatch.setattr("app.search.orchestrator.requests.post", post)
    monkeypatch.setattr(
        search_analytics,
        "record_search_request",
        lambda *_args, **_kwargs: SearchRequestContext(user_id=None, is_admin=False),
    )

    SearchOrchestrator().search(FakeDB(), MagicMock(spec=Request), q="rent", source="native")

    assert post.call_args.args == ("https://search.example.test/base/segments/_search",)
    assert post.call_args.kwargs["auth"] == ("search-user", "search-password")
    assert post.call_args.kwargs["verify"] is False


def test_opensearch_fallback_converts_postgres_mapping_highlights(monkeypatch):
    class FakeBackend:
        def search(self, request):
            return [
                SearchResult(
                    id=1,
                    video_id="11111111-1111-1111-1111-111111111111",
                    start_ms=0,
                    end_ms=10,
                    snippet="hello world",
                    rank=0.9,
                    highlights=({"start": 0, "end": 5},),
                )
            ]

    monkeypatch.setattr("app.search.orchestrator.settings.SEARCH_BACKEND", "opensearch")
    monkeypatch.setattr(
        "app.search.orchestrator.requests.post", MagicMock(side_effect=requests.exceptions.ConnectionError)
    )
    monkeypatch.setattr("app.search.orchestrator.PostgresSearchBackend", lambda _db: FakeBackend())
    monkeypatch.setattr(
        search_analytics,
        "record_search_request",
        lambda *_args, **_kwargs: SearchRequestContext(user_id=None, is_admin=False),
    )
    monkeypatch.setattr(
        "app.search.orchestrator.search_freshness",
        lambda _db: {"indexed_at": None, "index_lag_seconds": 0},
    )

    result = SearchOrchestrator().search(FakeDB(), MagicMock(spec=Request), q="hello", source="native")

    assert result.backend == "postgres"
    assert result.degraded is True
    assert [item.model_dump() for item in result.hits[0].highlights] == [{"start": 0, "end": 5}]


def test_export_rows_normalize_engine_markers(monkeypatch):
    row = {
        "id": 1,
        "video_id": "11111111-1111-1111-1111-111111111111",
        "start_ms": 0,
        "end_ms": 10,
        "snippet": f"literal <img onerror=x> {HIGHLIGHT_START}rent{HIGHLIGHT_END}",
    }
    monkeypatch.setattr("app.search.orchestrator.crud.search_segments_advanced", lambda *_args, **_kwargs: [row])
    db = MagicMock()
    db.execute.return_value.mappings.return_value.first.return_value = None

    rows, _video_details = SearchOrchestrator().prepare_export_rows(db, q="rent", format="json", source="native")

    assert rows[0]["snippet"] == "literal <img onerror=x> rent"
    assert rows[0]["highlights"] == [{"start": 24, "end": 28}]
