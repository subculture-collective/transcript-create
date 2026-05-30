import secrets
import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text


def _setup_youtube_export(db_session, *, plan: str = "pro"):
    user_id = uuid.uuid4()
    session_token = secrets.token_urlsafe(32)
    db_session.execute(
        text(
            "INSERT INTO users (id, email, oauth_provider, oauth_subject, plan) "
            "VALUES (:id, :email, 'google', 'test', :plan)"
        ),
        {"id": str(user_id), "email": f"{plan}@example.com", "plan": plan},
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
        {"id": str(video_id), "job_id": str(job_id), "yt_id": "ytcap123"},
    )
    db_session.execute(
        text("INSERT INTO youtube_transcripts (id, video_id, language, kind) VALUES (:id, :vid, 'en', 'asr')"),
        {"id": str(transcript_id), "vid": str(video_id)},
    )
    return video_id, transcript_id, session_token


def test_youtube_caption_json_includes_segments_blocks_and_full_text(client: TestClient, db_session):
    video_id, transcript_id, session_token = _setup_youtube_export(db_session)
    db_session.execute(
        text(
            "INSERT INTO youtube_segments (youtube_transcript_id, start_ms, end_ms, text) "
            "VALUES (:tid, :start, :end, :text)"
        ),
        {"tid": str(transcript_id), "start": 0, "end": 1000, "text": "You"},
    )
    db_session.execute(
        text(
            "INSERT INTO youtube_segments (youtube_transcript_id, start_ms, end_ms, text) "
            "VALUES (:tid, :start, :end, :text)"
        ),
        {"tid": str(transcript_id), "start": 1000, "end": 2000, "text": "Actual caption"},
    )
    db_session.execute(
        text(
            "INSERT INTO youtube_segments (youtube_transcript_id, start_ms, end_ms, text) "
            "VALUES (:tid, :start, :end, :text)"
        ),
        {"tid": str(transcript_id), "start": 2000, "end": 3000, "text": "continues"},
    )
    db_session.commit()

    response = client.get(f"/videos/{video_id}/youtube-transcript.json", cookies={"tc_session": session_token})
    assert response.status_code == 200
    data = response.json()
    assert len(data["segments"]) == 3
    assert data["full_text"] == "Actual caption continues."
    assert len(data["blocks"]) == 1
    assert data["blocks"][0]["text"] == "Actual caption continues."
    assert data["blocks"][0]["segment_ids"] == [1, 2]


def test_youtube_caption_srt_and_vtt_use_formatted_blocks(client: TestClient, db_session):
    video_id, transcript_id, session_token = _setup_youtube_export(db_session)
    db_session.execute(
        text(
            "INSERT INTO youtube_segments (youtube_transcript_id, start_ms, end_ms, text) "
            "VALUES (:tid, :start, :end, :text)"
        ),
        {"tid": str(transcript_id), "start": 0, "end": 1000, "text": "You"},
    )
    db_session.execute(
        text(
            "INSERT INTO youtube_segments (youtube_transcript_id, start_ms, end_ms, text) "
            "VALUES (:tid, :start, :end, :text)"
        ),
        {"tid": str(transcript_id), "start": 1000, "end": 2000, "text": "Actual caption"},
    )
    db_session.execute(
        text(
            "INSERT INTO youtube_segments (youtube_transcript_id, start_ms, end_ms, text) "
            "VALUES (:tid, :start, :end, :text)"
        ),
        {"tid": str(transcript_id), "start": 2000, "end": 3000, "text": "continues"},
    )
    db_session.commit()

    srt = client.get(f"/videos/{video_id}/youtube-transcript.srt", cookies={"tc_session": session_token})
    vtt = client.get(f"/videos/{video_id}/youtube-transcript.vtt", cookies={"tc_session": session_token})
    assert srt.status_code == 200
    assert vtt.status_code == 200
    assert "You" not in srt.text
    assert "Actual caption continues." in srt.text
    assert "WEBVTT" in vtt.text
    assert "You" not in vtt.text
    assert "Actual caption continues." in vtt.text
