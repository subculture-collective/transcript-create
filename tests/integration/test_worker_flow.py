"""Integration tests for worker processing."""

import uuid

import pytest
from sqlalchemy import text


class TestWorkerVideoProcessing:
    """Integration tests for worker video processing."""

    @pytest.mark.timeout(120)
    def test_worker_picks_pending_video(self, integration_db, clean_test_data):
        """Test that worker can pick up pending videos."""
        # Create job and video
        job_id = uuid.uuid4()
        video_id = uuid.uuid4()

        integration_db.execute(
            text(
                """
                INSERT INTO jobs (id, kind, state, input_url)
                VALUES (:job_id, 'single', 'expanded', 'https://youtube.com/watch?v=test')
            """
            ),
            {"job_id": str(job_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state)
                VALUES (:video_id, :job_id, 'test123', 0, 'Test Video', 180, 'pending')
            """
            ),
            {"video_id": str(video_id), "job_id": str(job_id)},
        )
        integration_db.commit()

        # Simulate worker picking video with SKIP LOCKED
        result = integration_db.execute(
            text(
                """
                SELECT id, youtube_id, state
                FROM videos
                WHERE state = 'pending'
                ORDER BY created_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            """
            )
        )
        video = result.mappings().first()

        assert video is not None
        assert str(video["id"]) == str(video_id)
        assert video["state"] == "pending"

    @pytest.mark.timeout(60)
    def test_skip_locked_prevents_double_processing(self, integration_db, clean_test_data):
        """Test that SKIP LOCKED prevents multiple workers from picking same video."""
        # Create job and video
        job_id = uuid.uuid4()
        video_id = uuid.uuid4()

        integration_db.execute(
            text(
                """
                INSERT INTO jobs (id, kind, state, input_url)
                VALUES (:job_id, 'single', 'expanded', 'https://youtube.com/watch?v=test')
            """
            ),
            {"job_id": str(job_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state)
                VALUES (:video_id, :job_id, 'test123', 0, 'Test Video', 180, 'pending')
            """
            ),
            {"video_id": str(video_id), "job_id": str(job_id)},
        )
        integration_db.commit()

        # Start a transaction that locks the video
        conn1 = integration_db.connection()
        trans1 = conn1.begin_nested()

        result1 = conn1.execute(
            text(
                """
                SELECT id FROM videos
                WHERE state = 'pending'
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            """
            )
        )
        video1 = result1.first()
        assert video1 is not None

        # Try to pick video from another session (should skip locked)
        conn2 = integration_db.get_bind().connect()
        trans2 = conn2.begin()

        result2 = conn2.execute(
            text(
                """
                SELECT id FROM videos
                WHERE state = 'pending'
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            """
            )
        )
        video2 = result2.first()

        # Second worker should not get the video
        assert video2 is None

        # Clean up
        trans1.rollback()
        trans2.rollback()
        conn2.close()

    @pytest.mark.timeout(60)
    def test_video_state_updates(self, integration_db, clean_test_data):
        """Test that video state updates work correctly."""
        job_id = uuid.uuid4()
        video_id = uuid.uuid4()

        integration_db.execute(
            text(
                """
                INSERT INTO jobs (id, kind, state, input_url)
                VALUES (:job_id, 'single', 'expanded', 'https://youtube.com/watch?v=test')
            """
            ),
            {"job_id": str(job_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state)
                VALUES (:video_id, :job_id, 'test123', 0, 'Test Video', 180, 'pending')
            """
            ),
            {"video_id": str(video_id), "job_id": str(job_id)},
        )
        integration_db.commit()

        # Update state through typical worker progression
        states = ["downloading", "transcoding", "transcribing", "completed"]

        for state in states:
            integration_db.execute(
                text("UPDATE videos SET state = :state, updated_at = now() WHERE id = :id"),
                {"state": state, "id": str(video_id)},
            )
            integration_db.commit()

            result = integration_db.execute(text("SELECT state FROM videos WHERE id = :id"), {"id": str(video_id)})
            current_state = result.scalar()
            assert current_state == state


class TestWorkerJobExpansion:
    """Integration tests for job expansion."""

    @pytest.mark.timeout(60)
    def test_single_job_expansion(self, integration_db, clean_test_data):
        """Test that single jobs can be expanded into videos."""
        job_id = uuid.uuid4()

        integration_db.execute(
            text(
                """
                INSERT INTO jobs (id, kind, state, input_url)
                VALUES (:job_id, 'single', 'pending', 'https://youtube.com/watch?v=test123')
            """
            ),
            {"job_id": str(job_id)},
        )
        integration_db.commit()

        # Simulate job expansion by inserting video
        video_id = uuid.uuid4()
        integration_db.execute(
            text(
                """
                INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state)
                VALUES (:video_id, :job_id, 'test123', 0, 'Expanded Video', 180, 'pending')
            """
            ),
            {"video_id": str(video_id), "job_id": str(job_id)},
        )

        # Update job state
        integration_db.execute(text("UPDATE jobs SET state = 'expanded' WHERE id = :id"), {"id": str(job_id)})
        integration_db.commit()

        # Verify expansion
        result = integration_db.execute(
            text("SELECT COUNT(*) FROM videos WHERE job_id = :job_id"), {"job_id": str(job_id)}
        )
        count = result.scalar()
        assert count == 1

        result = integration_db.execute(text("SELECT state FROM jobs WHERE id = :id"), {"id": str(job_id)})
        state = result.scalar()
        assert state == "expanded"

    @pytest.mark.timeout(60)
    def test_channel_job_expansion(self, integration_db, clean_test_data):
        """Test that channel jobs can be expanded into multiple videos."""
        job_id = uuid.uuid4()

        integration_db.execute(
            text(
                """
                INSERT INTO jobs (id, kind, state, input_url)
                VALUES (:job_id, 'channel', 'pending', 'https://youtube.com/channel/UCtest')
            """
            ),
            {"job_id": str(job_id)},
        )
        integration_db.commit()

        # Simulate channel expansion by inserting multiple videos
        video_ids = [uuid.uuid4() for _ in range(5)]
        for idx, video_id in enumerate(video_ids):
            integration_db.execute(
                text(
                    """
                    INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state)
                    VALUES (:video_id, :job_id, :youtube_id, :idx, :title, 180, 'pending')
                """
                ),
                {
                    "video_id": str(video_id),
                    "job_id": str(job_id),
                    "youtube_id": f"video{idx}",
                    "idx": idx,
                    "title": f"Channel Video {idx}",
                },
            )

        integration_db.execute(text("UPDATE jobs SET state = 'expanded' WHERE id = :id"), {"id": str(job_id)})
        integration_db.commit()

        # Verify expansion
        result = integration_db.execute(
            text("SELECT COUNT(*) FROM videos WHERE job_id = :job_id"), {"job_id": str(job_id)}
        )
        count = result.scalar()
        assert count == 5


class TestWorkerErrorHandling:
    """Integration tests for worker error handling."""

    @pytest.mark.timeout(60)
    def test_video_failure_state(self, integration_db, clean_test_data):
        """Test that videos can be marked as failed."""
        job_id = uuid.uuid4()
        video_id = uuid.uuid4()

        integration_db.execute(
            text(
                """
                INSERT INTO jobs (id, kind, state, input_url)
                VALUES (:job_id, 'single', 'expanded', 'https://youtube.com/watch?v=test')
            """
            ),
            {"job_id": str(job_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state)
                VALUES (:video_id, :job_id, 'test123', 0, 'Test Video', 180, 'pending')
            """
            ),
            {"video_id": str(video_id), "job_id": str(job_id)},
        )
        integration_db.commit()

        # Mark video as failed
        error_message = "Download failed: Video not available"
        integration_db.execute(
            text("UPDATE videos SET state = 'failed', error = :error WHERE id = :id"),
            {"error": error_message, "id": str(video_id)},
        )
        integration_db.commit()

        # Verify failure state
        result = integration_db.execute(text("SELECT state, error FROM videos WHERE id = :id"), {"id": str(video_id)})
        video = result.mappings().first()
        assert video["state"] == "failed"
        assert video["error"] == error_message

    @pytest.mark.timeout(60)
    def test_job_failure_state(self, integration_db, clean_test_data):
        """Test that jobs can be marked as failed."""
        job_id = uuid.uuid4()

        integration_db.execute(
            text(
                """
                INSERT INTO jobs (id, kind, state, input_url)
                VALUES (:job_id, 'single', 'pending', 'https://youtube.com/watch?v=invalid')
            """
            ),
            {"job_id": str(job_id)},
        )
        integration_db.commit()

        # Mark job as failed
        error_message = "Invalid YouTube URL"
        integration_db.execute(
            text("UPDATE jobs SET state = 'failed', error = :error WHERE id = :id"),
            {"error": error_message, "id": str(job_id)},
        )
        integration_db.commit()

        # Verify failure state
        result = integration_db.execute(text("SELECT state, error FROM jobs WHERE id = :id"), {"id": str(job_id)})
        job = result.mappings().first()
        assert job["state"] == "failed"
        assert job["error"] == error_message


class TestWorkerPerformance:
    """Performance tests for worker operations."""

    @pytest.mark.timeout(60)
    def test_large_channel_expansion(self, integration_db, clean_test_data):
        """Test expansion of large channel with many videos."""
        job_id = uuid.uuid4()

        integration_db.execute(
            text(
                """
                INSERT INTO jobs (id, kind, state, input_url)
                VALUES (:job_id, 'channel', 'pending', 'https://youtube.com/channel/UCtest')
            """
            ),
            {"job_id": str(job_id)},
        )
        integration_db.commit()

        # Insert 100 videos
        import time

        start_time = time.time()

        for idx in range(100):
            video_id = uuid.uuid4()
            integration_db.execute(
                text(
                    """
                    INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state)
                    VALUES (:video_id, :job_id, :youtube_id, :idx, :title, 180, 'pending')
                """
                ),
                {
                    "video_id": str(video_id),
                    "job_id": str(job_id),
                    "youtube_id": f"video{idx}",
                    "idx": idx,
                    "title": f"Video {idx}",
                },
            )

        integration_db.commit()
        elapsed = time.time() - start_time

        # Should complete within reasonable time
        assert elapsed < 10.0

        # Verify all videos inserted
        result = integration_db.execute(
            text("SELECT COUNT(*) FROM videos WHERE job_id = :job_id"), {"job_id": str(job_id)}
        )
        count = result.scalar()
        assert count == 100
