import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .settings import settings

logging.basicConfig(
    level=getattr(logging, (os.environ.get("LOG_LEVEL") or "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [api] %(message)s",
)
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
