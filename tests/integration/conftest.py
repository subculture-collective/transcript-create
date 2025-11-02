"""Pytest configuration and fixtures for integration testing."""

import logging
import os
import time
import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.db import SessionLocal

try:
    from app.main import app
except ImportError as e:
    app = None
    logging.warning("Could not import app.main (missing dependencies): %s", e)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def integration_database_url() -> str:
    """Get integration test database URL from environment."""
    return os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")


@pytest.fixture(scope="session")
def integration_engine(integration_database_url: str):
    """Create an integration test database engine."""
    try:
        return create_engine(integration_database_url, poolclass=NullPool)
    except ModuleNotFoundError as e:
        logger.warning("Could not create database engine (missing driver): %s", e)
        return None


@pytest.fixture(scope="function")
def integration_db(integration_engine) -> Generator:
    """Create a new database session for an integration test."""
    if integration_engine is None:
        pytest.skip("Database engine not available (missing driver)")

    connection = integration_engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def integration_client(integration_db) -> Generator:
    """Create a test client for integration tests, sharing the DB session with the app."""
    if app is None:
        pytest.skip("FastAPI app not available (missing dependencies)")

    # Override the app's DB dependency to use the test session
    from app.db import get_db as real_get_db

    def override_get_db():
        try:
            yield integration_db
        finally:
            pass

    app.dependency_overrides[real_get_db] = override_get_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(real_get_db, None)


@pytest.fixture(scope="function")
def clean_test_data(integration_engine):
    """Clean up test data before and after each test."""
    if integration_engine is None:
        yield
        return

    # Clean up before test
    with integration_engine.begin() as conn:
        conn.execute(text("DELETE FROM segments"))
        conn.execute(text("DELETE FROM transcripts"))
        conn.execute(text("DELETE FROM videos"))
        conn.execute(text("DELETE FROM jobs"))

    yield

    # Clean up after test
    with integration_engine.begin() as conn:
        conn.execute(text("DELETE FROM segments"))
        conn.execute(text("DELETE FROM transcripts"))
        conn.execute(text("DELETE FROM videos"))
        conn.execute(text("DELETE FROM jobs"))


@pytest.fixture
def wait_for_job_completion(integration_engine):
    """Helper fixture to wait for job completion."""

    def _wait(job_id: uuid.UUID, timeout_seconds: int = 300, poll_interval: float = 2.0) -> dict:
        """
        Wait for a job to complete (or fail).

        Args:
            job_id: The job UUID to wait for
            timeout_seconds: Maximum time to wait in seconds
            poll_interval: Time between polls in seconds

        Returns:
            The final job record as dict

        Raises:
            TimeoutError: If job doesn't complete within timeout
        """
        start_time = time.time()
        with integration_engine.connect() as conn:
            while time.time() - start_time < timeout_seconds:
                result = conn.execute(text("SELECT * FROM jobs WHERE id = :id"), {"id": str(job_id)})
                job = result.mappings().first()

                if not job:
                    raise ValueError(f"Job {job_id} not found")

                if job["state"] in ["completed", "failed"]:
                    return dict(job)

                time.sleep(poll_interval)

            raise TimeoutError(f"Job {job_id} did not complete within {timeout_seconds} seconds")

    return _wait


@pytest.fixture
def wait_for_video_completion(integration_engine):
    """Helper fixture to wait for video completion."""

    def _wait(video_id: uuid.UUID, timeout_seconds: int = 300, poll_interval: float = 2.0) -> dict:
        """
        Wait for a video to complete transcription.

        Args:
            video_id: The video UUID to wait for
            timeout_seconds: Maximum time to wait in seconds
            poll_interval: Time between polls in seconds

        Returns:
            The final video record as dict

        Raises:
            TimeoutError: If video doesn't complete within timeout
        """
        start_time = time.time()
        with integration_engine.connect() as conn:
            while time.time() - start_time < timeout_seconds:
                result = conn.execute(text("SELECT * FROM videos WHERE id = :id"), {"id": str(video_id)})
                video = result.mappings().first()

                if not video:
                    raise ValueError(f"Video {video_id} not found")

                if video["state"] in ["completed", "failed"]:
                    return dict(video)

                time.sleep(poll_interval)

            raise TimeoutError(f"Video {video_id} did not complete within {timeout_seconds} seconds")

    return _wait


@pytest.fixture
def mock_youtube_video():
    """Fixture providing mock YouTube video data."""
    return {
        "id": "dQw4w9WgXcQ",
        "title": "Test Video Title",
        "duration": 212,  # 3:32 minutes
        "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
    }


@pytest.fixture
def mock_youtube_channel():
    """Fixture providing mock YouTube channel data."""
    return {
        "id": "UCtest123",
        "title": "Test Channel",
        "url": "https://youtube.com/channel/UCtest123",
        "videos": [
            {"id": "video1", "title": "Video 1", "duration": 180},
            {"id": "video2", "title": "Video 2", "duration": 240},
            {"id": "video3", "title": "Video 3", "duration": 300},
        ],
    }


@pytest.fixture
def sample_transcript_segments():
    """Fixture providing sample transcript segments."""
    return [
        {"start_ms": 0, "end_ms": 1000, "text": "Hello world", "speaker_label": "Speaker 1"},
        {"start_ms": 1000, "end_ms": 2000, "text": "This is a test", "speaker_label": "Speaker 1"},
        {"start_ms": 2000, "end_ms": 3000, "text": "Of the transcription system", "speaker_label": "Speaker 2"},
    ]
