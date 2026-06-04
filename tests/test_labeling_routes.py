from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.routes import archive as archive_routes
from app.schemas import ArchiveLabelReviewAction


class FakeResult:
    def __init__(self, rows=None):
        self._rows = list(rows or [])

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class FakeDb:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []
        self.commit_count = 0

    def execute(self, sql, params=None):
        self.calls.append((str(sql), params))
        if not self.results:
            raise AssertionError(f"Unexpected query: {sql}")
        return self.results.pop(0)

    def commit(self):
        self.commit_count += 1


def _create_user_session(db_session, *, email: str = "user@example.com") -> str:
    user_id = uuid.uuid4()
    session_token = secrets.token_urlsafe(32)
    db_session.execute(
        text("INSERT INTO users (id, email, oauth_provider, oauth_subject, plan) VALUES (:id, :email, 'google', :subject, 'free')"),
        {"id": str(user_id), "email": email, "subject": f"{email}-subject"},
    )
    db_session.execute(
        text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
        {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
    )
    db_session.commit()
    return session_token


def _label_row(label_id: uuid.UUID, *, label: str = "Old Label", slug: str = "old-label", status: str = "candidate"):
    return {
        "id": label_id,
        "slug": slug,
        "label": label,
        "kind": "topic",
        "status": status,
        "source": "automatic",
        "publish_tier": "shadow",
        "confidence_score": 0.91,
        "description": None,
        "canonical_id": None,
    }


def _assignment_row(assignment_id: uuid.UUID, label_id: uuid.UUID, *, assignment_status: str = "candidate", label_status: str = "candidate"):
    return {
        "id": assignment_id,
        "video_id": uuid.uuid4(),
        "unit_type": "window",
        "start_ms": 100,
        "end_ms": 200,
        "status": assignment_status,
        "publish_tier": "shadow",
        "confidence_score": 0.88,
        "evidence_count": 1,
        "evidence": [{"kind": "alias", "text": "old label"}],
        "label_id": label_id,
        "label_slug": "old-label",
        "label_label": "Old Label",
        "label_kind": "topic",
        "label_status": label_status,
        "label_source": "automatic",
        "label_publish_tier": "shadow",
        "label_confidence_score": 0.91,
        "label_description": None,
    }


def test_labeling_admin_routes_registered(client: TestClient):
    spec = client.get("/openapi.json").json()
    expected_paths = {
        "/admin/archive/labels": {"get"},
        "/admin/archive/labels/{label_id}/assignments": {"get"},
        "/admin/archive/labels/{label_id}/review": {"post"},
        "/admin/archive/label-assignments/{assignment_id}/review": {"post"},
        "/admin/archive/labels/extract-video/{video_id}": {"post"},
    }

    for path, methods in expected_paths.items():
        assert path in spec["paths"]
        assert methods.issubset(set(spec["paths"][path].keys()))


def test_labeling_admin_routes_require_auth(client: TestClient):
    label_id = uuid.uuid4()
    assignment_id = uuid.uuid4()
    video_id = uuid.uuid4()

    assert client.get("/admin/archive/labels").status_code == 401
    assert client.get(f"/admin/archive/labels/{label_id}/assignments").status_code == 401
    assert client.post(f"/admin/archive/labels/{label_id}/review", json={"action": "approve"}).status_code == 401
    assert client.post(f"/admin/archive/label-assignments/{assignment_id}/review", json={"action": "approve"}).status_code == 401
    assert client.post(f"/admin/archive/labels/extract-video/{video_id}").status_code == 401


def test_labeling_admin_routes_require_admin(client: TestClient, db_session):
    session_token = _create_user_session(db_session, email="not-admin@example.com")
    cookies = {"tc_session": session_token}
    label_id = uuid.uuid4()
    assignment_id = uuid.uuid4()
    video_id = uuid.uuid4()

    assert client.get("/admin/archive/labels", cookies=cookies).status_code == 403
    assert client.get(f"/admin/archive/labels/{label_id}/assignments", cookies=cookies).status_code == 403
    assert client.post(f"/admin/archive/labels/{label_id}/review", json={"action": "approve"}, cookies=cookies).status_code == 403
    assert client.post(f"/admin/archive/label-assignments/{assignment_id}/review", json={"action": "approve"}, cookies=cookies).status_code == 403
    assert client.post(f"/admin/archive/labels/extract-video/{video_id}", cookies=cookies).status_code == 403


def test_review_label_action_updates_status_and_feedback():
    label_id = uuid.uuid4()
    before = _label_row(label_id)
    after = _label_row(label_id, status="published")
    db = FakeDb([FakeResult([before]), FakeResult(), FakeResult(), FakeResult([after])])
    payload = ArchiveLabelReviewAction(action="approve", reason="looks good")

    result = archive_routes._review_label_action(db, label_id, payload, {"id": uuid.uuid4()})

    assert result.status == "published"
    assert db.commit_count == 0
    assert "UPDATE archive_labels SET status = :status" in db.calls[1][0]
    assert "INSERT INTO archive_label_feedback" in db.calls[2][0]
    assert db.calls[2][1]["action"] == "approve"


def test_review_assignment_approve_updates_assignment_label_and_feedback():
    label_id = uuid.uuid4()
    assignment_id = uuid.uuid4()
    before = _assignment_row(assignment_id, label_id)
    after = _assignment_row(assignment_id, label_id, assignment_status="admin_approved", label_status="published")
    db = FakeDb([FakeResult([before]), FakeResult(), FakeResult(), FakeResult(), FakeResult([after])])
    payload = ArchiveLabelReviewAction(action="approve")

    result = archive_routes._review_assignment_action(db, assignment_id, payload, {"id": uuid.uuid4()})

    assert result.status == "admin_approved"
    assert result.label.status == "published"
    assert "UPDATE archive_label_assignments SET status = 'admin_approved'" in db.calls[1][0]
    assert "UPDATE archive_labels SET status = 'published'" in db.calls[2][0]
    assert "INSERT INTO archive_label_feedback" in db.calls[3][0]


def test_extract_video_route_calls_pipeline_and_commits(monkeypatch):
    db = FakeDb([])
    captured = {}

    def fake_extract(db_arg, video_id, extraction_tier="cheap"):
        captured["db"] = db_arg
        captured["video_id"] = video_id
        captured["extraction_tier"] = extraction_tier
        return {"video_id": video_id, "extraction_tier": extraction_tier, "run_id": "run-1", "windows": 2, "candidates": 1, "assignments": 3}

    monkeypatch.setattr(archive_routes, "extract_labels_for_video", fake_extract)

    video_id = uuid.uuid4()
    result = archive_routes.admin_extract_labels_for_video(video_id=video_id, extraction_tier="balanced", db=db, user={"id": uuid.uuid4()})

    assert captured == {"db": db, "video_id": str(video_id), "extraction_tier": "balanced"}
    assert result.run_id == "run-1"
    assert result.windows == 2
    assert db.commit_count == 1
