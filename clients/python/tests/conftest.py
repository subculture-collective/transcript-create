"""Pytest configuration and fixtures for SDK tests."""

import pytest
from pytest_httpx import HTTPXMock


@pytest.fixture
def base_url() -> str:
    """Base URL for testing."""
    return "http://test.example.com"


@pytest.fixture
def api_key() -> str:
    """API key for testing."""
    return "test_api_key_12345"
