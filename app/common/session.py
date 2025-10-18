from __future__ import annotations

import os
from typing import Optional

from fastapi import Request, Response
from sqlalchemy import text

SESSION_COOKIE = os.environ.get("SESSION_COOKIE_NAME", "tc_session")


def get_session_token(req: Request) -> Optional[str]:
    return req.cookies.get(SESSION_COOKIE)


def set_session_cookie(resp: Response, token: str):
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", secure=False, max_age=60 * 60 * 24 * 7)


def clear_session_cookie(resp: Response):
    resp.delete_cookie(SESSION_COOKIE)


def get_user_from_session(db, token: Optional[str]):
    if not token:
        return None
    row = db.execute(
        text(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=:t AND (s.expires_at IS NULL OR s.expires_at>now())"
        ),
        {"t": token},
    ).mappings().first()
    return row


def is_admin(user) -> bool:
    if not user:
        return False
    admins_env = os.environ.get("ADMIN_EMAILS", "")
    admins = set([e.strip().lower() for e in admins_env.split(",") if e.strip()])
    email = (user.get("email") or "").lower()
    return email in admins if admins else False
