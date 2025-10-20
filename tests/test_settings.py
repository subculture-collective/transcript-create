"""Tests for settings and configuration."""

import os


def test_settings_load():
    """Test that settings can be loaded."""
    from app.settings import settings

    assert settings is not None
    assert hasattr(settings, "DATABASE_URL")


def test_database_url_from_env():
    """Test that DATABASE_URL can be read from environment."""
    from app.settings import settings

    # In test environment, DATABASE_URL should be set
    database_url = os.environ.get("DATABASE_URL", settings.DATABASE_URL)
    assert database_url is not None
    assert "postgresql" in database_url
