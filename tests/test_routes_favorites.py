"""Behavior tests for authenticated favorite persistence."""

import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import Request

from app.exceptions import AuthenticationError, NotFoundError, ValidationError
from app.routes import favorites


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def _authenticated(monkeypatch, user_id: uuid.UUID):
    monkeypatch.setattr(favorites, "_get_session_token", lambda _request: "session-token")
    monkeypatch.setattr(favorites, "_get_user_from_session", lambda _db, _token: {"id": user_id})


def test_list_favorites_requires_authentication(monkeypatch):
    monkeypatch.setattr(favorites, "_get_session_token", lambda _request: None)
    monkeypatch.setattr(favorites, "_get_user_from_session", lambda _db, _token: None)

    with pytest.raises(AuthenticationError):
        favorites.list_favorites(_request(), Mock())


def test_list_favorites_scopes_query_to_user_and_video(monkeypatch):
    user_id = uuid.uuid4()
    video_id = uuid.uuid4()
    rows = [{"id": uuid.uuid4(), "video_id": video_id, "start_ms": 10, "end_ms": 20}]
    result = Mock()
    result.mappings.return_value.all.return_value = rows
    db = Mock()
    db.execute.return_value = result
    _authenticated(monkeypatch, user_id)

    assert favorites.list_favorites(_request(), db, video_id=video_id) == {"items": rows}
    statement, params = db.execute.call_args.args
    assert "user_id=:u AND video_id=:v" in str(statement)
    assert params == {"u": str(user_id), "v": str(video_id)}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"video_id": "not-a-uuid", "start_ms": 0, "end_ms": 1},
        {"video_id": str(uuid.uuid4()), "start_ms": True, "end_ms": 1},
        {"video_id": str(uuid.uuid4()), "start_ms": -1, "end_ms": 1},
        {"video_id": str(uuid.uuid4()), "start_ms": 10, "end_ms": 10},
        {"video_id": str(uuid.uuid4()), "start_ms": 0, "end_ms": 1, "text": 3},
    ],
)
def test_add_favorite_rejects_invalid_ranges_and_payloads(monkeypatch, payload):
    _authenticated(monkeypatch, uuid.uuid4())

    with pytest.raises(ValidationError):
        favorites.add_favorite(payload, _request(), Mock())


def test_add_favorite_persists_valid_segment(monkeypatch):
    user_id = uuid.uuid4()
    video_id = uuid.uuid4()
    db = Mock()
    _authenticated(monkeypatch, user_id)

    response = favorites.add_favorite(
        {"video_id": str(video_id), "start_ms": 100, "end_ms": 250, "text": "A useful passage"},
        _request(),
        db,
    )

    assert isinstance(response["id"], uuid.UUID)
    _, params = db.execute.call_args.args
    assert params == {
        "i": str(response["id"]),
        "u": str(user_id),
        "v": str(video_id),
        "s": 100,
        "e": 250,
        "t": "A useful passage",
    }
    db.commit.assert_called_once_with()


def test_delete_favorite_reports_missing_or_wrong_owner(monkeypatch):
    _authenticated(monkeypatch, uuid.uuid4())
    db = Mock()
    db.execute.return_value = SimpleNamespace(rowcount=0)

    with pytest.raises(NotFoundError):
        favorites.delete_favorite(uuid.uuid4(), _request(), db)

    db.commit.assert_not_called()


def test_delete_favorite_commits_owned_row(monkeypatch):
    user_id = uuid.uuid4()
    favorite_id = uuid.uuid4()
    _authenticated(monkeypatch, user_id)
    db = Mock()
    db.execute.return_value = SimpleNamespace(rowcount=1)

    assert favorites.delete_favorite(favorite_id, _request(), db) == {"ok": True}
    _, params = db.execute.call_args.args
    assert params == {"i": str(favorite_id), "u": str(user_id)}
    db.commit.assert_called_once_with()
