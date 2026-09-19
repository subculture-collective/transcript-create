import uuid
from hashlib import sha256

import pytest
from sqlalchemy import text

from app.main import app
from app.security import require_auth
from app.settings import settings


@pytest.fixture
def community(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "COMMUNITY_ENABLED", True)
    users = [{"id": uuid.uuid4(), "role": role, "name": role} for role in ("admin", "user", "moderator", "user")]
    for user in users:
        db_session.execute(text("INSERT INTO users(id,role,name) VALUES (:id,:role,:name)"), user)
    job, video = uuid.uuid4(), uuid.uuid4()
    db_session.execute(
        text("INSERT INTO jobs(id,kind,input_url) VALUES (:id,'single','https://example.invalid')"), {"id": job}
    )
    db_session.execute(
        text("INSERT INTO videos(id,job_id,youtube_id,title,duration_seconds) VALUES (:id,:job,:youtube,'Example',60)"),
        {"id": video, "job": job, "youtube": str(video)},
    )
    current = {"user": users[0]}
    app.dependency_overrides[require_auth] = lambda: current["user"]
    yield client, db_session, users, current, video
    app.dependency_overrides.pop(require_auth, None)


def test_draft_publish_public_pagination_and_export(community):
    client, db, users, current, video = community
    response = client.post("/community/posts", json={"kind": "update", "body": "  Creator news  "})
    assert response.status_code == 201, response.text
    post = response.json()
    assert post["status"] == "draft"
    assert post["body"] == "Creator news"
    assert client.get("/community/posts").json()["items"] == []
    assert client.get("/community/export").json()["items"][0]["id"] == post["id"]
    current["user"] = users[1]
    assert client.get("/community/export").json()["items"] == []
    assert client.post(f"/community/posts/{post['id']}/publish").status_code == 403
    assert (
        client.post("/community/posts", json={"kind": "update", "body": "Impersonation", "publish": True}).status_code
        == 403
    )
    current["user"] = users[0]
    assert client.post(f"/community/posts/{post['id']}/publish").status_code == 200
    client.post("/community/posts", json={"kind": "update", "body": "Second", "publish": True})
    page = client.get("/community/posts?limit=1").json()
    assert len(page["items"]) == 1 and page["next_offset"] == 1
    assert client.get("/community/posts?offset=1").json()["items"][0]["id"] != page["items"][0]["id"]
    assert db.execute(text("SELECT count(*) FROM audit_logs WHERE action='community.publish'")).scalar() >= 1


def test_discussions_moderation_reporting_and_hidden_parent(community):
    client, db, users, current, video = community
    current["user"] = users[1]
    root = client.post(
        "/community/posts",
        json={
            "kind": "discussion",
            "body": "In context",
            "video_id": str(video),
            "start_ms": 1000,
            "end_ms": 5000,
            "publish": True,
        },
    ).json()
    reply = client.post(
        "/community/posts", json={"kind": "reply", "body": "A reply", "parent_id": root["id"], "publish": True}
    ).json()
    assert len(client.get(f"/community/posts?parent_id={root['id']}").json()["items"]) == 1
    assert (
        client.post(f"/community/posts/{root['id']}/moderate", json={"action": "hide", "reason": "test"}).status_code
        == 403
    )
    current["user"] = users[3]
    assert client.delete(f"/community/posts/{root['id']}").status_code == 404
    assert client.post(f"/community/posts/{root['id']}/report", json={"reason": "Review context"}).status_code == 204
    assert client.get("/community/reports").status_code == 403
    assert client.get("/community/hidden").status_code == 403
    current["user"] = users[2]
    report = client.get("/community/reports").json()["items"][0]
    assert "reporter_id" not in report
    assert (
        client.post(f"/community/posts/{root['id']}/moderate", json={"action": "hide", "reason": "Review"}).status_code
        == 200
    )
    assert client.get("/community/posts").json()["items"] == []
    assert client.get("/community/hidden").json()["items"][0]["id"] == root["id"]
    assert client.get(f"/community/posts?parent_id={root['id']}").status_code == 404
    assert (
        client.post(
            "/community/posts", json={"kind": "reply", "body": "Hidden reply", "parent_id": root["id"], "publish": True}
        ).status_code
        == 404
    )
    assert client.post(f"/community/posts/{reply['id']}/report", json={"reason": "Hidden"}).status_code == 404
    current["user"] = users[1]
    assert client.post(f"/community/posts/{root['id']}/publish").status_code == 409
    current["user"] = users[2]
    assert (
        client.post(
            f"/community/posts/{root['id']}/moderate", json={"action": "restore", "reason": "Reviewed"}
        ).status_code
        == 200
    )
    assert client.post(f"/community/reports/{report['id']}/resolve", json={"reason": "Resolved"}).status_code == 204
    assert client.get("/community/reports").json()["items"] == []
    current["user"] = users[1]
    assert client.delete(f"/community/posts/{root['id']}").status_code == 204
    assert client.get("/community/mine").json()["items"] == []


def test_pin_draft_and_source_validation(community):
    client, db, users, current, video = community
    draft = client.post("/community/posts", json={"kind": "update", "body": "Private"}).json()
    assert (
        client.post(
            f"/community/posts/{draft['id']}/moderate", json={"action": "restore", "reason": "Cannot publish"}
        ).status_code
        == 409
    )
    for payload in (
        {"kind": "discussion", "body": "No source"},
        {"kind": "reply", "body": "No parent"},
        {"kind": "update", "body": "   "},
        {"kind": "discussion", "body": "Invalid range", "video_id": str(video), "start_ms": 5, "end_ms": 4},
    ):
        assert client.post("/community/posts", json=payload).status_code == 422
    assert (
        client.post(
            "/community/posts",
            json={"kind": "discussion", "body": "Too long", "video_id": str(video), "start_ms": 0, "end_ms": 61000},
        ).status_code
        == 422
    )
    assert client.post(f"/community/posts/{draft['id']}/publish").status_code == 200
    assert (
        client.post(f"/community/posts/{draft['id']}/moderate", json={"action": "pin", "reason": "Welcome"}).json()[
            "pinned"
        ]
        is True
    )


def test_submission_rate_limit(community):
    client, db, users, current, video = community
    for _ in range(10):
        assert client.post("/community/posts", json={"kind": "update", "body": "Draft"}).status_code == 201
    assert client.post("/community/posts", json={"kind": "update", "body": "Overflow"}).status_code == 429


def test_disabled_authentication_and_session_csrf(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "COMMUNITY_ENABLED", False)
    assert client.get("/community/posts").status_code == 404
    monkeypatch.setattr(settings, "COMMUNITY_ENABLED", True)
    assert client.post("/community/posts", json={"kind": "update", "body": "Anonymous"}).status_code == 401
    user_id = uuid.uuid4()
    token = str(uuid.uuid4())
    db_session.execute(text("INSERT INTO users(id,role) VALUES (:id,'admin')"), {"id": user_id})
    db_session.execute(
        text("INSERT INTO sessions(token_hash,user_id) VALUES (:token,:id)"),
        {"id": user_id, "token": sha256(token.encode()).hexdigest()},
    )
    client.cookies.set("tc_session", token)
    assert client.post("/community/posts", json={"kind": "update", "body": "No CSRF"}).status_code == 403
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/community/posts", json={"kind": "update", "body": "With CSRF"}, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 201, response.text


def test_author_edits_require_current_version_and_cannot_bypass_moderation(community):
    client, db, users, current, video = community
    post = client.post("/community/posts", json={"kind": "update", "body": "Original draft"}).json()
    edit = {"body": "Edited draft", "if_match": post["updated_at"]}
    current["user"] = users[1]
    assert client.patch(f"/community/posts/{post['id']}", json=edit).status_code == 403
    current["user"] = users[0]
    changed = client.patch(f"/community/posts/{post['id']}", json=edit)
    assert changed.status_code == 200, changed.text
    assert changed.json()["status"] == "draft"
    assert changed.json()["body"] == "Edited draft"
    assert client.patch(f"/community/posts/{post['id']}", json=edit).status_code == 409
    client.post(f"/community/posts/{post['id']}/publish")
    client.post(f"/community/posts/{post['id']}/moderate", json={"action": "hide", "reason": "Review"})
    assert (
        client.patch(
            f"/community/posts/{post['id']}", json={"body": "Bypass", "if_match": changed.json()["updated_at"]}
        ).status_code
        == 409
    )
    assert client.get("/community/posts").json()["items"] == []


def test_combined_timeline_includes_ready_recordings_and_public_roots_only(community):
    client, db, users, current, video = community
    db.execute(
        text("UPDATE videos SET state='completed',created_at=now()-interval '1 day' WHERE id=:id"), {"id": video}
    )
    db.execute(
        text("INSERT INTO segments(video_id,start_ms,end_ms,text) VALUES (:id,0,1000,'Source context')"), {"id": video}
    )
    root = client.post("/community/posts", json={"kind": "update", "body": "Public update", "publish": True}).json()
    client.post("/community/posts", json={"kind": "update", "body": "Private draft"})
    client.post(
        "/community/posts",
        json={"kind": "reply", "body": "Reply only in thread", "parent_id": root["id"], "publish": True},
    )
    response = client.get("/community/timeline?limit=1")
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["next_offset"] == 1
    assert page["items"][0]["kind"] == "post"
    assert page["items"][0]["post"]["body"] == "Public update"
    archive = client.get("/community/timeline?offset=1").json()
    assert len(archive["items"]) == 1
    assert archive["items"][0]["kind"] == "archive"
    assert set(archive["items"][0]["video"]) == {"id", "title"}
    client.post(f"/community/posts/{root['id']}/moderate", json={"action": "hide", "reason": "Review"})
    assert [item["kind"] for item in client.get("/community/timeline").json()["items"]] == ["archive"]
    db.execute(text("DELETE FROM videos WHERE id=:id"), {"id": video})
    assert client.get("/community/timeline").json()["items"] == []
