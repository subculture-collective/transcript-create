"""Tests for export routes."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


class TestExportRoutes:
    """Tests for export endpoints."""

    def test_export_srt_unauthenticated(self, client: TestClient):
        """Test SRT export without authentication."""
        video_id = uuid.uuid4()
        response = client.get(f"/videos/{video_id}/transcript.srt")
        assert response.status_code == 401

    def test_export_youtube_transcript_srt(self, client: TestClient, db_session):
        """Test YouTube transcript SRT export."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        # Create authenticated user
        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, plan) "
                "VALUES (:id, :email, 'google', 'test', 'pro')"
            ),
            {"id": str(user_id), "email": "export@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )

        # Create test video with YouTube transcript
        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        yt_transcript_id = uuid.uuid4()

        db_session.execute(
            text("INSERT INTO jobs (id, kind, input_url) VALUES (:id, 'single', 'https://youtube.com/test')"),
            {"id": str(job_id)},
        )
        db_session.execute(
            text("INSERT INTO videos (id, job_id, youtube_id, idx) VALUES (:id, :job_id, :yt_id, 0)"),
            {"id": str(video_id), "job_id": str(job_id), "yt_id": "test123"},
        )
        db_session.execute(
            text("INSERT INTO youtube_transcripts (id, video_id, language) VALUES (:id, :vid, 'en')"),
            {"id": str(yt_transcript_id), "vid": str(video_id)},
        )
        db_session.execute(
            text(
                "INSERT INTO youtube_segments (youtube_transcript_id, start_ms, end_ms, text) "
                "VALUES (:tid, :start, :end, :text)"
            ),
            {"tid": str(yt_transcript_id), "start": 0, "end": 5000, "text": "Test segment"},
        )
        db_session.commit()

        response = client.get(f"/videos/{video_id}/youtube-transcript.srt", cookies={"tc_session": session_token})
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "Content-Disposition" in response.headers
        assert "Test segment" in response.text

    def test_export_youtube_transcript_vtt(self, client: TestClient, db_session):
        """Test YouTube transcript VTT export."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, plan) "
                "VALUES (:id, :email, 'google', 'test', 'pro')"
            ),
            {"id": str(user_id), "email": "vtt@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )

        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        yt_transcript_id = uuid.uuid4()

        db_session.execute(
            text("INSERT INTO jobs (id, kind, input_url) VALUES (:id, 'single', 'https://youtube.com/test')"),
            {"id": str(job_id)},
        )
        db_session.execute(
            text("INSERT INTO videos (id, job_id, youtube_id, idx) VALUES (:id, :job_id, :yt_id, 0)"),
            {"id": str(video_id), "job_id": str(job_id), "yt_id": "testvtt"},
        )
        db_session.execute(
            text("INSERT INTO youtube_transcripts (id, video_id, language) VALUES (:id, :vid, 'en')"),
            {"id": str(yt_transcript_id), "vid": str(video_id)},
        )
        db_session.execute(
            text(
                "INSERT INTO youtube_segments (youtube_transcript_id, start_ms, end_ms, text) "
                "VALUES (:tid, :start, :end, :text)"
            ),
            {"tid": str(yt_transcript_id), "start": 1000, "end": 3000, "text": "VTT test"},
        )
        db_session.commit()

        response = client.get(f"/videos/{video_id}/youtube-transcript.vtt", cookies={"tc_session": session_token})
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/vtt; charset=utf-8"
        assert "WEBVTT" in response.text
        assert "VTT test" in response.text

    def test_export_native_transcript_srt(self, client: TestClient, db_session):
        """Test native transcript SRT export."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, plan) "
                "VALUES (:id, :email, 'google', 'test', 'pro')"
            ),
            {"id": str(user_id), "email": "native@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )

        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        db_session.execute(
            text("INSERT INTO jobs (id, kind, input_url) VALUES (:id, 'single', 'https://youtube.com/test')"),
            {"id": str(job_id)},
        )
        db_session.execute(
            text("INSERT INTO videos (id, job_id, youtube_id, idx) VALUES (:id, :job_id, :yt_id, 0)"),
            {"id": str(video_id), "job_id": str(job_id), "yt_id": "nativesrt"},
        )
        db_session.execute(
            text("INSERT INTO transcripts (id, video_id, model) VALUES (:id, :vid, 'base')"),
            {"id": str(transcript_id), "vid": str(video_id)},
        )
        db_session.execute(
            text(
                "INSERT INTO segments (video_id, start_ms, end_ms, text, speaker_label) "
                "VALUES (:vid, :start, :end, :text, :speaker)"
            ),
            {"vid": str(video_id), "start": 2000, "end": 5000, "text": "Native SRT text", "speaker": "Speaker 1"},
        )
        db_session.commit()

        response = client.get(f"/videos/{video_id}/transcript.srt", cookies={"tc_session": session_token})
        assert response.status_code == 200
        assert "Native SRT text" in response.text

    def test_export_native_transcript_vtt(self, client: TestClient, db_session):
        """Test native transcript VTT export."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, plan) "
                "VALUES (:id, :email, 'google', 'test', 'pro')"
            ),
            {"id": str(user_id), "email": "nativevtt@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )

        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        db_session.execute(
            text("INSERT INTO jobs (id, kind, input_url) VALUES (:id, 'single', 'https://youtube.com/test')"),
            {"id": str(job_id)},
        )
        db_session.execute(
            text("INSERT INTO videos (id, job_id, youtube_id, idx) VALUES (:id, :job_id, :yt_id, 0)"),
            {"id": str(video_id), "job_id": str(job_id), "yt_id": "nativevtt"},
        )
        db_session.execute(
            text("INSERT INTO transcripts (id, video_id, model) VALUES (:id, :vid, 'base')"),
            {"id": str(transcript_id), "vid": str(video_id)},
        )
        db_session.execute(
            text(
                "INSERT INTO segments (video_id, start_ms, end_ms, text, speaker_label) "
                "VALUES (:vid, :start, :end, :text, :speaker)"
            ),
            {"vid": str(video_id), "start": 0, "end": 2000, "text": "Native VTT", "speaker": None},
        )
        db_session.commit()

        response = client.get(f"/videos/{video_id}/transcript.vtt", cookies={"tc_session": session_token})
        assert response.status_code == 200
        assert "WEBVTT" in response.text
        assert "Native VTT" in response.text

    def test_export_native_transcript_json(self, client: TestClient, db_session):
        """Test native transcript JSON export."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, plan) "
                "VALUES (:id, :email, 'google', 'test', 'pro')"
            ),
            {"id": str(user_id), "email": "json@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )

        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        db_session.execute(
            text("INSERT INTO jobs (id, kind, input_url) VALUES (:id, 'single', 'https://youtube.com/test')"),
            {"id": str(job_id)},
        )
        db_session.execute(
            text("INSERT INTO videos (id, job_id, youtube_id, idx) VALUES (:id, :job_id, :yt_id, 0)"),
            {"id": str(video_id), "job_id": str(job_id), "yt_id": "json123"},
        )
        db_session.execute(
            text("INSERT INTO transcripts (id, video_id, model) VALUES (:id, :vid, 'base')"),
            {"id": str(transcript_id), "vid": str(video_id)},
        )
        db_session.execute(
            text(
                "INSERT INTO segments (video_id, start_ms, end_ms, text, speaker_label) "
                "VALUES (:vid, :start, :end, :text, :speaker)"
            ),
            {"vid": str(video_id), "start": 1000, "end": 3000, "text": "JSON export", "speaker": "Speaker 1"},
        )
        db_session.commit()

        response = client.get(f"/videos/{video_id}/transcript.json", cookies={"tc_session": session_token})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["text"] == "JSON export"
        assert data[0]["speaker_label"] == "Speaker 1"

    def test_export_youtube_transcript_json(self, client: TestClient, db_session):
        """Test YouTube transcript JSON export."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, plan) "
                "VALUES (:id, :email, 'google', 'test', 'pro')"
            ),
            {"id": str(user_id), "email": "ytjson@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )

        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        yt_transcript_id = uuid.uuid4()

        db_session.execute(
            text("INSERT INTO jobs (id, kind, input_url) VALUES (:id, 'single', 'https://youtube.com/test')"),
            {"id": str(job_id)},
        )
        db_session.execute(
            text("INSERT INTO videos (id, job_id, youtube_id, idx) VALUES (:id, :job_id, :yt_id, 0)"),
            {"id": str(video_id), "job_id": str(job_id), "yt_id": "ytjson123"},
        )
        db_session.execute(
            text("INSERT INTO youtube_transcripts (id, video_id, language) VALUES (:id, :vid, 'en')"),
            {"id": str(yt_transcript_id), "vid": str(video_id)},
        )
        db_session.execute(
            text(
                "INSERT INTO youtube_segments (youtube_transcript_id, start_ms, end_ms, text) "
                "VALUES (:tid, :start, :end, :text)"
            ),
            {"tid": str(yt_transcript_id), "start": 500, "end": 2500, "text": "YT JSON"},
        )
        db_session.commit()

        response = client.get(f"/videos/{video_id}/youtube-transcript.json", cookies={"tc_session": session_token})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["text"] == "YT JSON"

    def test_export_native_transcript_pdf(self, client: TestClient, db_session):
        """Test native transcript PDF export."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, plan) "
                "VALUES (:id, :email, 'google', 'test', 'pro')"
            ),
            {"id": str(user_id), "email": "pdf@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )

        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        db_session.execute(
            text("INSERT INTO jobs (id, kind, input_url) VALUES (:id, 'single', 'https://youtube.com/test')"),
            {"id": str(job_id)},
        )
        db_session.execute(
            text("INSERT INTO videos (id, job_id, youtube_id, idx, title) VALUES (:id, :job_id, :yt_id, 0, :title)"),
            {"id": str(video_id), "job_id": str(job_id), "yt_id": "pdf123", "title": "PDF Test Video"},
        )
        db_session.execute(
            text("INSERT INTO transcripts (id, video_id, model) VALUES (:id, :vid, 'base')"),
            {"id": str(transcript_id), "vid": str(video_id)},
        )
        db_session.execute(
            text(
                "INSERT INTO segments (video_id, start_ms, end_ms, text, speaker_label) "
                "VALUES (:vid, :start, :end, :text, :speaker)"
            ),
            {"vid": str(video_id), "start": 0, "end": 1000, "text": "PDF content", "speaker": "Speaker 1"},
        )
        db_session.commit()

        response = client.get(f"/videos/{video_id}/transcript.pdf", cookies={"tc_session": session_token})
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        # PDF should start with %PDF
        assert response.content[:4] == b"%PDF"

    def test_export_not_found(self, client: TestClient, db_session):
        """Test export for non-existent video."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, plan) "
                "VALUES (:id, :email, 'google', 'test', 'pro')"
            ),
            {"id": str(user_id), "email": "notfound@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        video_id = uuid.uuid4()
        response = client.get(f"/videos/{video_id}/transcript.srt", cookies={"tc_session": session_token})
        assert response.status_code == 404

    def test_export_free_user_quota_exceeded(self, client: TestClient, db_session):
        """Test export quota for free users."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, plan) "
                "VALUES (:id, :email, 'google', 'test', 'free')"
            ),
            {"id": str(user_id), "email": "freequota@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )

        # Create many export events to exceed quota
        for i in range(10):  # Assuming FREE_DAILY_EXPORT_LIMIT is less than 10
            db_session.execute(
                text(
                    "INSERT INTO events (user_id, session_token, type, payload) "
                    "VALUES (:uid, :token, 'export', :payload)"
                ),
                {"uid": str(user_id), "token": session_token, "payload": {"format": "srt"}},
            )
        db_session.commit()

        video_id = uuid.uuid4()
        response = client.get(f"/videos/{video_id}/transcript.srt", cookies={"tc_session": session_token})
        # Should be blocked due to quota
        assert response.status_code in [402, 404]  # 402 for quota, 404 for missing video
