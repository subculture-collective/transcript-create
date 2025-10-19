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

    # Search backend toggle: 'postgres' (default) or 'opensearch'
    SEARCH_BACKEND: str = "postgres"
    # OpenSearch settings
    OPENSEARCH_URL: str = "http://localhost:9200"
    OPENSEARCH_INDEX_NATIVE: str = "segments"
    OPENSEARCH_INDEX_YOUTUBE: str = "youtube_segments"
    OPENSEARCH_USER: str = ""
    OPENSEARCH_PASSWORD: str = ""

    # Frontend origin for CORS/redirects
    FRONTEND_ORIGIN: str = "http://localhost:5173"
    # Session and OAuth
    SESSION_SECRET: str = "change-me"
    OAUTH_GOOGLE_CLIENT_ID: str = ""
    OAUTH_GOOGLE_CLIENT_SECRET: str = ""
    OAUTH_GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/callback/google"
    # Twitch OAuth
    OAUTH_TWITCH_CLIENT_ID: str = ""
    OAUTH_TWITCH_CLIENT_SECRET: str = ""
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
