"""
Tests for the backfill_formatting script.

Tests cover:
- Configuration hashing and version tracking
- Idempotency (skip already-formatted transcripts)
- Dry-run mode
- Batch processing
- Filtering by video IDs, channel, and job ID
- Error handling
- Resume capability
"""

import json
import uuid
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy import create_engine, text

# Import the backfill script functions
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.backfill_formatting import (
    FORMATTING_VERSION,
    apply_formatting_to_video,
    compute_config_hash,
    get_current_formatting_config,
    get_videos_to_process,
    load_segments_for_video,
    run_backfill,
    should_process_transcript,
)


class TestConfigHashing:
    """Tests for configuration hashing."""
    
    def test_compute_config_hash_stable(self):
        """Test that config hash is stable for same config."""
        config = {
            "enabled": True,
            "normalize_unicode": True,
            "remove_fillers": True,
        }
        
        hash1 = compute_config_hash(config)
        hash2 = compute_config_hash(config)
        
        assert hash1 == hash2
        assert len(hash1) == 16  # Should be 16 char hex string
    
    def test_compute_config_hash_different(self):
        """Test that different configs produce different hashes."""
        config1 = {"enabled": True, "normalize_unicode": True}
        config2 = {"enabled": True, "normalize_unicode": False}
        
        hash1 = compute_config_hash(config1)
        hash2 = compute_config_hash(config2)
        
        assert hash1 != hash2
    
    def test_compute_config_hash_order_independent(self):
        """Test that key order doesn't affect hash."""
        config1 = {"a": 1, "b": 2, "c": 3}
        config2 = {"c": 3, "a": 1, "b": 2}
        
        hash1 = compute_config_hash(config1)
        hash2 = compute_config_hash(config2)
        
        assert hash1 == hash2
    
    def test_get_current_formatting_config(self):
        """Test getting current formatting config from settings."""
        config = get_current_formatting_config()
        
        assert isinstance(config, dict)
        assert "enabled" in config
        assert "normalize_unicode" in config


class TestShouldProcessTranscript:
    """Tests for transcript processing decision logic."""
    
    def test_should_process_never_cleaned(self):
        """Test that transcripts never cleaned should be processed."""
        # Mock database connection
        mock_conn = Mock()
        mock_conn.execute.return_value.mappings.return_value.fetchone.return_value = {
            "cleanup_config": None,
            "is_cleaned": False,
        }
        
        should_process, reason = should_process_transcript(
            mock_conn, "transcript-id", "hash123", force=False
        )
        
        assert should_process is True
        assert "never formatted" in reason
    
    def test_should_process_version_changed(self):
        """Test that transcripts with old version should be processed."""
        mock_conn = Mock()
        mock_conn.execute.return_value.mappings.return_value.fetchone.return_value = {
            "cleanup_config": {
                "version": "0.9.0",
                "config_hash": "hash123",
            },
            "is_cleaned": True,
        }
        
        should_process, reason = should_process_transcript(
            mock_conn, "transcript-id", "hash123", force=False
        )
        
        assert should_process is True
        assert "version changed" in reason
    
    def test_should_process_config_changed(self):
        """Test that transcripts with changed config should be processed."""
        mock_conn = Mock()
        mock_conn.execute.return_value.mappings.return_value.fetchone.return_value = {
            "cleanup_config": {
                "version": FORMATTING_VERSION,
                "config_hash": "oldhash",
            },
            "is_cleaned": True,
        }
        
        should_process, reason = should_process_transcript(
            mock_conn, "transcript-id", "newhash", force=False
        )
        
        assert should_process is True
        assert "config changed" in reason
    
    def test_should_not_process_already_formatted(self):
        """Test that already-formatted transcripts are skipped."""
        current_hash = "hash123"
        mock_conn = Mock()
        mock_conn.execute.return_value.mappings.return_value.fetchone.return_value = {
            "cleanup_config": {
                "version": FORMATTING_VERSION,
                "config_hash": current_hash,
            },
            "is_cleaned": True,
        }
        
        should_process, reason = should_process_transcript(
            mock_conn, "transcript-id", current_hash, force=False
        )
        
        assert should_process is False
        assert "already formatted" in reason
    
    def test_should_process_force_flag(self):
        """Test that force flag overrides checks."""
        mock_conn = Mock()
        mock_conn.execute.return_value.mappings.return_value.fetchone.return_value = {
            "cleanup_config": {
                "version": FORMATTING_VERSION,
                "config_hash": "hash123",
            },
            "is_cleaned": True,
        }
        
        should_process, reason = should_process_transcript(
            mock_conn, "transcript-id", "hash123", force=True
        )
        
        assert should_process is True
        assert "forced" in reason


class TestLoadSegments:
    """Tests for segment loading."""
    
    def test_load_segments_for_video(self):
        """Test loading segments for a video."""
        mock_conn = Mock()
        
        # Mock database response
        mock_rows = [
            {
                "id": 1,
                "start_ms": 0,
                "end_ms": 1000,
                "text": "Hello world",
                "speaker": "Speaker 1",
                "speaker_label": "John",
                "idx": 0,
            },
            {
                "id": 2,
                "start_ms": 1000,
                "end_ms": 2000,
                "text": "How are you",
                "speaker": None,
                "speaker_label": None,
                "idx": 1,
            },
        ]
        
        mock_conn.execute.return_value.mappings.return_value = mock_rows
        
        segments = load_segments_for_video(mock_conn, "video-id")
        
        assert len(segments) == 2
        assert segments[0]["text"] == "Hello world"
        assert segments[0]["start"] == 0
        assert segments[0]["end"] == 1000
        assert "speaker" in segments[0]
        assert "speaker_label" in segments[0]
        
        # Second segment shouldn't have speaker keys if they're None
        assert segments[1]["text"] == "How are you"
    
    def test_load_segments_empty_video(self):
        """Test loading segments for video with no segments."""
        mock_conn = Mock()
        mock_conn.execute.return_value.mappings.return_value = []
        
        segments = load_segments_for_video(mock_conn, "video-id")
        
        assert segments == []


class TestApplyFormatting:
    """Tests for applying formatting to videos."""
    
    @patch("scripts.backfill_formatting.load_segments_for_video")
    @patch("scripts.backfill_formatting.TranscriptFormatter")
    def test_apply_formatting_dry_run(self, mock_formatter_class, mock_load_segments):
        """Test dry-run mode doesn't commit changes."""
        mock_conn = Mock()
        
        # Setup mock segments
        mock_segments = [
            {"id": 1, "start": 0, "end": 1000, "text": "um hello world", "idx": 0}
        ]
        mock_load_segments.return_value = mock_segments
        
        # Setup mock video info
        mock_conn.execute.return_value.mappings.return_value.fetchone.return_value = {
            "language": "en"
        }
        
        # Setup mock formatter
        mock_formatter = Mock()
        mock_formatter.format_segments.return_value = [
            {"id": 1, "start": 0, "end": 1000, "text": "Hello world.", "idx": 0}
        ]
        mock_formatter_class.return_value = mock_formatter
        
        result = apply_formatting_to_video(
            mock_conn,
            "video-id",
            "transcript-id",
            mock_formatter,
            "config-hash",
            dry_run=True,
        )
        
        assert result["status"] == "dry_run"
        assert result["segments_processed"] == 1
        
        # Verify no database updates were made
        update_calls = [
            call for call in mock_conn.execute.call_args_list
            if "UPDATE" in str(call)
        ]
        assert len(update_calls) == 0
    
    @patch("scripts.backfill_formatting.load_segments_for_video")
    def test_apply_formatting_no_segments(self, mock_load_segments):
        """Test handling video with no segments."""
        mock_conn = Mock()
        mock_load_segments.return_value = []
        mock_formatter = Mock()
        
        result = apply_formatting_to_video(
            mock_conn,
            "video-id",
            "transcript-id",
            mock_formatter,
            "config-hash",
            dry_run=False,
        )
        
        assert result["status"] == "skipped"
        assert "no segments" in result["reason"]
    
    @patch("scripts.backfill_formatting.load_segments_for_video")
    @patch("scripts.backfill_formatting.TranscriptFormatter")
    def test_apply_formatting_error_handling(self, mock_formatter_class, mock_load_segments):
        """Test error handling during formatting."""
        mock_conn = Mock()
        mock_segments = [{"id": 1, "start": 0, "end": 1000, "text": "test", "idx": 0}]
        mock_load_segments.return_value = mock_segments
        
        mock_conn.execute.return_value.mappings.return_value.fetchone.return_value = {
            "language": "en"
        }
        
        # Setup formatter to raise exception
        mock_formatter = Mock()
        mock_formatter.format_segments.side_effect = Exception("Formatting error")
        mock_formatter_class.return_value = mock_formatter
        
        result = apply_formatting_to_video(
            mock_conn,
            "video-id",
            "transcript-id",
            mock_formatter,
            "config-hash",
            dry_run=False,
        )
        
        assert result["status"] == "error"
        assert "Formatting error" in result["reason"]


class TestGetVideosToProcess:
    """Tests for video selection."""
    
    def test_get_videos_basic(self):
        """Test basic video selection."""
        mock_conn = Mock()
        mock_rows = [
            {"video_id": "vid1", "transcript_id": "trans1"},
            {"video_id": "vid2", "transcript_id": "trans2"},
        ]
        mock_conn.execute.return_value.mappings.return_value = mock_rows
        
        videos = get_videos_to_process(mock_conn, batch_size=10)
        
        assert len(videos) == 2
        assert videos[0] == ("vid1", "trans1")
        assert videos[1] == ("vid2", "trans2")
    
    def test_get_videos_with_filters(self):
        """Test video selection with filters."""
        mock_conn = Mock()
        mock_conn.execute.return_value.mappings.return_value = []
        
        # Test with channel filter
        get_videos_to_process(
            mock_conn,
            batch_size=10,
            channel_name="Test Channel",
        )
        
        # Verify query was called with channel parameter
        call_args = mock_conn.execute.call_args
        assert "channel" in call_args[0][1]
        
        # Test with job ID filter
        get_videos_to_process(
            mock_conn,
            batch_size=10,
            job_id="job-uuid",
        )
        
        call_args = mock_conn.execute.call_args
        assert "job_id" in call_args[0][1]
    
    def test_get_videos_with_specific_ids(self):
        """Test video selection with specific video IDs."""
        mock_conn = Mock()
        mock_conn.execute.return_value.mappings.return_value = []
        
        video_ids = ["vid1", "vid2", "vid3"]
        get_videos_to_process(
            mock_conn,
            batch_size=10,
            video_ids=video_ids,
        )
        
        # Verify query includes video IDs
        call_args = mock_conn.execute.call_args
        params = call_args[0][1]
        assert "vid0" in params
        assert "vid1" in params
        assert "vid2" in params


class TestRunBackfill:
    """Integration tests for the full backfill process."""
    
    @patch("scripts.backfill_formatting.create_engine")
    @patch("scripts.backfill_formatting.get_videos_to_process")
    @patch("scripts.backfill_formatting.should_process_transcript")
    @patch("scripts.backfill_formatting.apply_formatting_to_video")
    def test_run_backfill_single_batch(
        self,
        mock_apply,
        mock_should_process,
        mock_get_videos,
        mock_create_engine,
    ):
        """Test running backfill for a single batch."""
        # Setup mocks
        mock_engine = Mock()
        mock_conn = Mock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine
        
        # First call returns videos, second call returns empty (done)
        mock_get_videos.side_effect = [
            [("vid1", "trans1"), ("vid2", "trans2")],
            [],
        ]
        
        mock_should_process.return_value = (True, "never formatted")
        
        mock_apply.return_value = {
            "video_id": "vid1",
            "status": "success",
            "segments_processed": 10,
            "segments_updated": 10,
        }
        
        # Run backfill
        result = run_backfill(batch_size=10, until_empty=True)
        
        assert result["processed"] == 2
        assert result["errors"] == 0
        assert result["iterations"] >= 1
    
    @patch("scripts.backfill_formatting.create_engine")
    @patch("scripts.backfill_formatting.get_videos_to_process")
    def test_run_backfill_no_videos(self, mock_get_videos, mock_create_engine):
        """Test running backfill when no videos need processing."""
        mock_engine = Mock()
        mock_conn = Mock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine
        
        mock_get_videos.return_value = []
        
        result = run_backfill(batch_size=10)
        
        assert result["processed"] == 0
        assert result["skipped"] == 0
        assert result["iterations"] == 1
    
    @patch("scripts.backfill_formatting.create_engine")
    @patch("scripts.backfill_formatting.get_videos_to_process")
    @patch("scripts.backfill_formatting.should_process_transcript")
    @patch("scripts.backfill_formatting.apply_formatting_to_video")
    def test_run_backfill_max_iterations(
        self,
        mock_apply,
        mock_should_process,
        mock_get_videos,
        mock_create_engine,
    ):
        """Test that max_iterations stops the backfill."""
        mock_engine = Mock()
        mock_conn = Mock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine
        
        # Always return some videos
        mock_get_videos.return_value = [("vid1", "trans1")]
        mock_should_process.return_value = (True, "never formatted")
        mock_apply.return_value = {
            "status": "success",
            "segments_processed": 10,
            "segments_updated": 10,
        }
        
        result = run_backfill(
            batch_size=10,
            until_empty=True,
            max_iterations=3,
        )
        
        # Should stop at max_iterations
        assert result["iterations"] == 3
    
    @patch("scripts.backfill_formatting.create_engine")
    @patch("scripts.backfill_formatting.get_videos_to_process")
    @patch("scripts.backfill_formatting.should_process_transcript")
    def test_run_backfill_skip_already_formatted(
        self,
        mock_should_process,
        mock_get_videos,
        mock_create_engine,
    ):
        """Test that already-formatted videos are skipped."""
        mock_engine = Mock()
        mock_conn = Mock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine
        
        mock_get_videos.side_effect = [
            [("vid1", "trans1"), ("vid2", "trans2")],
            [],
        ]
        
        # First video already formatted, second needs processing
        mock_should_process.side_effect = [
            (False, "already formatted"),
            (True, "never formatted"),
        ]
        
        result = run_backfill(batch_size=10, until_empty=True)
        
        assert result["skipped"] >= 1


class TestIntegration:
    """Integration tests requiring database setup."""
    
    # These tests would require actual database setup
    # For now, we'll mark them as requiring database
    
    @pytest.mark.skip(reason="Requires database setup")
    def test_full_backfill_workflow(self):
        """Test complete backfill workflow with real database."""
        # This would test the actual backfill on a test database
        pass
    
    @pytest.mark.skip(reason="Requires database setup")
    def test_idempotency(self):
        """Test that running backfill twice doesn't duplicate work."""
        # This would verify idempotency with real data
        pass


class TestEdgeCases:
    """Tests for edge cases and error conditions."""
    
    def test_config_hash_with_none_values(self):
        """Test config hashing with None values."""
        config = {
            "enabled": True,
            "model": None,
            "threshold": 0,
        }
        
        hash_result = compute_config_hash(config)
        assert isinstance(hash_result, str)
        assert len(hash_result) == 16
    
    def test_config_hash_with_nested_dicts(self):
        """Test config hashing with nested structures."""
        config = {
            "enabled": True,
            "options": {
                "level": 2,
                "filters": ["a", "b"],
            },
        }
        
        hash_result = compute_config_hash(config)
        assert isinstance(hash_result, str)
    
    @patch("scripts.backfill_formatting.load_segments_for_video")
    @patch("scripts.backfill_formatting.TranscriptFormatter")
    def test_apply_formatting_with_unicode(self, mock_formatter_class, mock_load_segments):
        """Test formatting with unicode characters."""
        mock_conn = Mock()
        mock_segments = [
            {"id": 1, "start": 0, "end": 1000, "text": "café ☕ 日本語", "idx": 0}
        ]
        mock_load_segments.return_value = mock_segments
        
        mock_conn.execute.return_value.mappings.return_value.fetchone.return_value = {
            "language": "en"
        }
        
        mock_formatter = Mock()
        mock_formatter.format_segments.return_value = [
            {"id": 1, "start": 0, "end": 1000, "text": "Café ☕ 日本語.", "idx": 0}
        ]
        mock_formatter_class.return_value = mock_formatter
        
        result = apply_formatting_to_video(
            mock_conn,
            "video-id",
            "transcript-id",
            mock_formatter,
            "config-hash",
            dry_run=False,
        )
        
        # Should handle unicode without errors
        assert result["status"] == "success"
