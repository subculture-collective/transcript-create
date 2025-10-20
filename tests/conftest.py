"""Pytest configuration and fixtures for testing."""

import os
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.db import SessionLocal
from app.main import app


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Get test database URL from environment."""
    return os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")


@pytest.fixture(scope="session")
def test_engine(test_database_url: str):
    """Create a test database engine."""
    return create_engine(test_database_url, poolclass=NullPool)


@pytest.fixture(scope="function")
def db_session(test_engine) -> Generator:
    """Create a new database session for a test."""
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
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def setup_test_database(test_engine):
    """Ensure test database schema is set up."""
    # Check if tables exist by trying to query a core table
    try:
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM jobs LIMIT 1"))
    except Exception:
        # Schema doesn't exist, but we won't create it here
        # The CI will handle schema setup via docker-compose
        pass

    yield
