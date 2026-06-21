"""Tests for settings and configuration."""

import os

import pytest


def _isolated_settings(**overrides):
    from app.settings import Settings

    return Settings(_env_file=None, **overrides)


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


def test_validate_production_settings_allows_safe_config():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET="super-secret-value",
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
    )

    validate_production_settings(config)


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg://postgres:postgres@db/transcripts",
        "postgresql+psycopg://postgres:change-me-in-production@db/transcripts",
    ],
)
def test_validate_production_settings_rejects_weak_database_password(database_url):
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET="super-secret-value",
        DATABASE_URL=database_url,
        FRONTEND_ORIGIN="https://app.example.com",
    )

    with pytest.raises(ValueError, match="DATABASE_URL"):
        validate_production_settings(config)


def test_validate_production_settings_rejects_unsafe_production_defaults():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET="change-me",
        DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/transcripts",
        FRONTEND_ORIGIN="http://localhost:5173",
    )

    with pytest.raises(ValueError) as exc_info:
        validate_production_settings(config)

    message = str(exc_info.value)
    assert "SESSION_SECRET" in message
    assert "DATABASE_URL" in message
    assert "FRONTEND_ORIGIN" in message


def test_validate_production_settings_rejects_wildcard_cors():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET="super-secret-value",
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
        CORS_ALLOW_ORIGINS="https://app.example.com, *",
    )

    with pytest.raises(ValueError, match="CORS_ALLOW_ORIGINS"):
        validate_production_settings(config)


def test_validate_production_settings_rejects_frontend_origin_with_path():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET="super-secret-value",
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com/path",
    )

    with pytest.raises(ValueError, match="FRONTEND_ORIGIN"):
        validate_production_settings(config)


def test_validate_production_settings_rejects_http_frontend_origin():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET="super-secret-value",
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="http://app.example.com",
    )

    with pytest.raises(ValueError, match="FRONTEND_ORIGIN"):
        validate_production_settings(config)


def test_validate_production_settings_skips_oauth_when_unset():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET="super-secret-value",
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
    )

    validate_production_settings(config)


def test_validate_production_settings_rejects_partial_oauth_config():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET="super-secret-value",
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
        OAUTH_GOOGLE_CLIENT_ID="google-client-id",
        OAUTH_GOOGLE_CLIENT_SECRET="",
    )

    with pytest.raises(ValueError, match="OAUTH_GOOGLE_CLIENT_SECRET"):
        validate_production_settings(config)


def test_validate_production_settings_rejects_local_oauth_redirect_uri():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET="super-secret-value",
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
        OAUTH_GOOGLE_CLIENT_ID="google-client-id",
        OAUTH_GOOGLE_CLIENT_SECRET="google-client-secret",
        OAUTH_GOOGLE_REDIRECT_URI="http://localhost:8000/auth/callback/google",
    )

    with pytest.raises(ValueError, match="OAUTH_GOOGLE_REDIRECT_URI"):
        validate_production_settings(config)


def test_validate_production_settings_allows_complete_oauth_config():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET="super-secret-value",
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
        OAUTH_GOOGLE_CLIENT_ID="google-client-id",
        OAUTH_GOOGLE_CLIENT_SECRET="google-client-secret",
        OAUTH_GOOGLE_REDIRECT_URI="https://api.example.com/auth/callback/google",
    )

    validate_production_settings(config)
