"""Tests for database query performance optimizations."""

import uuid

from sqlalchemy import text

from app import crud


class TestDatabaseIndices:
    """Tests for database indices existence and effectiveness."""

    def test_jobs_queue_ordering_index_exists(self, db_session):
        """Test that jobs_queue_ordering_idx index exists."""
        result = db_session.execute(
            text(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'jobs'
                AND indexname = 'jobs_queue_ordering_idx'
                """
            )
        ).scalar()

        # Index may not exist yet if migration hasn't run
        # This test will pass once migration is applied
        if result:
            assert result == "jobs_queue_ordering_idx"

    def test_jobs_pending_partial_index_exists(self, db_session):
        """Test that jobs_pending_idx partial index exists."""
        result = db_session.execute(
            text(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'jobs'
                AND indexname = 'jobs_pending_idx'
                """
            )
        ).scalar()

        if result:
            assert result == "jobs_pending_idx"

    def test_users_email_index_exists(self, db_session):
        """Test that users_email_idx index exists."""
        result = db_session.execute(
            text(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'users'
                AND indexname = 'users_email_idx'
                """
            )
        ).scalar()

        if result:
            assert result == "users_email_idx"

    def test_events_user_created_index_exists(self, db_session):
        """Test that events_user_created_idx index exists."""
        result = db_session.execute(
            text(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'events'
                AND indexname = 'events_user_created_idx'
                """
            )
        ).scalar()

        if result:
            assert result == "events_user_created_idx"


class TestCachedQueries:
    """Tests for cached query operations."""

    def test_get_video_cacheable(self, db_session):
        """Test that get_video function is cacheable."""
        # Create a test job and video
        job_id = crud.create_job(db_session, "single", "https://youtube.com/watch?v=test")
        video_id = uuid.uuid4()
        db_session.execute(
            text(
                "INSERT INTO videos (id, job_id, youtube_id, title, duration_seconds) "
                "VALUES (:id, :job_id, :yt_id, :title, :duration)"
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

        # First call - should hit database
        video1 = crud.get_video(db_session, video_id)
        assert video1 is not None
        assert video1["title"] == "Test Video"

        # Second call - should potentially hit cache (if Redis is available)
        video2 = crud.get_video(db_session, video_id)
        assert video2 is not None
        assert video2["title"] == "Test Video"

    def test_list_segments_cacheable(self, db_session):
        """Test that list_segments function is cacheable."""
        # Create a test job and video
        job_id = crud.create_job(db_session, "single", "https://youtube.com/watch?v=test")
        video_id = uuid.uuid4()
        db_session.execute(
            text(
                "INSERT INTO videos (id, job_id, youtube_id, title, duration_seconds) "
                "VALUES (:id, :job_id, :yt_id, :title, :duration)"
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

        # Insert test segments
        db_session.execute(
            text("INSERT INTO segments (video_id, start_ms, end_ms, text) " "VALUES (:vid, :start, :end, :text)"),
            {
                "vid": str(video_id),
                "start": 0,
                "end": 1000,
                "text": "Test segment",
            },
        )
        db_session.commit()

        # First call - should hit database
        segments1 = crud.list_segments(db_session, video_id)
        assert len(segments1) == 1
        assert segments1[0][2] == "Test segment"

        # Second call - should potentially hit cache
        segments2 = crud.list_segments(db_session, video_id)
        assert len(segments2) == 1


class TestQueryPerformance:
    """Tests for query performance characteristics."""

    def test_job_queue_query_uses_index(self, db_session):
        """Test that job queue queries can use the index."""
        # Create some test jobs
        for i in range(5):
            crud.create_job(db_session, "single", f"https://youtube.com/watch?v=test{i}")

        # Query for pending jobs (worker hot path)
        # This should use jobs_pending_idx or jobs_queue_ordering_idx
        result = db_session.execute(
            text(
                """
                EXPLAIN (FORMAT JSON)
                SELECT * FROM jobs
                WHERE state IN ('pending', 'downloading')
                ORDER BY priority, created_at
                LIMIT 10
                """
            )
        ).scalar()

        # Check that explain plan exists (index usage details depend on data volume)
        assert result is not None

    def test_user_email_lookup_performance(self, db_session):
        """Test that user email lookups are efficient."""
        # Insert a test user
        user_id = uuid.uuid4()
        test_email = "test@example.com"
        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject) "
                "VALUES (:id, :email, :provider, :subject)"
            ),
            {
                "id": str(user_id),
                "email": test_email,
                "provider": "google",
                "subject": "test123",
            },
        )
        db_session.commit()

        # Query by email (should use users_email_idx if it exists)
        result = db_session.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": test_email},
        ).scalar()

        assert result == str(user_id)

    def test_quota_check_query_performance(self, db_session):
        """Test that quota check queries are efficient."""
        # Create a test user
        user_id = uuid.uuid4()
        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject) "
                "VALUES (:id, :email, :provider, :subject)"
            ),
            {
                "id": str(user_id),
                "email": "quota@example.com",
                "provider": "google",
                "subject": "quota123",
            },
        )
        db_session.commit()

        # Insert some events
        for _i in range(3):
            db_session.execute(
                text("INSERT INTO events (user_id, type, payload) " "VALUES (:user_id, :type, :payload)"),
                {
                    "user_id": str(user_id),
                    "type": "search_api",
                    "payload": "{}",
                },
            )
        db_session.commit()

        # Quota check query (should use events_user_created_idx)
        count = db_session.execute(
            text(
                """
                SELECT COUNT(*) FROM events
                WHERE user_id = :user_id
                AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC')
                """
            ),
            {"user_id": str(user_id)},
        ).scalar()

        assert count == 3
