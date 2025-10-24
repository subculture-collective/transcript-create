import logging
import os
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError

from .exceptions import AppError
from .settings import settings

logging.basicConfig(
    level=getattr(logging, (os.environ.get("LOG_LEVEL") or "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [api] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI()

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


# Exception handlers
@app.exception_handler(AppError)
async def app_exception_handler(request: Request, exc: AppError):
    """Handle custom application exceptions."""
    request_id = getattr(request.state, "request_id", None)
    logger.warning(
        "Application error: %s | path=%s request_id=%s details=%s",
        exc.message,
        request.url.path,
        request_id,
        exc.details,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors with user-friendly messages."""
    request_id = getattr(request.state, "request_id", None)
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
        "Validation error: path=%s request_id=%s errors=%s",
        request.url.path,
        request_id,
        errors,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "details": {"errors": errors},
        },
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors."""
    request_id = getattr(request.state, "request_id", None)
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"]) if error["loc"] else "unknown"
        errors.append(
            {
                "field": field,
                "message": error["msg"],
                "type": error["type"],
            }
        )

    logger.warning(
        "Pydantic validation error: path=%s request_id=%s errors=%s",
        request.url.path,
        request_id,
        errors,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Data validation failed",
            "details": {"errors": errors},
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """Handle SQLAlchemy database errors without exposing details."""
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "Database error: %s | path=%s request_id=%s",
        str(exc),
        request.url.path,
        request_id,
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
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "Unhandled exception: %s | path=%s request_id=%s",
        str(exc),
        request.url.path,
        request_id,
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


# Middleware for request ID tracking
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID for tracing."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


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


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring and E2E tests"""
    return {"status": "ok"}
