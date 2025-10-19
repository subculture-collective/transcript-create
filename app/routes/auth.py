import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text

from ..common.session import clear_session_cookie as _clear_session_cookie
from ..common.session import get_session_token as _get_session_token
from ..common.session import get_user_from_session as _get_user_from_session
from ..common.session import set_session_cookie as _set_session_cookie
from ..db import get_db
from ..settings import settings

try:
    from authlib.integrations.starlette_client import OAuth
except Exception:
    OAuth = None

router = APIRouter()


def _new_oauth():
    if not OAuth:
        return None
    oauth = OAuth()
    oauth.register(
        name="twitch",
        client_id=settings.OAUTH_TWITCH_CLIENT_ID,
        client_secret=settings.OAUTH_TWITCH_CLIENT_SECRET,
        access_token_url="https://id.twitch.tv/oauth2/token",
        authorize_url="https://id.twitch.tv/oauth2/authorize",
        api_base_url="https://api.twitch.tv/helix/",
        client_kwargs={"scope": "user:read:email"},
    )
    return oauth


@router.get("/auth/me")
def auth_me(request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        return {"user": None}
    plan = user.get("plan") or "free"
    limit = settings.FREE_DAILY_SEARCH_LIMIT if plan == "free" else None
    # Count searches today used in main previously via events table
    used = None
    if plan == "free":
        used = db.execute(
            text(
                """
            SELECT COUNT(*) FROM events
            WHERE user_id = :u
              AND type = 'search'
              AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC')
        """
            ),
            {"u": str(user["id"])},
        ).scalar_one()
    return {
        "user": {
            "id": user["id"],
            "email": user.get("email"),
            "name": user.get("name"),
            "avatar_url": user.get("avatar_url"),
            "plan": plan,
            "searches_used_today": used,
            "search_limit": limit,
        }
    }


@router.get("/auth/login/google")
def auth_login_google(request: Request):
    if not OAuth:
        raise HTTPException(501, "Authlib not installed")
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.OAUTH_GOOGLE_CLIENT_ID,
        client_secret=settings.OAUTH_GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    redirect_uri = settings.OAUTH_GOOGLE_REDIRECT_URI
    return oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/login/twitch")
def auth_login_twitch(request: Request):
    if not OAuth:
        raise HTTPException(501, "Authlib not installed")
    oauth = _new_oauth()
    redirect_uri = settings.OAUTH_TWITCH_REDIRECT_URI
    return oauth.twitch.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback/google")
async def auth_callback_google(request: Request, db=Depends(get_db)):
    if not OAuth:
        raise HTTPException(501, "Authlib not installed")
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.OAUTH_GOOGLE_CLIENT_ID,
        client_secret=settings.OAUTH_GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    if not userinfo:
        resp = await oauth.google.get("userinfo", token=token)
        userinfo = resp.json()
    sub = userinfo.get("sub")
    email = userinfo.get("email")
    name = userinfo.get("name")
    avatar = userinfo.get("picture")
    if not sub:
        raise HTTPException(400, "Missing subject")
    with db.begin():
        row = (
            db.execute(text("SELECT * FROM users WHERE oauth_provider='google' AND oauth_subject=:s"), {"s": sub})
            .mappings()
            .first()
        )
        if row:
            user_id = row["id"]
            db.execute(
                text("UPDATE users SET email=:e, name=:n, avatar_url=:a, updated_at=now() WHERE id=:i"),
                {"e": email, "n": name, "a": avatar, "i": str(user_id)},
            )
        else:
            user_id = uuid.uuid4()
            db.execute(
                text(
                    "INSERT INTO users (id,email,name,avatar_url,oauth_provider,oauth_subject) VALUES (:i,:e,:n,:a,'google',:s)"  # noqa: E501
                ),
                {"i": str(user_id), "e": email, "n": name, "a": avatar, "s": sub},
            )
        session_token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(days=7)
        db.execute(
            text(
                "INSERT INTO sessions (user_id, token, user_agent, ip_address, expires_at) VALUES (:u,:t,:ua,:ip,:exp)"
            ),
            {
                "u": str(user_id),
                "t": session_token,
                "ua": request.headers.get("user-agent"),
                "ip": request.client.host if request.client else None,
                "exp": expires,
            },
        )
    resp = RedirectResponse(url=f"{settings.FRONTEND_ORIGIN}")
    _set_session_cookie(resp, session_token)
    return resp


@router.get("/auth/callback/twitch")
async def auth_callback_twitch(request: Request, db=Depends(get_db)):
    if not OAuth:
        raise HTTPException(501, "Authlib not installed")
    oauth = _new_oauth()
    token = await oauth.twitch.authorize_access_token(request)
    access_token = token.get("access_token")
    if not access_token:
        raise HTTPException(400, "Missing access token")
    headers = {
        "Client-ID": settings.OAUTH_TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {access_token}",
    }
    resp = await oauth.twitch.get("users", token=token, headers=headers)
    data = resp.json()
    users = data.get("data") or []
    if not users:
        raise HTTPException(400, "Failed to fetch Twitch user")
    u0 = users[0]
    sub = u0.get("id")
    email = u0.get("email")
    name = u0.get("display_name") or u0.get("login")
    avatar = u0.get("profile_image_url")
    if not sub:
        raise HTTPException(400, "Missing Twitch user id")
    with db.begin():
        row = (
            db.execute(text("SELECT * FROM users WHERE oauth_provider='twitch' AND oauth_subject=:s"), {"s": sub})
            .mappings()
            .first()
        )
        if row:
            user_id = row["id"]
            db.execute(
                text("UPDATE users SET email=:e, name=:n, avatar_url=:a, updated_at=now() WHERE id=:i"),
                {"e": email, "n": name, "a": avatar, "i": str(user_id)},
            )
        else:
            user_id = uuid.uuid4()
            db.execute(
                text(
                    "INSERT INTO users (id,email,name,avatar_url,oauth_provider,oauth_subject) VALUES (:i,:e,:n,:a,'twitch',:s)"  # noqa: E501
                ),
                {"i": str(user_id), "e": email, "n": name, "a": avatar, "s": sub},
            )
        session_token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(days=7)
        db.execute(
            text(
                "INSERT INTO sessions (user_id, token, user_agent, ip_address, expires_at) VALUES (:u,:t,:ua,:ip,:exp)"
            ),
            {
                "u": str(user_id),
                "t": session_token,
                "ua": request.headers.get("user-agent"),
                "ip": request.client.host if request.client else None,
                "exp": expires,
            },
        )
    resp = RedirectResponse(url=f"{settings.FRONTEND_ORIGIN}")
    _set_session_cookie(resp, session_token)
    return resp


@router.post("/auth/logout")
def auth_logout(request: Request, db=Depends(get_db)):
    tok = _get_session_token(request)
    if tok:
        db.execute(text("DELETE FROM sessions WHERE token=:t"), {"t": tok})
        db.commit()
    resp = JSONResponse({"ok": True})
    _clear_session_cookie(resp)
    return resp
