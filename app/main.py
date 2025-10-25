import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError

from .exceptions import AppError
from .logging_config import configure_logging, get_logger, request_id_ctx, user_id_ctx
from .settings import settings

# Configure structured logging for API service
configure_logging(
    service="api",
    level=settings.LOG_LEVEL,
    json_format=(settings.LOG_FORMAT == "json"),
)
logger = get_logger(__name__)

app = FastAPI(
    title="Transcript Create API",
    description="""
YouTube video transcription service API with searchable and exportable transcripts.

## Features

* **Job Management** - Create and monitor transcription jobs for single videos or entire channels
* **Video Transcripts** - Access Whisper-generated transcripts with optional speaker diarization
* **YouTube Captions** - Retrieve and export YouTube's native closed captions
* **Full-Text Search** - Search across transcripts using PostgreSQL or OpenSearch
* **Export Formats** - Download transcripts in SRT, VTT, JSON, and PDF formats
* **Authentication** - OAuth 2.0 via Google and Twitch
* **Billing** - Stripe integration for Pro subscriptions
* **Admin Tools** - Event analytics and user management

## Authentication

Most endpoints require authentication via session cookies set after OAuth login.
Admin endpoints require additional authorization.
    """,
    version="0.1.0",
    contact={
        "name": "onnwee",
        "url": "https://github.com/onnwee",
    },
    license_info={
        "name": "TBD",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "Jobs", "description": "Create and monitor transcription jobs"},
        {"name": "Videos", "description": "Access video information and transcripts"},
        {"name": "Search", "description": "Full-text search across transcripts"},
        {"name": "Exports", "description": "Export transcripts in various formats"},
        {"name": "Auth", "description": "OAuth authentication and session management"},
        {"name": "Billing", "description": "Stripe subscription and payment management"},
        {"name": "Admin", "description": "Administrative endpoints for event analytics"},
        {"name": "Favorites", "description": "User favorite transcript segments"},
        {"name": "Events", "description": "Client-side event tracking"},
        {"name": "Health", "description": "Service health check"},
    ],
)

# Allow local dev frontends to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_ORIGIN,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSION_COOKIE = "tc_session"


# Optional Sentry integration
if settings.SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
            ],
        )
        logger.info("Sentry initialized", extra={"environment": settings.SENTRY_ENVIRONMENT})
    except ImportError:
        logger.warning("Sentry SDK not installed. Set SENTRY_DSN to enable error tracking.")
    except Exception as e:
        logger.error("Failed to initialize Sentry", extra={"error": str(e)})


@app.on_event("startup")
async def startup_event():
    """Log application startup."""
    logger.info(
        "API service started",
        extra={
            "log_level": settings.LOG_LEVEL,
            "log_format": settings.LOG_FORMAT,
            "database_url": settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "[hidden]",
        },
    )


# Exception handlers
@app.exception_handler(AppError)
async def app_exception_handler(request: Request, exc: AppError):
    """Handle custom application exceptions."""
    logger.warning(
        "Application error",
        extra={
            "error_type": type(exc).__name__,
            "message": exc.message,
            "path": request.url.path,
            "details": exc.details,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors with user-friendly messages."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"][1:]) if len(error["loc"]) > 1 else str(error["loc"][0])
        errors.append(
            {
                "field": field,
                "message": error["msg"],
                "type": error["type"],
            }
        )

    logger.warning(
        "Validation error",
        extra={
            "path": request.url.path,
            "errors": errors,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "details": {"errors": errors},
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """Handle SQLAlchemy database errors without exposing details."""
    logger.error(
        "Database error",
        extra={
            "error_type": type(exc).__name__,
            "path": request.url.path,
        },
        exc_info=True,
    )

    # Determine if it's a connection issue
    if isinstance(exc, (OperationalError, DBAPIError)):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": "service_unavailable",
                "message": "Database service is temporarily unavailable. Please try again later.",
                "details": {},
            },
        )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "database_error",
            "message": "A database error occurred. Please try again later.",
            "details": {},
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions."""
    logger.error(
        "Unhandled exception",
        extra={
            "error_type": type(exc).__name__,
            "path": request.url.path,
        },
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please try again later.",
            "details": {},
        },
    )


# Middleware for request ID tracking and context
@app.middleware("http")
async def add_request_context(request: Request, call_next):
    """Add request ID and user context for tracing."""
    req_id = str(uuid.uuid4())
    request.state.request_id = req_id
    
    # Set request ID in context for logging
    request_id_ctx.set(req_id)
    
    # Extract user ID from session if available
    # Note: User ID will be set by auth middleware/dependency
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response
    finally:
        # Clean up context
        request_id_ctx.set(None)
        user_id_ctx.set(None)


from .routes.admin import router as admin_router  # noqa: E402
from .routes.auth import router as auth_router  # noqa: E402
from .routes.billing import router as billing_router  # noqa: E402
from .routes.events import router as events_router  # noqa: E402
from .routes.exports import router as exports_router  # noqa: E402
from .routes.favorites import router as favorites_router  # noqa: E402
from .routes.jobs import router as jobs_router  # noqa: E402
from .routes.search import router as search_router  # noqa: E402
from .routes.videos import router as videos_router  # noqa: E402

app.include_router(exports_router)
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(jobs_router)
app.include_router(videos_router)
app.include_router(favorites_router)
app.include_router(events_router)
app.include_router(admin_router)
app.include_router(search_router)


@app.get(
    "/health",
    tags=["Health"],
    summary="Health check",
    description="Check if the API service is running and responding to requests.",
    responses={
        200: {
            "description": "Service is healthy",
            "content": {"application/json": {"example": {"status": "ok"}}},
        }
    },
)
async def health_check():
    """Health check endpoint for monitoring and E2E tests"""
    return {"status": "ok"}
