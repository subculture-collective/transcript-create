"""Tests for settings and configuration."""

import os
import secrets
import uuid

import pytest

ANALYTICS_SECRET = "analytics-secret-with-at-least-32-bytes"
SESSION_SECRET = "session-secret-with-at-least-32-bytes"


def _isolated_settings(**overrides):
    from app.settings import Settings

    overrides.setdefault("ANALYTICS_HMAC_SECRET", ANALYTICS_SECRET)
    overrides.setdefault("REDIS_URL", "redis://redis:6379/0")
    overrides.setdefault("FORWARDED_ALLOW_IPS", "172.20.0.250")
    return Settings(_env_file=None, **overrides)


def test_settings_load():
    """Test that settings can be loaded."""
    from app.settings import settings

    assert settings is not None
    assert hasattr(settings, "DATABASE_URL")


@pytest.mark.parametrize("provider", ["", "alibaba", "deepinfra/fp8"])
def test_enrichment_provider_routing_configuration(provider):
    assert (
        _isolated_settings(
            ARCHIVE_ENRICHMENT_OPENROUTER_PROVIDER_ONLY=provider
        ).ARCHIVE_ENRICHMENT_OPENROUTER_PROVIDER_ONLY
        == provider
    )


def test_enrichment_routing_defaults_to_openrouter(monkeypatch):
    monkeypatch.delenv("ARCHIVE_ENRICHMENT_OPENROUTER_PROVIDER_ONLY", raising=False)
    assert _isolated_settings().ARCHIVE_ENRICHMENT_OPENROUTER_PROVIDER_ONLY == ""


@pytest.mark.parametrize("provider", [" ", "alibaba,deepinfra", "ALIBABA", "*"])
def test_enrichment_provider_rejects_ambiguous_pins(provider):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _isolated_settings(ARCHIVE_ENRICHMENT_OPENROUTER_PROVIDER_ONLY=provider)


def test_bootstrap_admin_identities_are_parsed_as_immutable_entries():
    config = _isolated_settings(BOOTSTRAP_ADMIN_IDENTITIES="google:123, twitch:456,google:123")

    assert config.BOOTSTRAP_ADMIN_IDENTITIES == frozenset({"google:123", "twitch:456"})


def test_bootstrap_admin_identities_default_constructs_without_env(monkeypatch):
    from app.settings import Settings

    monkeypatch.delenv("BOOTSTRAP_ADMIN_IDENTITIES", raising=False)

    config = Settings(_env_file=None)

    assert config.BOOTSTRAP_ADMIN_IDENTITIES == frozenset()


@pytest.mark.parametrize("value", ["google", ":subject", "provider:", "google:one:two", "google:one,,twitch:two"])
def test_bootstrap_admin_identities_reject_malformed_entries(value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="BOOTSTRAP_ADMIN_IDENTITIES"):
        _isolated_settings(BOOTSTRAP_ADMIN_IDENTITIES=value)


def test_bootstrap_admin_identities_allow_empty_config():
    assert _isolated_settings(BOOTSTRAP_ADMIN_IDENTITIES="").BOOTSTRAP_ADMIN_IDENTITIES == frozenset()


def test_diarization_allowlist_parses_strict_uuid_list():
    first, second = uuid.uuid4(), uuid.uuid4()
    config = _isolated_settings(DIARIZATION_ALLOWED_VIDEO_IDS=f"{first},{second}")
    assert config.DIARIZATION_ALLOWED_VIDEO_IDS == frozenset({first, second})


def test_diarization_allowlist_default_constructs_without_env(monkeypatch):
    from app.settings import Settings

    monkeypatch.delenv("DIARIZATION_ALLOWED_VIDEO_IDS", raising=False)

    assert Settings(_env_file=None).DIARIZATION_ALLOWED_VIDEO_IDS == frozenset()


@pytest.mark.parametrize("value", ["not-a-uuid", " ", "a, b", ",", "00000000-0000-0000-0000-000000000000,"])
def test_diarization_allowlist_rejects_malformed_entries(value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="DIARIZATION_ALLOWED_VIDEO_IDS"):
        _isolated_settings(DIARIZATION_ALLOWED_VIDEO_IDS=value)


@pytest.mark.parametrize("value", ["A0000000-0000-4000-8000-000000000000", "a0000000000040008000000000000000"])
def test_diarization_allowlist_rejects_noncanonical_uuid_strings(value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="canonical lowercase"):
        _isolated_settings(DIARIZATION_ALLOWED_VIDEO_IDS=value)


def test_diarization_allowlist_rejects_more_than_five_ids():
    value = ",".join(str(uuid.uuid4()) for _ in range(6))
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="at most 5"):
        _isolated_settings(DIARIZATION_ALLOWED_VIDEO_IDS=value)


@pytest.mark.parametrize("value", [frozenset(), [], {uuid.uuid4()}])
def test_diarization_allowlist_rejects_non_string_external_values(value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="DIARIZATION_ALLOWED_VIDEO_IDS"):
        _isolated_settings(DIARIZATION_ALLOWED_VIDEO_IDS=value)


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
        SESSION_SECRET=SESSION_SECRET,
        ANALYTICS_HMAC_SECRET=ANALYTICS_SECRET,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
    )

    validate_production_settings(config)


def test_donation_payment_link_defaults_to_disabled():
    config = _isolated_settings()

    assert config.DONATION_PAYMENT_LINK_URL == ""


@pytest.mark.parametrize("hostname", ["buy.stripe.com", "donate.stripe.com"])
def test_donation_payment_link_accepts_stripe_https_url(hostname):
    payment_url = f"https://{hostname}/test_example"
    config = _isolated_settings(DONATION_PAYMENT_LINK_URL=payment_url)

    assert config.DONATION_PAYMENT_LINK_URL == payment_url


@pytest.mark.parametrize(
    "value",
    [
        "http://buy.stripe.com/example",
        "https://example.com/pretending-to-be-stripe",
        "https://donate.stripe.com.evil.example/example",
        "https://buy.stripe.com",
        "https://user:password@buy.stripe.com/example",
        "https://buy.stripe.com/example#fragment",
    ],
)
def test_donation_payment_link_rejects_unsafe_urls(value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="DONATION_PAYMENT_LINK_URL"):
        _isolated_settings(DONATION_PAYMENT_LINK_URL=value)


def test_archive_enrichment_defaults_to_disabled_v4_pro_candidates():
    config = _isolated_settings()

    assert config.WHISPER_LANGUAGE == "en"
    assert config.WHISPER_VAD_FILTER is True
    assert config.WHISPER_INITIAL_PROMPT == ""
    assert config.ARCHIVE_ENRICHMENT_ENABLED is False
    assert config.ARCHIVE_ENRICHMENT_MODEL == "deepseek/deepseek-v4-pro"
    assert config.ARCHIVE_ENRICHMENT_MAX_WINDOW_MINUTES == 90
    assert config.ARCHIVE_ENRICHMENT_PUBLISH is False
    assert config.ARCHIVE_ENRICHMENT_QUEUE_POLL_SECONDS == 300
    assert config.ARCHIVE_ENRICHMENT_QUEUE_FAILURE_COOLDOWN_SECONDS == 86400
    assert config.ARCHIVE_ENRICHMENT_QUEUE_CREDIT_COOLDOWN_SECONDS == 3600
    assert config.ARCHIVE_ENRICHMENT_QUEUE_MAX_ATTEMPTS_PER_24H == 20
    assert config.ARCHIVE_ENRICHMENT_QUEUE_MAX_COST_USD_PER_24H == 5.0
    assert config.ARCHIVE_ENRICHMENT_QUEUE_FAILURE_WINDOW == 20
    assert config.ARCHIVE_ENRICHMENT_QUEUE_MAX_FAILURE_RATE == 0.25


def test_production_archive_enrichment_requires_openrouter_key():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=SESSION_SECRET,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
        ARCHIVE_ENRICHMENT_ENABLED=True,
        OPENROUTER_API_KEY="",
    )

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        validate_production_settings(config)


def test_validate_worker_production_settings_allows_missing_web_auth_settings():
    from app.settings import validate_worker_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET="",
        ANALYTICS_HMAC_SECRET="",
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="",
        OAUTH_STATE_VALIDATION=False,
        CORS_ALLOW_ORIGINS="*",
        OAUTH_GOOGLE_CLIENT_ID="google-client-id",
        OAUTH_GOOGLE_CLIENT_SECRET="",
    )

    validate_worker_production_settings(config)


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg://postgres:postgres@db/transcripts",
        "postgresql+psycopg://postgres:change-me-in-production@db/transcripts",
    ],
)
def test_validate_worker_production_settings_rejects_weak_database_password(database_url):
    from app.settings import validate_worker_production_settings

    config = _isolated_settings(ENVIRONMENT="production", DATABASE_URL=database_url)

    with pytest.raises(ValueError, match="DATABASE_URL"):
        validate_worker_production_settings(config)


def test_validate_worker_production_settings_rejects_disabled_opensearch_tls_verification():
    from app.settings import validate_worker_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        OPENSEARCH_URL="https://opensearch.example.com",
        OPENSEARCH_VERIFY_SSL=False,
    )

    with pytest.raises(ValueError, match="OPENSEARCH_VERIFY_SSL"):
        validate_worker_production_settings(config)


def test_validate_worker_production_settings_allows_non_production_defaults():
    from app.settings import validate_worker_production_settings

    validate_worker_production_settings(_isolated_settings(ENVIRONMENT="development"))


def test_validate_production_settings_requires_dedicated_analytics_secret():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=SESSION_SECRET,
        ANALYTICS_HMAC_SECRET="",
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
    )

    with pytest.raises(ValueError, match="ANALYTICS_HMAC_SECRET"):
        validate_production_settings(config)


def test_validate_production_settings_rejects_reused_session_secret_for_analytics():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET="reused-secret-value-with-at-least-32-bytes",
        ANALYTICS_HMAC_SECRET="reused-secret-value-with-at-least-32-bytes",
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
    )

    with pytest.raises(ValueError, match="must differ from SESSION_SECRET"):
        validate_production_settings(config)


@pytest.mark.parametrize(
    "placeholder",
    [
        "change-me-generate-a-different-secure-random-value",
        "YOUR_ANALYTICS_HMAC_SECRET_HERE",
        "your-independent-random-secret",
    ],
)
def test_validate_production_settings_rejects_documented_analytics_placeholder(placeholder):
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=SESSION_SECRET,
        ANALYTICS_HMAC_SECRET=placeholder,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
    )

    with pytest.raises(ValueError, match="placeholder"):
        validate_production_settings(config)


@pytest.mark.parametrize(
    "placeholder",
    [
        "change-me",
        "change-me-generate-secure-random-value",
        "your-random-secret",
        "YOUR_SESSION_SECRET_HERE",
        "SESSION_SECRET_PLACEHOLDER_REJECTED",
    ],
)
def test_validate_production_settings_rejects_documented_session_secret_placeholder(placeholder):
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=placeholder,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
    )

    with pytest.raises(ValueError, match="SESSION_SECRET must not use a documented placeholder"):
        validate_production_settings(config)


def test_validate_production_settings_rejects_short_session_secret():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET="a" * 31,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
    )

    with pytest.raises(ValueError, match="SESSION_SECRET must contain at least 32 bytes"):
        validate_production_settings(config)


def test_validate_production_settings_allows_generated_session_secret():
    from app.settings import validate_production_settings

    generated_secret = secrets.token_urlsafe(32)
    assert len(generated_secret.encode("utf-8")) >= 32
    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=generated_secret,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
    )

    validate_production_settings(config)


def test_validate_production_settings_requires_32_byte_analytics_secret():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=SESSION_SECRET,
        ANALYTICS_HMAC_SECRET="a" * 31,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
    )

    with pytest.raises(ValueError, match="at least 32 bytes"):
        validate_production_settings(config)


def test_validate_production_settings_allows_exactly_32_utf8_bytes():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=SESSION_SECRET,
        ANALYTICS_HMAC_SECRET="é" * 16,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
    )

    validate_production_settings(config)


def test_validate_production_settings_rejects_disabled_opensearch_tls_verification():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=SESSION_SECRET,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
        OPENSEARCH_URL="https://opensearch.example.com",
        OPENSEARCH_VERIFY_SSL=False,
    )

    with pytest.raises(ValueError, match="OPENSEARCH_VERIFY_SSL"):
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
        SESSION_SECRET=SESSION_SECRET,
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
        SESSION_SECRET=SESSION_SECRET,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
        CORS_ALLOW_ORIGINS="https://app.example.com, *",
    )

    with pytest.raises(ValueError, match="CORS_ALLOW_ORIGINS"):
        validate_production_settings(config)


@pytest.mark.parametrize(
    "cors_origins",
    [
        "http://app.example.com",
        "null",
        "https://app.example.com/path",
        "https://app.example.com?next=/",
        "https://app.example.com#section",
        "https://*.example.com",
        "https://app*.example.com",
        "not-an-origin",
    ],
)
def test_validate_production_settings_rejects_invalid_cors_origins(cors_origins):
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=SESSION_SECRET,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
        CORS_ALLOW_ORIGINS=cors_origins,
    )

    with pytest.raises(ValueError, match="CORS_ALLOW_ORIGINS"):
        validate_production_settings(config)


@pytest.mark.parametrize(
    "cors_origins",
    ["", "https://app.example.com", "https://app.example.com, https://admin.example.com"],
)
def test_validate_production_settings_allows_exact_https_cors_origins(cors_origins):
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=SESSION_SECRET,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
        CORS_ALLOW_ORIGINS=cors_origins,
    )

    validate_production_settings(config)


def test_validate_production_settings_rejects_frontend_origin_with_path():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=SESSION_SECRET,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com/path",
    )

    with pytest.raises(ValueError, match="FRONTEND_ORIGIN"):
        validate_production_settings(config)


def test_validate_production_settings_rejects_http_frontend_origin():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=SESSION_SECRET,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="http://app.example.com",
    )

    with pytest.raises(ValueError, match="FRONTEND_ORIGIN"):
        validate_production_settings(config)


def test_validate_production_settings_skips_oauth_when_unset():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=SESSION_SECRET,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
    )

    validate_production_settings(config)


def test_validate_production_settings_rejects_partial_oauth_config():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=SESSION_SECRET,
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
        SESSION_SECRET=SESSION_SECRET,
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
        SESSION_SECRET=SESSION_SECRET,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
        OAUTH_GOOGLE_CLIENT_ID="google-client-id",
        OAUTH_GOOGLE_CLIENT_SECRET="google-client-secret",
        OAUTH_GOOGLE_REDIRECT_URI="https://api.hasanara.test/auth/callback/google",
    )

    validate_production_settings(config)


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "REQUIRED_OAUTH_GOOGLE_REDIRECT_URI",
        "https://api.example.com/auth/callback/google",
        "https://your-api-domain.com/auth/callback/google",
    ],
)
def test_validate_production_settings_rejects_placeholder_oauth_redirect_uri(redirect_uri):
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=SESSION_SECRET,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.hasanara.test",
        OAUTH_GOOGLE_CLIENT_ID="google-client-id",
        OAUTH_GOOGLE_CLIENT_SECRET="google-client-secret",
        OAUTH_GOOGLE_REDIRECT_URI=redirect_uri,
    )

    with pytest.raises(ValueError, match="non-placeholder https production callback"):
        validate_production_settings(config)


def test_validate_production_settings_rejects_disabled_oauth_state_validation():
    from app.settings import validate_production_settings

    config = _isolated_settings(
        ENVIRONMENT="production",
        SESSION_SECRET=SESSION_SECRET,
        ANALYTICS_HMAC_SECRET=ANALYTICS_SECRET,
        DATABASE_URL="postgresql+psycopg://postgres:strong-password@db/transcripts",
        FRONTEND_ORIGIN="https://app.example.com",
        OAUTH_GOOGLE_CLIENT_ID="google-client-id",
        OAUTH_GOOGLE_CLIENT_SECRET="google-client-secret",
        OAUTH_GOOGLE_REDIRECT_URI="https://api.hasanara.test/auth/callback/google",
        OAUTH_STATE_VALIDATION=False,
    )

    with pytest.raises(ValueError, match="OAUTH_STATE_VALIDATION cannot be disabled in production"):
        validate_production_settings(config)
