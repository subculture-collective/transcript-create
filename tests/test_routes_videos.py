"""Tests for video routes."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text


class TestVideosRoutes:
    """Tests for /videos endpoints."""

    def test_list_videos_empty(self, client: TestClient):
        """Test listing videos when there are none."""
        response = client.get("/videos")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Could be empty or have pre-existing videos

    def test_list_videos_pagination(self, client: TestClient):
        """Test listing videos with pagination parameters."""
        response = client.get("/videos?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5

    def test_list_videos_invalid_limit(self, client: TestClient):
        """Test listing videos with invalid limit."""
        # Negative limit should be handled
        response = client.get("/videos?limit=-1")
        assert response.status_code == 422  # Validation error

    def test_get_video_not_found(self, client: TestClient):
        """Test getting a non-existent video."""
        non_existent_id = uuid.uuid4()
        response = client.get(f"/videos/{non_existent_id}")
        assert response.status_code == 404

    def test_get_video_invalid_uuid(self, client: TestClient):
        """Test getting a video with invalid UUID."""
        response = client.get("/videos/not-a-uuid")
        assert response.status_code == 422

    def test_get_video_with_data(self, client: TestClient, db_session):
        """Test getting a video that exists."""
        # Create test data
        job_response = client.post("/jobs", json={"url": "https://youtube.com/watch?v=testvideo", "kind": "single"})
        job_id = job_response.json()["id"]

        video_id = uuid.uuid4()
        db_session.execute(
            text(
                "INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds) "
                "VALUES (:id, :job_id, :yt_id, 0, :title, :duration)"
            ),
            {
                "id": str(video_id),
                "job_id": job_id,
                "yt_id": "testvideo123",
                "title": "Test Video Title",
                "duration": 300,
            },
        )
        db_session.commit()

        # Fetch the video
        response = client.get(f"/videos/{video_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(video_id)
        assert data["youtube_id"] == "testvideo123"
        assert data["title"] == "Test Video Title"
        assert data["duration_seconds"] == 300

    def test_get_transcript_no_segments(self, client: TestClient):
        """Test getting a transcript for a video with no segments."""
        non_existent_id = uuid.uuid4()
        response = client.get(f"/videos/{non_existent_id}/transcript")
        assert response.status_code == 404
        assert "No segments" in response.json()["detail"]

    def test_get_transcript_with_segments(self, client: TestClient, db_session):
        """Test getting a transcript with segments."""
        # Create test data
        job_response = client.post("/jobs", json={"url": "https://youtube.com/watch?v=testtranscript"})
        job_id = job_response.json()["id"]

        video_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        db_session.execute(
            text("INSERT INTO videos (id, job_id, youtube_id, idx) VALUES (:id, :job_id, :yt_id, 0)"),
            {"id": str(video_id), "job_id": job_id, "yt_id": "transcript123"},
        )
        db_session.execute(
            text("INSERT INTO transcripts (id, video_id, model) VALUES (:id, :vid, 'base')"),
            {"id": str(transcript_id), "vid": str(video_id)},
        )
        # Add multiple segments
        segments_data = [
            (0, 1000, "Hello world", "Speaker 1"),
            (1000, 2500, "This is a test", "Speaker 2"),
            (2500, 4000, "Final segment", "Speaker 1"),
        ]
        for start, end, seg_text, speaker in segments_data:
            db_session.execute(
                text(
                    "INSERT INTO segments (video_id, start_ms, end_ms, text, speaker_label) "
                    "VALUES (:vid, :start, :end, :text, :speaker)"
                ),
                {"vid": str(video_id), "start": start, "end": end, "text": seg_text, "speaker": speaker},
            )
        db_session.commit()

        # Fetch transcript
        response = client.get(f"/videos/{video_id}/transcript")
        assert response.status_code == 200
        data = response.json()
        assert data["video_id"] == str(video_id)
        assert len(data["segments"]) == 3
        assert data["segments"][0]["start_ms"] == 0
        assert data["segments"][0]["text"] == "Hello world"
        assert data["segments"][0]["speaker_label"] == "Speaker 1"

    def test_get_transcript_segments_ordered(self, client: TestClient, db_session):
        """Test that transcript segments are returned in order."""
        # Create test data
        job_response = client.post("/jobs", json={"url": "https://youtube.com/watch?v=testorder"})
        job_id = job_response.json()["id"]

        video_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        db_session.execute(
            text("INSERT INTO videos (id, job_id, youtube_id, idx) VALUES (:id, :job_id, :yt_id, 0)"),
            {"id": str(video_id), "job_id": job_id, "yt_id": "order123"},
        )
        db_session.execute(
            text("INSERT INTO transcripts (id, video_id, model) VALUES (:id, :vid, 'base')"),
            {"id": str(transcript_id), "vid": str(video_id)},
        )
        # Add segments in non-sequential order
        segments_data = [
            (3000, 4000, "Third", None),
            (0, 1000, "First", None),
            (1000, 2000, "Second", None),
        ]
        for start, end, seg_text, speaker in segments_data:
            db_session.execute(
                text(
                    "INSERT INTO segments (video_id, start_ms, end_ms, text, speaker_label) "
                    "VALUES (:vid, :start, :end, :text, :speaker)"
                ),
                {"vid": str(video_id), "start": start, "end": end, "text": seg_text, "speaker": speaker},
            )
        db_session.commit()

        # Fetch transcript
        response = client.get(f"/videos/{video_id}/transcript")
        assert response.status_code == 200
        data = response.json()
        # Segments should be ordered by start_ms
        assert data["segments"][0]["text"] == "First"
        assert data["segments"][1]["text"] == "Second"
        assert data["segments"][2]["text"] == "Third"

    def test_get_youtube_transcript_not_found(self, client: TestClient):
        """Test getting a non-existent YouTube transcript."""
        non_existent_id = uuid.uuid4()
        response = client.get(f"/videos/{non_existent_id}/youtube-transcript")
        assert response.status_code == 404
        assert "No YouTube transcript" in response.json()["detail"]

    def test_get_youtube_transcript_with_data(self, client: TestClient, db_session):
        """Test getting a YouTube transcript with data."""
        # Create test data
        job_response = client.post("/jobs", json={"url": "https://youtube.com/watch?v=testyttranscript"})
        job_id = job_response.json()["id"]

        video_id = uuid.uuid4()
        yt_transcript_id = uuid.uuid4()

        db_session.execute(
            text("INSERT INTO videos (id, job_id, youtube_id, idx) VALUES (:id, :job_id, :yt_id, 0)"),
            {"id": str(video_id), "job_id": job_id, "yt_id": "yttranscript123"},
        )
        db_session.execute(
            text(
                "INSERT INTO youtube_transcripts (id, video_id, language, kind, full_text) "
                "VALUES (:id, :vid, :lang, :kind, :text)"
            ),
            {
                "id": str(yt_transcript_id),
                "vid": str(video_id),
                "lang": "en",
                "kind": "asr",
                "text": "Full transcript text",
            },
        )
        db_session.execute(
            text(
                "INSERT INTO youtube_segments (youtube_transcript_id, start_ms, end_ms, text) "
                "VALUES (:tid, :start, :end, :text)"
            ),
            {"tid": str(yt_transcript_id), "start": 0, "end": 3000, "text": "YouTube segment text"},
        )
        db_session.commit()

        # Fetch YouTube transcript
        response = client.get(f"/videos/{video_id}/youtube-transcript")
        assert response.status_code == 200
        data = response.json()
        assert data["video_id"] == str(video_id)
        assert data["language"] == "en"
        assert data["kind"] == "asr"
        assert data["full_text"] == "Full transcript text"
        assert len(data["segments"]) == 1
        assert data["segments"][0]["text"] == "YouTube segment text"

    def test_video_info_fields(self, client: TestClient, db_session):
        """Test that video info contains all required fields."""
        # Create test data
        job_response = client.post("/jobs", json={"url": "https://youtube.com/watch?v=testfields"})
        job_id = job_response.json()["id"]

        video_id = uuid.uuid4()
        db_session.execute(
            text(
                "INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds) "
                "VALUES (:id, :job_id, :yt_id, 0, :title, :duration)"
            ),
            {"id": str(video_id), "job_id": job_id, "yt_id": "fields123", "title": "Test", "duration": 100},
        )
        db_session.commit()

        response = client.get(f"/videos/{video_id}")
        assert response.status_code == 200
        data = response.json()

        required_fields = ["id", "youtube_id"]
        for field in required_fields:
            assert field in data
