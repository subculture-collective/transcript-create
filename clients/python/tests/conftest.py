"""Test configuration for the Python client package tests.

Ensures the package root (clients/python) is on sys.path so
`import transcript_create_client` works when running tests from repo root.
"""

import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
"""Pytest configuration and fixtures for SDK tests."""

import pytest


@pytest.fixture
def base_url() -> str:
    """Base URL for testing."""
    return "http://test.example.com"


@pytest.fixture
def api_key() -> str:
    """API key for testing."""
    return "test_api_key_12345"
