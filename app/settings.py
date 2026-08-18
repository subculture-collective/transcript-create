import hmac
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse
from uuid import UUID

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]  # repo root (parent of 'app')

_ANALYTICS_HMAC_SECRET_PLACEHOLDERS = {
    "change-me-generate-a-different-secure-random-value",
    "your_analytics_hmac_secret_here",
    "your-independent-random-secret",
}

_SESSION_SECRET_PLACEHOLDERS = {
    "change-me",
    "change-me-generate-secure-random-value",
    "your-random-secret",
    "your_session_secret_here",
    "session_secret_placeholder_rejected",
}


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/transcripts"
    HF_TOKEN: str = ""
    WHISPER_MODEL: str = "large-v3"
    # Select backend: 'faster-whisper' (CTranslate2) or 'whisper' (OpenAI PyTorch)
    WHISPER_BACKEND: str = "faster-whisper"
    CHUNK_SECONDS: int = 900
    MAX_PARALLEL_JOBS: int = 1
    JOB_LEASE_SECONDS: int = 300
    MAX_JOB_ATTEMPTS: int = 3
    ROCM: bool = True
    # Force GPU usage for faster-whisper; if true, we will try GPU backends only and fail otherwise
    FORCE_GPU: bool = False
    # GPU device preference order: try in this sequence
    GPU_DEVICE_PREFERENCE: str = "cuda,hip"
    # Preferred compute types on GPU; will pick the first supported by the selected backend.
    # Keep plain int8 in the default order for older NVIDIA Pascal cards (for example GTX 1080),
    # which do not have a practical FP16 path for faster-whisper/CTranslate2.
    GPU_COMPUTE_TYPES: str = "float16,int8_float16,int8,bfloat16,float32"
    # Model fallbacks when forcing GPU to reduce VRAM: will try these in order if the primary model fails
    GPU_MODEL_FALLBACKS: str = "large-v3,medium,small,base,tiny"
    # Cleanup options: delete large media after successful processing
    CLEANUP_AFTER_PROCESS: bool = False
    CLEANUP_DELETE_RAW: bool = True
    CLEANUP_DELETE_WAV: bool = True
    CLEANUP_DELETE_CHUNKS: bool = True
    CLEANUP_DELETE_DIR_IF_EMPTY: bool = True
    # If a video stays in a non-terminal state for too long, requeue it
    RESCUE_STUCK_AFTER_SECONDS: int = 900

    # JavaScript runtime configuration for yt-dlp
    # yt-dlp requires a JS runtime (Deno/Node/Bun/QuickJS) to solve YouTube challenges
    JS_RUNTIME_CMD: str = "deno"  # Command for JS runtime (deno, node, bun, quickjs)
    JS_RUNTIME_ARGS: str = "run -A"  # Arguments for JS runtime (e.g., "run -A" for Deno)
    YTDLP_REQUIRE_JS_RUNTIME: bool = True  # Require JS runtime validation at startup
    YTDLP_JS_RUNTIME_HINT: str = ""  # Optional custom hint for installation instructions

    # PO Token configuration for YouTube
    # YouTube requires PO tokens for Player, GVS, and Subs in many flows
    PO_TOKEN_PLAYER: str = ""  # Manual player token injection
    PO_TOKEN_GVS: str = ""  # Manual GVS (GetVideoStream) token injection
    PO_TOKEN_SUBS: str = ""  # Manual Subs (Subtitles) token injection
    PO_TOKEN_PROVIDER_ENABLED: bool = False  # Enable external provider plugin
    PO_TOKEN_PROVIDER_URL: str = ""  # URL for external token provider service (e.g., http://localhost:8080/token)
    PO_TOKEN_PROVIDER_TIMEOUT: float = 5.0  # Timeout for provider requests in seconds
    PO_TOKEN_CACHE_TTL: int = 3600  # Token cache TTL in seconds (1 hour)
    PO_TOKEN_COOLDOWN_SECONDS: int = 60  # Cooldown period after token failure (1 minute)
    # Feature flags for controlled rollout
    PO_TOKEN_USE_FOR_AUDIO: bool = False  # Use PO tokens for audio downloads (Player/GVS); advanced fallback only
    PO_TOKEN_USE_FOR_CAPTIONS: bool = False  # Use PO tokens for caption fetching (Subs); advanced fallback only

    # yt-dlp client fallback strategy configuration
    # Client order for fallback (comma-separated): default, mweb, web_safari, ios, android, tv
    YTDLP_CLIENT_ORDER: str = "default,mweb,web_safari,ios,android,tv"
    # Enable/disable specific clients (comma-separated list of disabled clients)
    YTDLP_CLIENTS_DISABLED: str = ""
    # Path to cookies file for yt-dlp (Netscape format)
    YTDLP_COOKIES_PATH: str = ""
    # Number of retry attempts per client strategy
    YTDLP_TRIES_PER_CLIENT: int = 1
    # Sleep time between retries within same client (seconds)
    YTDLP_RETRY_SLEEP: float = 1.0
    # Additional extractor args (space-separated, applied to all clients)
    YTDLP_EXTRA_ARGS: str = ""

    # Retry and backoff configuration for YouTube requests
    YTDLP_MAX_RETRY_ATTEMPTS: int = 3  # Maximum retry attempts for transient failures
    YTDLP_BACKOFF_BASE_DELAY: float = 1.0  # Initial backoff delay in seconds
    YTDLP_BACKOFF_MAX_DELAY: float = 60.0  # Maximum backoff delay in seconds
    YTDLP_BACKOFF_JITTER: bool = True  # Add random jitter to backoff delays
    YTDLP_REQUEST_TIMEOUT: float = 120.0  # Timeout per request attempt in seconds
    YTDLP_RATE_LIMIT_COOLDOWN_SECONDS: int = 3600  # Pause YouTube caption ingest after rate-limit detection

    # Circuit breaker configuration for YouTube requests
    YTDLP_CIRCUIT_BREAKER_ENABLED: bool = True  # Enable circuit breaker
    YTDLP_CIRCUIT_BREAKER_THRESHOLD: int = 5  # Consecutive failures before opening
    YTDLP_CIRCUIT_BREAKER_COOLDOWN: float = 60.0  # Cooldown period in seconds
    YTDLP_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = 2  # Successes to close from half-open

    # Search backend toggle: 'postgres' (default) or 'opensearch'
    SEARCH_BACKEND: str = "postgres"
    # OpenSearch settings
    OPENSEARCH_URL: str = "http://localhost:9200"
    OPENSEARCH_INDEX_NATIVE: str = "segments"
    OPENSEARCH_INDEX_YOUTUBE: str = "youtube_segments"
    OPENSEARCH_USER: str = ""
    OPENSEARCH_PASSWORD: str = ""
    OPENSEARCH_VERIFY_SSL: bool = True
    OPENSEARCH_TLS_VERIFY: bool = True
    OPENSEARCH_CA_BUNDLE: str = ""

    # Redis caching configuration
    REDIS_URL: str = ""  # e.g., "redis://localhost:6379/0" or empty to disable caching
    ENABLE_CACHING: bool = True  # Enable/disable caching layer
    CACHE_DEFAULT_TTL: int = 300  # Default cache TTL in seconds (5 minutes)
    CACHE_VIDEO_TTL: int = 300  # Video metadata cache TTL (5 minutes)
    CACHE_TRANSCRIPT_TTL: int = 3600  # Transcript segments cache TTL (1 hour)
    CACHE_SEARCH_TTL: int = 600  # Search results cache TTL (10 minutes)

    # Frontend origin for CORS/redirects
    FRONTEND_ORIGIN: str = "http://localhost:5173"
    # Session and OAuth
    SESSION_SECRET: str = "change-me"
    # Dedicated key for deriving pseudonymous analytics subjects. Production
    # must set this independently from the login-session secret.
    ANALYTICS_HMAC_SECRET: str = ""
    OAUTH_GOOGLE_CLIENT_ID: str = ""
    OAUTH_GOOGLE_CLIENT_SECRET: str = ""
    # OAuth redirect URI - must match what's configured in Google Cloud Console
    # Default uses port 8000 (matches docker-compose API_HOST_PORT default)
    OAUTH_GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/callback/google"
    # Twitch OAuth
    OAUTH_TWITCH_CLIENT_ID: str = ""
    OAUTH_TWITCH_CLIENT_SECRET: str = ""
    # OAuth redirect URI - must match what's configured in Twitch Developer Console
    OAUTH_TWITCH_REDIRECT_URI: str = "http://localhost:8000/auth/callback/twitch"
    # Comma-separated immutable provider:subject identities for future canonical sign-in bootstrap.
    BOOTSTRAP_ADMIN_IDENTITIES: Annotated[frozenset[str], NoDecode] = frozenset()
    PRO_PLAN_NAME: str = "pro"
    # PDF export font: path to a .ttf file inside the container/host; falls back to system serif
    PDF_FONT_PATH: str = ""

    # Logging configuration
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # 'json' or 'text'
    # Optional Sentry integration for error tracking
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "development"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # Health check configuration
    HEALTH_CHECK_TIMEOUT: float = 5.0  # seconds
    HEALTH_CHECK_WORKER_STALE_SECONDS: int = 300  # 5 minutes
    HEALTH_CHECK_DISK_MIN_FREE_GB: float = 10.0  # minimum free disk space in GB
    HEALTH_CHECK_CRITICAL_COMPONENTS: str = "database"  # comma-separated: database,opensearch,storage,worker
    WORKDIR: str = "/data"  # data directory for storage health checks

    # Security configuration
    ENVIRONMENT: str = "development"  # development, staging, production
    ENABLE_RATE_LIMITING: bool = True  # Enable rate limiting middleware
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    FORWARDED_ALLOW_IPS: str = "127.0.0.1"
    SESSION_EXPIRE_HOURS: int = 24  # Session expiration in hours
    SESSION_REFRESH_THRESHOLD_HOURS: int = 12  # Refresh session if older than this
    API_KEY_EXPIRE_DAYS: int = 365  # Default API key expiration in days
    OAUTH_STATE_VALIDATION: bool = True  # Enable OAuth state parameter validation
    CORS_ALLOW_ORIGINS: str = ""  # Comma-separated allowed origins; empty = use FRONTEND_ORIGIN only
    MAX_LOGIN_ATTEMPTS: int = 5  # Max failed login attempts before rate limiting
    LOGIN_ATTEMPT_WINDOW_MINUTES: int = 15  # Time window for tracking login attempts
    # Job creation abuse controls
    JOB_CREATE_QUOTA_WINDOW_HOURS: int = 24  # Rolling quota window for user-created ingestion jobs
    JOB_CREATE_DAILY_LIMIT: int = 5  # Regular-user jobs per quota window
    JOB_CREATE_PRO_DAILY_LIMIT: int = 25  # Pro-user jobs per quota window
    JOB_CREATE_CHANNEL_DAILY_LIMIT: int = 1  # Regular-user channel jobs per quota window
    JOB_CREATE_PRO_CHANNEL_DAILY_LIMIT: int = 5  # Pro-user channel jobs per quota window
    JOB_CREATE_MAX_CHANNEL_VIDEOS: int = 250  # Maximum videos a channel job may expand into
    JOB_CREATE_MAX_BATCH_EXPECTED_JOBS: int = 100  # Upper bound for staged batch coordination fan-out
    JOB_CREATE_ADMIN_BYPASS_QUOTAS: bool = True  # Admins may create ingestion jobs without quota limits
    CHANNEL_SYNC_URLS: str = ""  # Comma-separated YouTube channel /videos URLs for recurring discovery
    CHANNEL_SYNC_INTERVAL_SECONDS: int = Field(default=6 * 60 * 60, ge=60, le=24 * 60 * 60)

    # Backup and disaster recovery configuration
    BACKUP_DIR: str = "/backups"  # Root directory for all backups
    BACKUP_ENCRYPT: bool = False  # Enable GPG encryption for backups
    BACKUP_GPG_RECIPIENT: str = ""  # GPG recipient email for backup encryption
    BACKUP_RETENTION_DAILY: int = 7  # Days to keep daily backups
    BACKUP_RETENTION_WEEKLY: int = 4  # Weeks to keep weekly backups (28 days)
    BACKUP_RETENTION_MONTHLY: int = 12  # Months to keep monthly backups (360 days)
    BACKUP_S3_BUCKET: str = ""  # S3 bucket for remote backup storage
    BACKUP_GCS_BUCKET: str = ""  # GCS bucket for remote backup storage
    BACKUP_AZURE_CONTAINER: str = ""  # Azure container for remote backup storage
    WAL_ARCHIVE_DIR: str = "/backups/wal_archive"  # PostgreSQL WAL archive directory
    MEDIA_BACKUP_DIR: str = "/backups/media"  # Media files backup directory
    MEDIA_RETENTION_DAYS: int = 30  # Days to keep media backups

    # Metrics and monitoring configuration
    ENABLE_METRICS: bool = True  # Enable Prometheus metrics collection

    # Advanced transcription features
    # Language detection (uses Whisper's built-in capability)
    WHISPER_LANGUAGE: str = "en"  # HasanAbi archive audio is English; avoids music-driven language misdetection
    # Quality presets: fast, balanced, accurate
    WHISPER_QUALITY_PRESET: str = "balanced"  # Default quality preset
    WHISPER_BEAM_SIZE: int = 5  # Beam size for decoding (1-10, higher = more accurate but slower)
    WHISPER_TEMPERATURE: float = 0.0  # Temperature for sampling (0.0-1.0, 0.0 = greedy)
    WHISPER_VAD_FILTER: bool = True  # Skip music/silence before decoding with faster-whisper
    WHISPER_WORD_TIMESTAMPS: bool = True  # Extract word-level timestamps
    WHISPER_INITIAL_PROMPT: str = (
        "What's going on, everybody? I hope everyone's having a fantastic evening, afternoon, pre-noon, "
        "no matter where you are in the world. I'm Hasan Piker, and this is the HasanAbi broadcast. "
        "All the boys, girls and Enbies. Hasan HasanAbi Piker. Oliver Larkin. Melat Kiros."
    )
    # Speaker diarization assigns anonymous labels like "Speaker 1"/"Speaker 2".
    # It does not identify real people without a separate voice-enrollment system.
    ENABLE_DIARIZATION: bool = False
    # Run inside transcription worker; false lets separate diarization worker handle it.
    DIARIZATION_INLINE: bool = False
    DIARIZATION_DEVICE: str = "cpu"  # 'cpu', 'cuda', or 'auto'. Production GTX 1080 diarization is CPU-only.
    DIARIZATION_MODEL: str = "pyannote/speaker-diarization-community-1"
    DIARIZATION_FALLBACK_MODEL: str = "pyannote/speaker-diarization"
    DIARIZATION_POLL_INTERVAL: int = 10
    DIARIZATION_RUNNING_TIMEOUT_MINUTES: int = 5
    # Bound pyannote memory use and recycle its process between jobs.
    DIARIZATION_MAX_DURATION_SECONDS: int = 7200
    DIARIZATION_MAX_JOBS_PER_PROCESS: int = 1
    # A bounded standalone run may mutate only these explicit video UUIDs.
    # Do not validate the programmatic empty default as if it came from the
    # environment. Explicit external values must remain strict strings.
    DIARIZATION_ALLOWED_VIDEO_IDS: Annotated[frozenset[UUID], NoDecode] = Field(
        default_factory=frozenset, validate_default=False
    )
    # Retained for compatibility with inline callers; the standalone worker always
    # requires an allow-list regardless of this setting.
    DIARIZATION_REQUIRE_ALLOWLIST: bool = True
    DIARIZATION_EXIT_WHEN_IDLE: bool = False
    # A production canary is preclaimed by the operator helper. Its UUID is a
    # durable fencing token, never a queue identifier supplied implicitly.
    DIARIZATION_CANARY_MODE: bool = False
    DIARIZATION_CANARY_TOKEN: UUID | None = None
    # Strict mode is used by the production one-off worker: no fallback, download,
    # decode, or device-placement failure may be hidden.
    DIARIZATION_STRICT: bool = False
    # Custom vocabulary post-processing
    ENABLE_CUSTOM_VOCABULARY: bool = True  # Apply custom vocabulary corrections
    # Translation support
    ENABLE_TRANSLATION: bool = False  # Enable translation features
    TRANSLATION_PROVIDER: str = "libretranslate"  # 'google', 'deepl', 'libretranslate'
    LIBRETRANSLATE_URL: str = "https://libretranslate.com"  # LibreTranslate API URL
    LIBRETRANSLATE_API_KEY: str = ""  # Optional API key for LibreTranslate
    GOOGLE_TRANSLATE_API_KEY: str = ""  # Google Cloud Translation API key
    DEEPL_API_KEY: str = ""  # DeepL API key

    # Model-backed archive enrichment. Disabled until explicitly enabled; new
    # model output remains a review candidate rather than public metadata.
    ARCHIVE_ENRICHMENT_ENABLED: bool = False
    ARCHIVE_ENRICHMENT_PROVIDER: str = "openrouter"
    ARCHIVE_ENRICHMENT_MODEL: str = "deepseek/deepseek-v4-pro"
    OPENROUTER_API_KEY: str = ""
    ARCHIVE_ENRICHMENT_MAX_WINDOW_MINUTES: int = Field(default=90, ge=30, le=120)
    ARCHIVE_ENRICHMENT_TIMEOUT_SECONDS: float = Field(default=300.0, ge=30.0, le=900.0)
    ARCHIVE_ENRICHMENT_MAX_COST_USD_PER_VIDEO: float = Field(default=1.0, gt=0.0, le=10.0)
    ARCHIVE_ENRICHMENT_PUBLISH: bool = False

    # Transcript cleanup configuration
    CLEANUP_ENABLED: bool = True  # Enable transcript cleanup features
    # Text normalization
    CLEANUP_NORMALIZE_UNICODE: bool = True  # Apply Unicode NFC normalization
    CLEANUP_NORMALIZE_WHITESPACE: bool = True  # Normalize whitespace characters
    CLEANUP_REMOVE_SPECIAL_TOKENS: bool = True  # Remove [MUSIC], [APPLAUSE], etc.
    CLEANUP_PRESERVE_SOUND_EVENTS: bool = False  # Keep sound event markers when cleaning
    # Punctuation and capitalization
    CLEANUP_PUNCTUATION_MODE: str = "rule-based"  # 'none', 'rule-based', 'model-based'
    CLEANUP_PUNCTUATION_MODEL: str = ""  # HuggingFace model name for model-based punctuation
    CLEANUP_ADD_SENTENCE_PUNCTUATION: bool = True  # Add terminal punctuation to segments
    CLEANUP_ADD_INTERNAL_PUNCTUATION: bool = False  # Add commas and internal punctuation
    CLEANUP_CAPITALIZE_SENTENCES: bool = True  # Capitalize sentence-initial letters
    CLEANUP_FIX_ALL_CAPS: bool = True  # Fix inappropriate all-caps text
    # De-filler configuration
    CLEANUP_REMOVE_FILLERS: bool = True  # Enable filler word removal
    CLEANUP_FILLER_LEVEL: int = 1  # 0=disabled, 1=conservative, 2=moderate, 3=aggressive
    # Segmentation
    CLEANUP_SEGMENT_BY_SENTENCES: bool = True  # Split segments on sentence boundaries
    CLEANUP_MERGE_SHORT_SEGMENTS: bool = True  # Merge segments with small gaps
    CLEANUP_MIN_SEGMENT_LENGTH_MS: int = 1000  # Minimum segment duration in milliseconds
    CLEANUP_MAX_GAP_FOR_MERGE_MS: int = 500  # Maximum gap for merging segments
    CLEANUP_SPEAKER_FORMAT: str = "structured"  # 'inline', 'dialogue', 'structured'
    # Advanced cleanup features
    CLEANUP_DETECT_HALLUCINATIONS: bool = True  # Detect and mark Whisper hallucinations
    CLEANUP_LANGUAGE_SPECIFIC_RULES: bool = True  # Apply language-specific cleanup rules

    # Resolve .env relative to the repository root so scripts work from any CWD.
    # Allow extra env vars (ignore) so container-only vars in .env don't break settings.
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("BOOTSTRAP_ADMIN_IDENTITIES", mode="before")
    @classmethod
    def parse_bootstrap_admin_identities(cls, value: object) -> frozenset[str]:
        if value is None or value == "":
            return frozenset()
        if isinstance(value, str):
            entries: tuple[object, ...] = tuple(value.split(","))
        elif isinstance(value, (frozenset, set, tuple, list)):
            entries = tuple(value)
        else:
            raise ValueError("BOOTSTRAP_ADMIN_IDENTITIES must be a comma-separated list of provider:subject entries")

        identities = set()
        for entry in entries:
            if not isinstance(entry, str):
                raise ValueError("BOOTSTRAP_ADMIN_IDENTITIES entries must use provider:subject syntax")
            identity = entry.strip()
            if identity.count(":") != 1:
                raise ValueError("BOOTSTRAP_ADMIN_IDENTITIES entries must use provider:subject syntax")
            provider, subject = (part.strip() for part in identity.split(":", 1))
            if not provider or not subject:
                raise ValueError("BOOTSTRAP_ADMIN_IDENTITIES entries must use provider:subject syntax")
            identities.add(f"{provider}:{subject}")
        return frozenset(identities)

    @field_validator("DIARIZATION_ALLOWED_VIDEO_IDS", mode="before")
    @classmethod
    def parse_diarization_allowed_video_ids(cls, value: object) -> frozenset[UUID]:
        if value == "":
            return frozenset()
        if not isinstance(value, str):
            raise ValueError("DIARIZATION_ALLOWED_VIDEO_IDS must be a comma-separated UUID list")
        entries = value.split(",")
        if not entries or any(not entry or entry != entry.strip() for entry in entries):
            raise ValueError("DIARIZATION_ALLOWED_VIDEO_IDS must be a comma-separated UUID list")
        try:
            parsed_ids = [UUID(entry) for entry in entries]
        except (TypeError, ValueError) as error:
            raise ValueError("DIARIZATION_ALLOWED_VIDEO_IDS must be a comma-separated UUID list") from error
        if any(str(parsed) != entry for parsed, entry in zip(parsed_ids, entries, strict=True)):
            raise ValueError("DIARIZATION_ALLOWED_VIDEO_IDS must use canonical lowercase UUID strings")
        ids = frozenset(parsed_ids)
        if len(ids) != len(entries):
            raise ValueError("DIARIZATION_ALLOWED_VIDEO_IDS must not contain duplicate UUIDs")
        if len(ids) > 5:
            raise ValueError("DIARIZATION_ALLOWED_VIDEO_IDS may contain at most 5 UUIDs")
        return ids


def _has_value(value: str | None) -> bool:
    return bool((value or "").strip())


def _parse_db_password(database_url: str) -> str:
    parsed = urlparse(database_url)
    return parsed.password or ""


def _is_local_origin(origin: str) -> bool:
    parsed = urlparse(origin)
    return parsed.hostname in {"localhost", "127.0.0.1", "::1"}


def _is_valid_origin(origin: str) -> bool:
    try:
        parsed = urlparse(origin)
        _ = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and not _is_local_origin(origin)
        and not parsed.username
        and not parsed.password
        and "*" not in origin
        and not any(character.isspace() for character in origin)
        and parsed.path in {"", "/"}
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def _is_valid_production_redirect_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    return bool(parsed.scheme == "https" and parsed.hostname and not _is_local_origin(uri))


def _is_placeholder_redirect_uri(uri: str) -> bool:
    """Reject repository examples and deployment-required callback placeholders."""
    parsed = urlparse(uri.strip())
    value = uri.strip().casefold()
    return (
        not value
        or "required_oauth_" in value
        or "your-" in value
        or (parsed.hostname or "").casefold().endswith(".example.com")
        or (parsed.hostname or "").casefold() == "example.com"
    )


def validate_worker_production_settings(config: Settings | None = None) -> None:
    """Fail closed on production settings used by the worker process."""

    cfg = config or settings
    if (cfg.ENVIRONMENT or "").strip().lower() != "production":
        return

    errors: list[str] = []

    if urlparse(cfg.OPENSEARCH_URL).scheme == "https" and (
        not cfg.OPENSEARCH_VERIFY_SSL or not cfg.OPENSEARCH_TLS_VERIFY
    ):
        errors.append(
            "OPENSEARCH_VERIFY_SSL and OPENSEARCH_TLS_VERIFY must remain enabled for production HTTPS endpoints."
        )

    db_password = _parse_db_password(cfg.DATABASE_URL)
    if not db_password or db_password in {"postgres", "change-me", "change-me-in-production"}:
        errors.append("DATABASE_URL must use a non-default database password in production.")

    if errors:
        raise ValueError("Production worker configuration validation failed:\n- " + "\n- ".join(errors))


def validate_production_settings(config: Settings | None = None) -> None:
    """Fail closed when production settings keep unsafe defaults."""

    cfg = config or settings
    if (cfg.ENVIRONMENT or "").strip().lower() != "production":
        return

    errors: list[str] = []

    if not cfg.OAUTH_STATE_VALIDATION:
        errors.append("OAUTH_STATE_VALIDATION cannot be disabled in production.")

    session_secret = cfg.SESSION_SECRET.strip()
    if not _has_value(session_secret):
        errors.append("SESSION_SECRET must be a generated secret in production.")
    elif session_secret.casefold() in _SESSION_SECRET_PLACEHOLDERS:
        errors.append("SESSION_SECRET must not use a documented placeholder in production.")
    elif len(session_secret.encode("utf-8")) < 32:
        errors.append("SESSION_SECRET must contain at least 32 bytes in production.")

    analytics_hmac_secret = cfg.ANALYTICS_HMAC_SECRET.strip()
    if not _has_value(analytics_hmac_secret):
        errors.append("ANALYTICS_HMAC_SECRET must be a dedicated generated secret in production.")
    elif analytics_hmac_secret.casefold() in _ANALYTICS_HMAC_SECRET_PLACEHOLDERS:
        errors.append("ANALYTICS_HMAC_SECRET must not use a documented placeholder in production.")
    elif len(analytics_hmac_secret.encode("utf-8")) < 32:
        errors.append("ANALYTICS_HMAC_SECRET must contain at least 32 bytes in production.")
    elif hmac.compare_digest(
        analytics_hmac_secret.encode("utf-8"),
        cfg.SESSION_SECRET.strip().encode("utf-8"),
    ):
        errors.append("ANALYTICS_HMAC_SECRET must differ from SESSION_SECRET in production.")

    if urlparse(cfg.OPENSEARCH_URL).scheme == "https" and (
        not cfg.OPENSEARCH_VERIFY_SSL or not cfg.OPENSEARCH_TLS_VERIFY
    ):
        errors.append(
            "OPENSEARCH_VERIFY_SSL and OPENSEARCH_TLS_VERIFY must remain enabled for production HTTPS endpoints."
        )

    if cfg.ENABLE_RATE_LIMITING and not _has_value(cfg.REDIS_URL):
        errors.append("REDIS_URL must be set when production rate limiting is enabled.")
    if not _has_value(cfg.FORWARDED_ALLOW_IPS) or cfg.FORWARDED_ALLOW_IPS.strip() == "*":
        errors.append("FORWARDED_ALLOW_IPS must restrict forwarded headers to trusted production proxies.")

    db_password = _parse_db_password(cfg.DATABASE_URL)
    if not db_password or db_password in {"postgres", "change-me", "change-me-in-production"}:
        errors.append("DATABASE_URL must use a non-default database password in production.")

    if cfg.ARCHIVE_ENRICHMENT_ENABLED:
        if cfg.ARCHIVE_ENRICHMENT_PROVIDER != "openrouter":
            errors.append("ARCHIVE_ENRICHMENT_PROVIDER must be openrouter when archive enrichment is enabled.")
        if not _has_value(cfg.OPENROUTER_API_KEY):
            errors.append("OPENROUTER_API_KEY must be set when archive enrichment is enabled.")
        if not _has_value(cfg.ARCHIVE_ENRICHMENT_MODEL):
            errors.append("ARCHIVE_ENRICHMENT_MODEL must be pinned when archive enrichment is enabled.")
        if cfg.ARCHIVE_ENRICHMENT_PUBLISH:
            errors.append("ARCHIVE_ENRICHMENT_PUBLISH must remain disabled until the editorial release gate passes.")

    if (
        not _has_value(cfg.FRONTEND_ORIGIN)
        or cfg.FRONTEND_ORIGIN.strip() == "*"
        or not _is_valid_origin(cfg.FRONTEND_ORIGIN.strip())
    ):
        errors.append("FRONTEND_ORIGIN must be a production https origin without path/query/fragment.")

    cors_origins = [origin.strip() for origin in (cfg.CORS_ALLOW_ORIGINS or "").split(",") if origin.strip()]
    if any(
        origin == "*" or "*" in origin or _is_local_origin(origin) or not _is_valid_origin(origin)
        for origin in cors_origins
    ):
        errors.append("CORS_ALLOW_ORIGINS must contain only exact production https origins without wildcards or paths.")

    oauth_providers = {
        "google": (
            cfg.OAUTH_GOOGLE_CLIENT_ID,
            cfg.OAUTH_GOOGLE_CLIENT_SECRET,
            cfg.OAUTH_GOOGLE_REDIRECT_URI,
        ),
        "twitch": (
            cfg.OAUTH_TWITCH_CLIENT_ID,
            cfg.OAUTH_TWITCH_CLIENT_SECRET,
            cfg.OAUTH_TWITCH_REDIRECT_URI,
        ),
    }
    for provider, (client_id, client_secret, redirect_uri) in oauth_providers.items():
        if _has_value(client_id) or _has_value(client_secret):
            if not _has_value(client_id):
                errors.append(f"OAUTH_{provider.upper()}_CLIENT_ID must be set when {provider} OAuth is enabled.")
            if not _has_value(client_secret):
                errors.append(f"OAUTH_{provider.upper()}_CLIENT_SECRET must be set when {provider} OAuth is enabled.")
            if (
                not _has_value(redirect_uri)
                or _is_placeholder_redirect_uri(redirect_uri)
                or not _is_valid_production_redirect_uri(redirect_uri.strip())
            ):
                errors.append(
                    f"OAUTH_{provider.upper()}_REDIRECT_URI must be a non-placeholder https production "
                    f"callback URI when {provider} OAuth is enabled."
                )

    if errors:
        raise ValueError("Production configuration validation failed:\n- " + "\n- ".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
