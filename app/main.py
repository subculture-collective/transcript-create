import logging, os
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
from .settings import settings


logging.basicConfig(
    level=getattr(logging, (os.environ.get("LOG_LEVEL") or "INFO").upper(), logging.INFO),
    format='%(asctime)s %(levelname)s [api] %(message)s',
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

from .routes.exports import router as exports_router
from .routes.auth import router as auth_router
from .routes.billing import router as billing_router
from .routes.jobs import router as jobs_router
from .routes.videos import router as videos_router
from .routes.favorites import router as favorites_router
from .routes.events import router as events_router
from .routes.admin import router as admin_router
from .routes.search import router as search_router

app.include_router(exports_router)
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(jobs_router)
app.include_router(videos_router)
app.include_router(favorites_router)
app.include_router(events_router)
app.include_router(admin_router)
app.include_router(search_router)

# Count today's searches for a user (based on events table) in UTC day
def _count_searches_today(db, user_id: Optional[str]) -> int:
    if not user_id:
        return 0
    return db.execute(text("""
        SELECT COUNT(*) FROM events
        WHERE user_id = :u
          AND type = 'search'
          AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC')
    """), {"u": user_id}).scalar_one()
# Configure OAuth registry lazily per request to avoid global state issues
def _new_oauth():
    if not OAuth:
        return None
    oauth = OAuth()
    def _row_to_status(row):
        return row  # no-op placeholder to avoid breaking imports if referenced elsewhere
        return 0
