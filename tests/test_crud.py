"""Tests for CRUD operations."""

import uuid

import pytest
from sqlalchemy import text

from app import crud


class TestJobCrud:
    """Tests for job-related CRUD operations."""

    def test_create_job_success(self, db_session):
        """Test creating a job successfully."""
        job_id = crud.create_job(db_session, "single", "https://youtube.com/watch?v=test123")
        assert isinstance(job_id, uuid.UUID)

        # Verify the job was created in the database
        job = crud.fetch_job(db_session, job_id)
        assert job is not None
        assert job["kind"] == "single"
        assert job["input_url"] == "https://youtube.com/watch?v=test123"
        assert job["state"] == "pending"

    def test_create_job_channel(self, db_session):
        """Test creating a channel job."""
        job_id = crud.create_job(db_session, "channel", "https://youtube.com/channel/UCtest")
        job = crud.fetch_job(db_session, job_id)
        assert job["kind"] == "channel"

    def test_fetch_job_not_found(self, db_session):
        """Test fetching a non-existent job."""
        non_existent_id = uuid.uuid4()
        job = crud.fetch_job(db_session, non_existent_id)
        assert job is None


class TestVideoCrud:
    """Tests for video-related CRUD operations."""

    def test_get_video(self, db_session):
        """Test getting a video by ID."""
        # Create a test job and video
        job_id = crud.create_job(db_session, "single", "https://youtube.com/watch?v=test")
        video_id = uuid.uuid4()
        db_session.execute(
            text(
                "INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds) "
                "VALUES (:id, :job_id, :yt_id, 0, :title, :duration)"
            ),
            {
                "id": str(video_id),
                "job_id": str(job_id),
                "yt_id": "test123",
                "title": "Test Video",
                "duration": 120,
            },
        )
        db_session.commit()

        # Fetch the video
        video = crud.get_video(db_session, video_id)
        assert video is not None
        assert video["youtube_id"] == "test123"
        assert video["title"] == "Test Video"
        assert video["duration_seconds"] == 120

    def test_get_video_not_found(self, db_session):
        """Test getting a non-existent video."""
        non_existent_id = uuid.uuid4()
        video = crud.get_video(db_session, non_existent_id)
        assert video is None

    def test_list_videos(self, db_session):
        """Test listing videos with pagination."""
        # Create a test job
        job_id = crud.create_job(db_session, "single", "https://youtube.com/watch?v=test")

        # Create multiple videos
        video_ids = []
        for i in range(3):
            video_id = uuid.uuid4()
            video_ids.append(video_id)
            db_session.execute(
                text(
                    "INSERT INTO videos (id, job_id, youtube_id, idx, title) "
                    "VALUES (:id, :job_id, :yt_id, :idx, :title)"
                ),
                {"id": str(video_id), "job_id": str(job_id), "yt_id": f"test{i}", "idx": i, "title": f"Video {i}"},
            )
        db_session.commit()

        # List videos
        videos = crud.list_videos(db_session, limit=10, offset=0)
        assert len(videos) >= 3
        video_ids_str = [str(vid) for vid in video_ids]
        returned_ids = [str(v["id"]) for v in videos]
        for vid_str in video_ids_str:
            assert vid_str in returned_ids

    def test_list_videos_pagination(self, db_session):
        """Test listing videos with pagination limits."""
        videos = crud.list_videos(db_session, limit=2, offset=0)
        assert len(videos) <= 2


class TestSegmentCrud:
    """Tests for segment-related CRUD operations."""

    def test_list_segments_empty(self, db_session):
        """Test listing segments for a video with no segments."""
        video_id = uuid.uuid4()
        segments = crud.list_segments(db_session, video_id)
        assert len(segments) == 0

    def test_list_segments_with_data(self, db_session):
        """Test listing segments for a video with segments."""
        # Create a test job, video, and transcript
        job_id = crud.create_job(db_session, "single", "https://youtube.com/watch?v=test")
        video_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        db_session.execute(
            text("INSERT INTO videos (id, job_id, youtube_id, idx) VALUES (:id, :job_id, :yt_id, 0)"),
            {"id": str(video_id), "job_id": str(job_id), "yt_id": "test123"},
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
            {"vid": str(video_id), "start": 0, "end": 1000, "text": "Hello world", "speaker": "Speaker 1"},
        )
        db_session.commit()

        # Fetch segments
        segments = crud.list_segments(db_session, video_id)
        assert len(segments) == 1
        assert segments[0][0] == 0  # start_ms
        assert segments[0][1] == 1000  # end_ms
        assert segments[0][2] == "Hello world"  # text
        assert segments[0][3] == "Speaker 1"  # speaker_label


class TestYouTubeTranscriptCrud:
    """Tests for YouTube transcript CRUD operations."""

    def test_get_youtube_transcript_not_found(self, db_session):
        """Test getting a non-existent YouTube transcript."""
        video_id = uuid.uuid4()
        yt_transcript = crud.get_youtube_transcript(db_session, video_id)
        assert yt_transcript is None

    def test_get_youtube_transcript_with_data(self, db_session):
        """Test getting a YouTube transcript with data."""
        # Create test data
        job_id = crud.create_job(db_session, "single", "https://youtube.com/watch?v=test")
        video_id = uuid.uuid4()
        yt_transcript_id = uuid.uuid4()

        db_session.execute(
            text("INSERT INTO videos (id, job_id, youtube_id, idx) VALUES (:id, :job_id, :yt_id, 0)"),
            {"id": str(video_id), "job_id": str(job_id), "yt_id": "test123"},
        )
        db_session.execute(
            text(
                "INSERT INTO youtube_transcripts (id, video_id, language, kind, full_text) "
                "VALUES (:id, :vid, :lang, :kind, :text)"
            ),
            {"id": str(yt_transcript_id), "vid": str(video_id), "lang": "en", "kind": "asr", "text": "Full text"},
        )
        db_session.commit()

        # Fetch transcript
        yt = crud.get_youtube_transcript(db_session, video_id)
        assert yt is not None
        assert yt["language"] == "en"
        assert yt["kind"] == "asr"
        assert yt["full_text"] == "Full text"

    def test_list_youtube_segments(self, db_session):
        """Test listing YouTube segments."""
        # Create test data
        job_id = crud.create_job(db_session, "single", "https://youtube.com/watch?v=test")
        video_id = uuid.uuid4()
        yt_transcript_id = uuid.uuid4()

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
            {"tid": str(yt_transcript_id), "start": 0, "end": 2000, "text": "YouTube segment"},
        )
        db_session.commit()

        # Fetch segments
        segments = crud.list_youtube_segments(db_session, yt_transcript_id)
        assert len(segments) == 1
        assert segments[0][0] == 0
        assert segments[0][1] == 2000
        assert segments[0][2] == "YouTube segment"


class TestSearchCrud:
    """Tests for search-related CRUD operations."""

    def test_search_segments_empty_query(self, db_session):
        """Test searching segments with an empty result."""
        results = crud.search_segments(db_session, q="nonexistentquery12345", limit=10, offset=0)
        assert len(results) == 0

    def test_search_youtube_segments_empty_query(self, db_session):
        """Test searching YouTube segments with an empty result."""
        results = crud.search_youtube_segments(db_session, q="nonexistentquery12345", limit=10, offset=0)
        assert len(results) == 0

    def test_search_segments_with_video_filter(self, db_session):
        """Test searching segments with video ID filter."""
        video_id = uuid.uuid4()
        results = crud.search_segments(db_session, q="test", video_id=str(video_id), limit=10, offset=0)
        # Should not error, even if no results
        assert isinstance(results, list)
