"""Pytest configuration and fixtures for testing."""

import logging
import os
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.pool import NullPool

from app.db import SessionLocal

# Mock JS runtime validation before importing the app
# This allows tests to run without requiring a JS runtime installed
with patch("app.ytdlp_validation.validate_js_runtime_or_exit"):
    try:
        from app.main import app
    except ImportError as e:
        # Allow worker tests to run without full app dependencies
        app = None
        logging.warning("Could not import app.main (missing dependencies): %s", e)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Get test database URL from environment."""
    return os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")


@pytest.fixture(scope="session")
def test_engine(test_database_url: str):
    """Create a test database engine."""
    try:
        return create_engine(test_database_url, poolclass=NullPool)
    except ModuleNotFoundError as e:
        # Allow worker tests to run without database driver
        logger.warning("Could not create database engine (missing driver): %s", e)
        return None


@pytest.fixture(scope="function")
def db_session(test_engine) -> Generator:
    """Create a new database session for a test."""
    if test_engine is None:
        pytest.skip("Database engine not available (missing driver)")
    connection = test_engine.connect()
    transaction = connection.begin()

    session = SessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="module")
def client() -> Generator:
    """Create a test client for the FastAPI app."""
    if app is None:
        pytest.skip("FastAPI app not available (missing dependencies)")
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def setup_test_database(test_engine):
    """Ensure test database schema is set up."""
    if test_engine is None:
        # Skip database setup if engine not available
        yield
        return
    # Check if tables exist by trying to query a core table
    try:
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM jobs LIMIT 1"))
    except ProgrammingError:
        # Schema doesn't exist (table not found), but we won't create it here
        # The CI will handle schema setup via docker-compose
        logger.warning("Database schema not found. Ensure schema is initialized before running tests.")
        pass
    except (OperationalError, ModuleNotFoundError) as e:
        # Connection or operational issues - log but don't fail for worker unit tests
        logger.warning("Database connection error (skipping for worker unit tests): %s", e)
        pass

    yield
