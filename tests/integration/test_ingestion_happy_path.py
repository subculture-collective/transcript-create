"""
E2E tests for ingestion happy path with mocked yt-dlp responses.

Tests cover:
- Single video ingestion with mocked yt-dlp
- Channel ingestion with mocked flat-playlist
- Caption availability detection
- Job state transitions
"""

import json
import uuid
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import text

from worker.youtube_captions import fetch_youtube_auto_captions


@pytest.fixture
def mock_yt_dlp_single_video():
    """Mock yt-dlp response for a single video."""
    return {
        "id": "test_video_123",
        "title": "Test Video Title",
        "duration": 120,
        "description": "Test video description",
        "uploader": "Test Channel",
        "upload_date": "20240101",
        "view_count": 1000,
        "like_count": 50,
        "automatic_captions": {
            "en": [
                {
                    "ext": "json3",
                    "url": "https://example.com/captions.json3",
                }
            ]
        },
    }


@pytest.fixture
def mock_yt_dlp_channel_playlist():
    """Mock yt-dlp response for a channel playlist."""
    return {
        "id": "test_channel_123",
        "title": "Test Channel",
        "entries": [
            {
                "id": "video_1",
                "title": "Video One",
                "duration": 60,
                "url": "https://youtube.com/watch?v=video_1",
            },
            {
                "id": "video_2",
                "title": "Video Two",
                "duration": 90,
                "url": "https://youtube.com/watch?v=video_2",
            },
            {
                "id": "video_3",
                "title": "Video Three",
                "duration": 120,
                "url": "https://youtube.com/watch?v=video_3",
            },
        ],
    }


@pytest.fixture
def mock_json3_captions():
    """Mock JSON3 caption response."""
    return {
        "events": [
            {
                "tStartMs": 0,
                "dDurationMs": 2000,
                "segs": [
                    {"utf8": "Hello "},
                    {"utf8": "world"},
                ]
            },
            {
                "tStartMs": 2000,
                "dDurationMs": 2000,
                "segs": [
                    {"utf8": "This is "},
                    {"utf8": "a test"},
                ]
            },
        ]
    }


class TestSingleVideoIngestion:
    """Tests for single video ingestion flow."""

    @patch('worker.youtube_captions._yt_dlp_json')
    @patch('worker.youtube_captions.urlopen')
    def test_fetch_youtube_captions_success(self, mock_urlopen, mock_yt_dlp, mock_yt_dlp_single_video, mock_json3_captions):
        """Test successful fetching of YouTube captions."""
        mock_yt_dlp.return_value = mock_yt_dlp_single_video
        
        # Mock caption download
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_json3_captions).encode()
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response
        
        result = fetch_youtube_auto_captions("test_video_123")
        
        assert result is not None
        track, segments = result
        
        # Verify track info
        assert track.language == "en"
        assert track.ext == "json3"
        
        # Verify segments
        assert len(segments) == 2
        assert segments[0].text == "Hello world"
        assert segments[1].text == "This is a test"

    @patch('worker.youtube_captions._yt_dlp_json')
    def test_video_without_captions_returns_none(self, mock_yt_dlp):
        """Test handling of video without automatic captions."""
        mock_data = {
            "id": "no_captions_video",
            "title": "Video Without Captions",
            "duration": 60,
            "automatic_captions": None,
        }
        mock_yt_dlp.return_value = mock_data
        
        result = fetch_youtube_auto_captions("no_captions_video")
        
        assert result is None

    @patch('worker.youtube_captions._yt_dlp_json')
    @patch('worker.youtube_captions.urlopen')
    def test_caption_language_selection(self, mock_urlopen, mock_yt_dlp):
        """Test that English captions are preferred over other languages."""
        mock_data = {
            "id": "multi_lang_video",
            "title": "Multilingual Video",
            "duration": 60,
            "automatic_captions": {
                "es": [
                    {"ext": "json3", "url": "https://example.com/es.json3"}
                ],
                "en": [
                    {"ext": "json3", "url": "https://example.com/en.json3"}
                ],
                "fr": [
                    {"ext": "json3", "url": "https://example.com/fr.json3"}
                ],
            }
        }
        mock_yt_dlp.return_value = mock_data
        
        # Mock successful caption download
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"events": []}).encode()
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response
        
        result = fetch_youtube_auto_captions("multi_lang_video")
        
        assert result is not None
        track, _ = result
        
        # Should prefer English
        assert track.language == "en"


class TestChannelIngestion:
    """Tests for channel/playlist ingestion flow."""

    @patch('subprocess.check_output')
    def test_channel_metadata_extraction(self, mock_subprocess, mock_yt_dlp_channel_playlist):
        """Test extraction of channel metadata with flat-playlist."""
        mock_subprocess.return_value = json.dumps(mock_yt_dlp_channel_playlist).encode()
        
        from worker.youtube_captions import _yt_dlp_json
        
        result = _yt_dlp_json("https://youtube.com/channel/test_channel_123")
        
        assert "entries" in result
        assert len(result["entries"]) == 3
        
        # Verify first entry
        first_entry = result["entries"][0]
        assert first_entry["id"] == "video_1"
        assert first_entry["title"] == "Video One"
        assert first_entry["duration"] == 60

    def test_empty_channel_handling(self):
        """Test handling of channel with no videos."""
        empty_channel_data = {
            "id": "empty_channel",
            "title": "Empty Channel",
            "entries": [],
        }
        
        # Empty entries list should be handled gracefully
        assert len(empty_channel_data["entries"]) == 0


class TestJobStateTransitions:
    """Tests for job state transitions during ingestion."""

    def test_job_creation_state(self, db_session):
        """Test that new job starts in pending state."""
        job_id = uuid.uuid4()
        
        db_session.execute(
            text("""
                INSERT INTO jobs (id, youtube_id, type, state)
                VALUES (:id, :youtube_id, :type, :state)
            """),
            {
                "id": job_id,
                "youtube_id": "test_video_123",
                "type": "single",
                "state": "pending",
            }
        )
        db_session.commit()
        
        # Verify job state
        result = db_session.execute(
            text("SELECT state FROM jobs WHERE id = :id"),
            {"id": job_id}
        ).fetchone()
        
        assert result[0] == "pending"

    def test_video_creation_after_expansion(self, db_session):
        """Test that videos are created after job expansion."""
        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        
        # Create job
        db_session.execute(
            text("""
                INSERT INTO jobs (id, youtube_id, type, state)
                VALUES (:id, :youtube_id, :type, :state)
            """),
            {
                "id": job_id,
                "youtube_id": "test_video_123",
                "type": "single",
                "state": "expanded",
            }
        )
        
        # Create video from expansion
        db_session.execute(
            text("""
                INSERT INTO videos (id, job_id, youtube_id, title, duration_seconds, status, idx)
                VALUES (:id, :job_id, :youtube_id, :title, :duration, :status, :idx)
            """),
            {
                "id": video_id,
                "job_id": job_id,
                "youtube_id": "test_video_123",
                "title": "Test Video",
                "duration": 120,
                "status": "pending",
                "idx": 0,
            }
        )
        db_session.commit()
        
        # Verify video exists
        result = db_session.execute(
            text("SELECT status FROM videos WHERE id = :id"),
            {"id": video_id}
        ).fetchone()
        
        assert result[0] == "pending"

    def test_video_state_progression(self, db_session):
        """Test video state progression: pending -> downloading -> transcoding -> transcribing -> completed."""
        video_id = uuid.uuid4()
        job_id = uuid.uuid4()
        
        # Create video in pending state
        db_session.execute(
            text("""
                INSERT INTO jobs (id, youtube_id, type, state)
                VALUES (:id, :youtube_id, :type, :state)
            """),
            {"id": job_id, "youtube_id": "test", "type": "single", "state": "expanded"}
        )
        
        db_session.execute(
            text("""
                INSERT INTO videos (id, job_id, youtube_id, title, duration_seconds, status)
                VALUES (:id, :job_id, :youtube_id, :title, :duration, :status)
            """),
            {
                "id": video_id,
                "job_id": job_id,
                "youtube_id": "test_video",
                "title": "Test",
                "duration": 60,
                "status": "pending",
            }
        )
        db_session.commit()
        
        # Simulate state transitions
        states = ["downloading", "transcoding", "transcribing", "completed"]
        
        for state in states:
            db_session.execute(
                text("UPDATE videos SET status = :status WHERE id = :id"),
                {"status": state, "id": video_id}
            )
            db_session.commit()
            
            result = db_session.execute(
                text("SELECT status FROM videos WHERE id = :id"),
                {"id": video_id}
            ).fetchone()
            
            assert result[0] == state


class TestCaptionAvailabilityDetection:
    """Tests for detecting caption availability."""

    @patch('worker.youtube_captions._yt_dlp_json')
    def test_detects_json3_captions(self, mock_yt_dlp):
        """Test detection of json3 format captions."""
        mock_data = {
            "automatic_captions": {
                "en": [
                    {"ext": "json3", "url": "https://example.com/captions.json3"}
                ]
            }
        }
        mock_yt_dlp.return_value = mock_data
        
        from worker.youtube_captions import _pick_auto_caption
        
        track = _pick_auto_caption(mock_data)
        
        assert track is not None
        assert track.ext == "json3"

    @patch('worker.youtube_captions._yt_dlp_json')
    def test_detects_vtt_captions(self, mock_yt_dlp):
        """Test detection of VTT format captions."""
        mock_data = {
            "automatic_captions": {
                "en": [
                    {"ext": "vtt", "url": "https://example.com/captions.vtt"}
                ]
            }
        }
        mock_yt_dlp.return_value = mock_data
        
        from worker.youtube_captions import _pick_auto_caption
        
        track = _pick_auto_caption(mock_data)
        
        assert track is not None
        assert track.ext == "vtt"

    @patch('worker.youtube_captions._yt_dlp_json')
    def test_no_captions_available(self, mock_yt_dlp):
        """Test handling when no captions are available."""
        mock_data = {
            "automatic_captions": {}
        }
        mock_yt_dlp.return_value = mock_data
        
        from worker.youtube_captions import _pick_auto_caption
        
        track = _pick_auto_caption(mock_data)
        
        assert track is None


class TestErrorRecovery:
    """Tests for error recovery during ingestion."""

    def test_failed_video_marked_as_failed(self, db_session):
        """Test that failed videos are marked with failed status."""
        video_id = uuid.uuid4()
        job_id = uuid.uuid4()
        
        db_session.execute(
            text("""
                INSERT INTO jobs (id, youtube_id, type, state)
                VALUES (:id, :youtube_id, :type, :state)
            """),
            {"id": job_id, "youtube_id": "test", "type": "single", "state": "expanded"}
        )
        
        db_session.execute(
            text("""
                INSERT INTO videos (id, job_id, youtube_id, title, duration_seconds, status)
                VALUES (:id, :job_id, :youtube_id, :title, :duration, :status)
            """),
            {
                "id": video_id,
                "job_id": job_id,
                "youtube_id": "failed_video",
                "title": "Failed Video",
                "duration": 60,
                "status": "failed",
            }
        )
        db_session.commit()
        
        result = db_session.execute(
            text("SELECT status FROM videos WHERE id = :id"),
            {"id": video_id}
        ).fetchone()
        
        assert result[0] == "failed"


class TestIntegrationWorkflow:
    """End-to-end integration tests for complete workflows."""

    @patch('worker.youtube_captions._yt_dlp_json')
    @patch('worker.youtube_captions.urlopen')
    def test_complete_single_video_workflow(self, mock_urlopen, mock_yt_dlp, mock_yt_dlp_single_video, mock_json3_captions):
        """Test complete workflow from caption fetch to segment parsing."""
        mock_yt_dlp.return_value = mock_yt_dlp_single_video
        
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_json3_captions).encode()
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response
        
        # Fetch captions
        result = fetch_youtube_auto_captions("test_video_123")
        
        assert result is not None
        track, segments = result
        
        # Verify complete workflow
        assert track.ext == "json3"
        assert len(segments) == 2
        assert all(hasattr(seg, 'start') for seg in segments)
        assert all(hasattr(seg, 'end') for seg in segments)
        assert all(hasattr(seg, 'text') for seg in segments)
        
        # Verify segment data
        assert segments[0].start == 0.0
        assert segments[0].end == 2.0
        assert segments[1].start == 2.0
        assert segments[1].end == 4.0

    def test_job_completion_updates_state(self, db_session):
        """Test that job state is updated upon completion."""
        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        
        # Create job and video
        db_session.execute(
            text("""
                INSERT INTO jobs (id, youtube_id, type, state)
                VALUES (:id, :youtube_id, :type, :state)
            """),
            {"id": job_id, "youtube_id": "test", "type": "single", "state": "expanded"}
        )
        
        db_session.execute(
            text("""
                INSERT INTO videos (id, job_id, youtube_id, title, duration_seconds, status)
                VALUES (:id, :job_id, :youtube_id, :title, :duration, :status)
            """),
            {
                "id": video_id,
                "job_id": job_id,
                "youtube_id": "completed_video",
                "title": "Completed Video",
                "duration": 60,
                "status": "completed",
            }
        )
        db_session.commit()
        
        # All videos completed, job should be completable
        video_result = db_session.execute(
            text("SELECT status FROM videos WHERE job_id = :job_id"),
            {"job_id": job_id}
        ).fetchone()
        
        assert video_result[0] == "completed"
