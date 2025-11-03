from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]  # repo root (parent of 'app')


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/transcripts"
    HF_TOKEN: str = ""
    WHISPER_MODEL: str = "large-v3"
    # Select backend: 'faster-whisper' (CTranslate2) or 'whisper' (OpenAI PyTorch)
    WHISPER_BACKEND: str = "faster-whisper"
    CHUNK_SECONDS: int = 900
    MAX_PARALLEL_JOBS: int = 1
    ROCM: bool = True
    # Force GPU usage for faster-whisper; if true, we will try GPU backends only and fail otherwise
    FORCE_GPU: bool = False
    # GPU device preference order: try in this sequence
    GPU_DEVICE_PREFERENCE: str = "cuda,hip"
    # Preferred compute types on GPU; will pick the first supported by the selected backend
    GPU_COMPUTE_TYPES: str = "float16,int8_float16,bfloat16,float32"
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

    # Search backend toggle: 'postgres' (default) or 'opensearch'
    SEARCH_BACKEND: str = "postgres"
    # OpenSearch settings
    OPENSEARCH_URL: str = "http://localhost:9200"
    OPENSEARCH_INDEX_NATIVE: str = "segments"
    OPENSEARCH_INDEX_YOUTUBE: str = "youtube_segments"
    OPENSEARCH_USER: str = ""
    OPENSEARCH_PASSWORD: str = ""

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
    # Comma-separated admin emails for admin dashboard access
    ADMIN_EMAILS: str = ""
    # Monetization / quotas
    FREE_DAILY_SEARCH_LIMIT: int = 5
    PRO_PLAN_NAME: str = "pro"
    FREE_DAILY_EXPORT_LIMIT: int = 2
    # PDF export font: path to a .ttf file inside the container/host; falls back to system serif
    PDF_FONT_PATH: str = ""
    # Stripe billing
    STRIPE_API_KEY: str = ""
    STRIPE_PRICE_PRO_MONTHLY: str = ""
    STRIPE_PRICE_PRO_YEARLY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_SUCCESS_URL: str = "{origin}/pricing?success=1"
    STRIPE_CANCEL_URL: str = "{origin}/pricing?canceled=1"

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
    SESSION_EXPIRE_HOURS: int = 24  # Session expiration in hours
    SESSION_REFRESH_THRESHOLD_HOURS: int = 12  # Refresh session if older than this
    API_KEY_EXPIRE_DAYS: int = 365  # Default API key expiration in days
    OAUTH_STATE_VALIDATION: bool = True  # Enable OAuth state parameter validation
    CORS_ALLOW_ORIGINS: str = ""  # Comma-separated allowed origins; empty = use FRONTEND_ORIGIN only
    MAX_LOGIN_ATTEMPTS: int = 5  # Max failed login attempts before rate limiting
    LOGIN_ATTEMPT_WINDOW_MINUTES: int = 15  # Time window for tracking login attempts

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
    WHISPER_LANGUAGE: str = ""  # Empty = auto-detect; set to specific language code to force (e.g., 'en', 'es', 'fr')
    # Quality presets: fast, balanced, accurate
    WHISPER_QUALITY_PRESET: str = "balanced"  # Default quality preset
    WHISPER_BEAM_SIZE: int = 5  # Beam size for decoding (1-10, higher = more accurate but slower)
    WHISPER_TEMPERATURE: float = 0.0  # Temperature for sampling (0.0-1.0, 0.0 = greedy)
    WHISPER_VAD_FILTER: bool = False  # Voice Activity Detection filter (faster-whisper only)
    WHISPER_WORD_TIMESTAMPS: bool = True  # Extract word-level timestamps
    # Custom vocabulary post-processing
    ENABLE_CUSTOM_VOCABULARY: bool = True  # Apply custom vocabulary corrections
    # Translation support
    ENABLE_TRANSLATION: bool = False  # Enable translation features
    TRANSLATION_PROVIDER: str = "libretranslate"  # 'google', 'deepl', 'libretranslate'
    LIBRETRANSLATE_URL: str = "https://libretranslate.com"  # LibreTranslate API URL
    LIBRETRANSLATE_API_KEY: str = ""  # Optional API key for LibreTranslate
    GOOGLE_TRANSLATE_API_KEY: str = ""  # Google Cloud Translation API key
    DEEPL_API_KEY: str = ""  # DeepL API key

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
