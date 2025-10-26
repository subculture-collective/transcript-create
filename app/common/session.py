from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request, Response
from sqlalchemy import text

from ..logging_config import user_id_ctx
from ..settings import settings

SESSION_COOKIE = os.environ.get("SESSION_COOKIE_NAME", "tc_session")


def get_session_token(req: Request) -> Optional[str]:
    return req.cookies.get(SESSION_COOKIE)


def set_session_cookie(resp: Response, token: str):
    """Set session cookie with secure settings."""
    # Determine if we should use secure flag based on environment
    secure = settings.ENVIRONMENT == "production"
    
    # Calculate max_age from settings (default 24 hours)
    max_age = settings.SESSION_EXPIRE_HOURS * 60 * 60
    
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,  # Prevent JavaScript access
        samesite="lax",  # CSRF protection
        secure=secure,  # HTTPS only in production
        max_age=max_age,
    )


def clear_session_cookie(resp: Response):
    resp.delete_cookie(SESSION_COOKIE, samesite="lax")


def get_user_from_session(db, token: Optional[str]):
    """Get user from session token, checking expiration."""
    if not token:
        return None
    row = (
        db.execute(
            text(
                "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=:t AND (s.expires_at IS NULL OR s.expires_at>now())"  # noqa: E501
            ),
            {"t": token},
        )
        .mappings()
        .first()
    )
    
    # Set user context for logging if user found
    if row:
        user_id_ctx.set(str(row.get("id")))
    
    return row


def should_refresh_session(db, token: Optional[str]) -> bool:
    """Check if session should be refreshed based on age."""
    if not token:
        return False
    
    result = db.execute(
        text(
            """
            SELECT created_at, expires_at
            FROM sessions
            WHERE token = :t
            AND (expires_at IS NULL OR expires_at > now())
            """
        ),
        {"t": token}
    ).mappings().first()
    
    if not result:
        return False
    
    # Refresh if session is older than threshold
    threshold = timedelta(hours=settings.SESSION_REFRESH_THRESHOLD_HOURS)
    age = datetime.utcnow() - result["created_at"]
    
    return age > threshold


def refresh_session(db, token: str):
    """Extend session expiration time."""
    new_expires = datetime.utcnow() + timedelta(hours=settings.SESSION_EXPIRE_HOURS)
    
    db.execute(
        text("UPDATE sessions SET expires_at = :exp WHERE token = :t"),
        {"exp": new_expires, "t": token}
    )
    db.commit()


def is_admin(user) -> bool:
    if not user:
        return False
    admins_env = os.environ.get("ADMIN_EMAILS", "")
    admins = set([e.strip().lower() for e in admins_env.split(",") if e.strip()])
    email = (user.get("email") or "").lower()
    return email in admins if admins else False

