import logging, os
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse, PlainTextResponse
from .db import get_db
from .settings import settings
import requests
from . import crud
from .schemas import JobCreate, JobStatus, TranscriptResponse, Segment, YouTubeTranscriptResponse, YTSegment, SearchResponse, SearchHit, VideoInfo
import uuid
import secrets
from datetime import datetime, timedelta
from sqlalchemy import text
import stripe
from io import BytesIO
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

try:
    from authlib.integrations.starlette_client import OAuth
except Exception:
    OAuth = None

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
stripe.api_key = settings.STRIPE_API_KEY or None

def _get_session_token(req: Request) -> str | None:
    return req.cookies.get(SESSION_COOKIE)

def _set_session_cookie(resp: Response, token: str):
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", secure=False, max_age=60*60*24*7)

def _clear_session_cookie(resp: Response):
    resp.delete_cookie(SESSION_COOKIE)

def _get_user_from_session(db, token: str | None):
    if not token:
        return None
    row = db.execute(
        text("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=:t AND (s.expires_at IS NULL OR s.expires_at>now())"),
        {"t": token}
    ).mappings().first()
    return row

def _is_admin(user) -> bool:
    if not user:
        return False
    admins = set([e.strip().lower() for e in (settings.ADMIN_EMAILS or "").split(",") if e.strip()])
    email = (user.get("email") or "").lower()
    return email in admins if admins else False

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
    # Google is configured inline in handlers
    # Twitch provider: authorization_code flow with user:read:email scope
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

@app.post("/jobs", response_model=JobStatus)
def create_job(payload: JobCreate, db=Depends(get_db)):
    job_id = crud.create_job(db, payload.kind, str(payload.url))
    job = crud.fetch_job(db, job_id)
    return _row_to_status(job)

@app.get("/auth/me")
def auth_me(request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        return {"user": None}
    # include plan and today's quota info
    plan = user.get("plan") or "free"
    limit = settings.FREE_DAILY_SEARCH_LIMIT if plan == "free" else None
    used = _count_searches_today(db, str(user["id"])) if plan == "free" else None
    return {"user": {"id": user["id"], "email": user.get("email"), "name": user.get("name"), "avatar_url": user.get("avatar_url"), "plan": plan, "searches_used_today": used, "search_limit": limit}}

@app.get("/auth/login/google")
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

@app.get("/auth/login/twitch")
def auth_login_twitch(request: Request):
    if not OAuth:
        raise HTTPException(501, "Authlib not installed")
    oauth = _new_oauth()
    redirect_uri = settings.OAUTH_TWITCH_REDIRECT_URI
    return oauth.twitch.authorize_redirect(request, redirect_uri)

@app.get("/auth/callback/google")
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
        # fetch userinfo explicitly
        resp = await oauth.google.get("userinfo", token=token)
        userinfo = resp.json()
    sub = userinfo.get("sub")
    email = userinfo.get("email")
    name = userinfo.get("name")
    avatar = userinfo.get("picture")
    if not sub:
        raise HTTPException(400, "Missing subject")
    # upsert user
    with db.begin():
        row = db.execute(text("SELECT * FROM users WHERE oauth_provider='google' AND oauth_subject=:s"), {"s": sub}).mappings().first()
        if row:
            user_id = row["id"]
            db.execute(text("UPDATE users SET email=:e, name=:n, avatar_url=:a, updated_at=now() WHERE id=:i"), {"e": email, "n": name, "a": avatar, "i": str(user_id)})
        else:
            user_id = uuid.uuid4()
            db.execute(text("INSERT INTO users (id,email,name,avatar_url,oauth_provider,oauth_subject) VALUES (:i,:e,:n,:a,'google',:s)"), {"i": str(user_id), "e": email, "n": name, "a": avatar, "s": sub})
        # create session
        session_token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(days=7)
        db.execute(text("INSERT INTO sessions (user_id, token, user_agent, ip_address, expires_at) VALUES (:u,:t,:ua,:ip,:exp)"), {"u": str(user_id), "t": session_token, "ua": request.headers.get("user-agent"), "ip": request.client.host if request.client else None, "exp": expires})
    resp = RedirectResponse(url=f"{settings.FRONTEND_ORIGIN}")
    _set_session_cookie(resp, session_token)
    return resp

@app.get("/auth/callback/twitch")
async def auth_callback_twitch(request: Request, db=Depends(get_db)):
    if not OAuth:
        raise HTTPException(501, "Authlib not installed")
    oauth = _new_oauth()
    token = await oauth.twitch.authorize_access_token(request)
    access_token = token.get("access_token")
    if not access_token:
        raise HTTPException(400, "Missing access token")
    # Fetch user info from Helix API
    # Authlib client can call relative to api_base_url and we must pass Client-ID and Authorization
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
    # upsert user
    with db.begin():
        row = db.execute(text("SELECT * FROM users WHERE oauth_provider='twitch' AND oauth_subject=:s"), {"s": sub}).mappings().first()
        if row:
            user_id = row["id"]
            db.execute(text("UPDATE users SET email=:e, name=:n, avatar_url=:a, updated_at=now() WHERE id=:i"), {"e": email, "n": name, "a": avatar, "i": str(user_id)})
        else:
            user_id = uuid.uuid4()
            db.execute(text("INSERT INTO users (id,email,name,avatar_url,oauth_provider,oauth_subject) VALUES (:i,:e,:n,:a,'twitch',:s)"), {"i": str(user_id), "e": email, "n": name, "a": avatar, "s": sub})
        # create session
        session_token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(days=7)
        db.execute(text("INSERT INTO sessions (user_id, token, user_agent, ip_address, expires_at) VALUES (:u,:t,:ua,:ip,:exp)"), {"u": str(user_id), "t": session_token, "ua": request.headers.get("user-agent"), "ip": request.client.host if request.client else None, "exp": expires})
    resp = RedirectResponse(url=f"{settings.FRONTEND_ORIGIN}")
    _set_session_cookie(resp, session_token)
    return resp

@app.post("/auth/logout")
def auth_logout(request: Request, db=Depends(get_db)):
    tok = _get_session_token(request)
    if tok:
        db.execute(text("DELETE FROM sessions WHERE token=:t"), {"t": tok}); db.commit()
    resp = JSONResponse({"ok": True})
    _clear_session_cookie(resp)
    return resp

# --- Stripe Billing ---
@app.post("/billing/checkout-session")
def create_checkout_session(payload: dict, request: Request, db=Depends(get_db)):
    if not settings.STRIPE_API_KEY:
        raise HTTPException(501, "Stripe not configured")
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise HTTPException(401)
    period = (payload.get("period") or "").lower()
    price_id = payload.get("price_id") or (settings.STRIPE_PRICE_PRO_YEARLY if period == 'yearly' and settings.STRIPE_PRICE_PRO_YEARLY else settings.STRIPE_PRICE_PRO_MONTHLY)
    origin = settings.FRONTEND_ORIGIN.rstrip('/')
    success_url_t = (settings.STRIPE_SUCCESS_URL or f"{origin}/pricing?success=1").replace("{origin}", origin)
    cancel_url_t = (settings.STRIPE_CANCEL_URL or f"{origin}/pricing?canceled=1").replace("{origin}", origin)
    # Idempotently create or reuse a customer
    customer_id = user.get("stripe_customer_id")
    if not customer_id:
        cust = stripe.Customer.create(email=user.get("email") or None, metadata={"user_id": str(user["id"])})
        customer_id = cust.id
        db.execute(text("UPDATE users SET stripe_customer_id=:c, updated_at=now() WHERE id=:i"), {"c": customer_id, "i": str(user["id"])})
        db.commit()
    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url_t,
        cancel_url=cancel_url_t,
        allow_promotion_codes=True,
        metadata={"user_id": str(user["id"])},
    )
    return {"id": session.id, "url": session.url}

@app.get("/billing/portal")
def billing_portal(request: Request, db=Depends(get_db)):
    if not settings.STRIPE_API_KEY:
        raise HTTPException(501, "Stripe not configured")
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise HTTPException(401)
    if not user.get("stripe_customer_id"):
        raise HTTPException(400, "No Stripe customer")
    origin = settings.FRONTEND_ORIGIN.rstrip('/')
    portal = stripe.billing_portal.Session.create(customer=user["stripe_customer_id"], return_url=f"{origin}/pricing")
    return {"url": portal.url}

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request, db=Depends(get_db)):
    if not settings.STRIPE_API_KEY:
        raise HTTPException(501, "Stripe not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        if settings.STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig, settings.STRIPE_WEBHOOK_SECRET)
        else:
            event = stripe.Event.construct_from(request.json(), stripe.api_key)
    except Exception as e:
        raise HTTPException(400, f"Webhook error: {e}")
    t = event.get("type")
    data = event.get("data", {}).get("object", {})
    # Map Stripe events to user plan
    def set_plan_by_customer(customer_id: str, plan: str | None, sub_status: str | None):
        row = db.execute(text("SELECT id FROM users WHERE stripe_customer_id=:c"), {"c": customer_id}).mappings().first()
        if not row:
            return
        if plan:
            db.execute(text("UPDATE users SET plan=:p, stripe_subscription_status=:s, updated_at=now() WHERE id=:i"), {"p": plan, "s": sub_status, "i": str(row["id"])})
        else:
            db.execute(text("UPDATE users SET stripe_subscription_status=:s, updated_at=now() WHERE id=:i"), {"s": sub_status, "i": str(row["id"])})
        db.commit()
    if t in ("checkout.session.completed", "customer.subscription.created", "customer.subscription.updated"):
        customer_id = data.get("customer") or data.get("customer_id")
        status = (data.get("status") or "").lower()
        plan = settings.PRO_PLAN_NAME if status in ("active", "trialing") else None
        if customer_id:
            set_plan_by_customer(customer_id, plan, status)
    elif t in ("customer.subscription.deleted",):
        customer_id = data.get("customer")
        if customer_id:
            set_plan_by_customer(customer_id, "free", "canceled")
    return {"received": True}

@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: uuid.UUID, db=Depends(get_db)):
    job = crud.fetch_job(db, job_id)
    if not job:
        raise HTTPException(404)
    return _row_to_status(job)

@app.get("/videos/{video_id}/transcript", response_model=TranscriptResponse)
def get_transcript(video_id: uuid.UUID, db=Depends(get_db)):
    segs = crud.list_segments(db, video_id)
    if not segs:
        raise HTTPException(404, "No segments")
    return TranscriptResponse(
        video_id=video_id,
        segments=[Segment(start_ms=r[0], end_ms=r[1], text=r[2], speaker_label=r[3]) for r in segs]
    )

@app.get("/videos/{video_id}", response_model=VideoInfo)
def get_video_info(video_id: uuid.UUID, db=Depends(get_db)):
    v = crud.get_video(db, video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    return VideoInfo(id=v["id"], youtube_id=v["youtube_id"], title=v.get("title"), duration_seconds=v.get("duration_seconds"))

@app.get("/videos", response_model=list[VideoInfo])
def list_videos(limit: int = 50, offset: int = 0, db=Depends(get_db)):
    rows = crud.list_videos(db, limit=limit, offset=offset)
    return [VideoInfo(id=r["id"], youtube_id=r["youtube_id"], title=r.get("title"), duration_seconds=r.get("duration_seconds")) for r in rows]

# Favorites API (session-authenticated)
from sqlalchemy import text as _text

@app.get("/users/me/favorites")
def list_favorites(request: Request, db=Depends(get_db), video_id: Optional[uuid.UUID] = None):
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise HTTPException(401)
    if video_id:
        rows = db.execute(_text("SELECT id, video_id, start_ms, end_ms, text, created_at FROM favorites WHERE user_id=:u AND video_id=:v ORDER BY created_at DESC"), {"u": str(user["id"]), "v": str(video_id)}).mappings().all()
    else:
        rows = db.execute(_text("SELECT id, video_id, start_ms, end_ms, text, created_at FROM favorites WHERE user_id=:u ORDER BY created_at DESC"), {"u": str(user["id"]) }).mappings().all()
    return {"items": rows}

@app.post("/users/me/favorites")
def add_favorite(payload: dict, request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise HTTPException(401)
    vid = payload.get("video_id"); start = payload.get("start_ms"); end = payload.get("end_ms"); textv = payload.get("text")
    if not (vid and isinstance(start, int) and isinstance(end, int)):
        raise HTTPException(400, "Missing fields")
    fid = uuid.uuid4()
    db.execute(_text("INSERT INTO favorites (id,user_id,video_id,start_ms,end_ms,text) VALUES (:i,:u,:v,:s,:e,:t)"), {"i": str(fid), "u": str(user["id"]), "v": str(vid), "s": start, "e": end, "t": textv})
    db.commit()
    return {"id": fid}

@app.delete("/users/me/favorites/{favorite_id}")
def delete_favorite(favorite_id: uuid.UUID, request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise HTTPException(401)
    db.execute(_text("DELETE FROM favorites WHERE id=:i AND user_id=:u"), {"i": str(favorite_id), "u": str(user["id"])})
    db.commit()
    return {"ok": True}

@app.post("/events")
def ingest_event(payload: dict, request: Request, db=Depends(get_db)):
    tok = _get_session_token(request)
    user = _get_user_from_session(db, tok)
    etype = payload.get("type") or "unknown"
    data = payload.get("payload") or {}
    db.execute(_text("INSERT INTO events (user_id, session_token, type, payload) VALUES (:u,:t,:ty,:p)"), {"u": str(user["id"]) if user else None, "t": tok, "ty": etype, "p": data})
    db.commit()
    return {"ok": True}

@app.post("/events/batch")
def ingest_events_batch(payload: dict, request: Request, db=Depends(get_db)):
    tok = _get_session_token(request)
    user = _get_user_from_session(db, tok)
    events = payload.get("events") or []
    for e in events:
        etype = e.get("type") or "unknown"
        data = e.get("payload") or {}
        db.execute(_text("INSERT INTO events (user_id, session_token, type, payload) VALUES (:u,:t,:ty,:p)"), {"u": str(user["id"]) if user else None, "t": tok, "ty": etype, "p": data})
    db.commit()
    return {"ok": True, "count": len(events)}

@app.get("/admin/events")
def admin_events(request: Request, db=Depends(get_db), type: Optional[str] = None, user_email: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None, limit: int = 100, offset: int = 0):
    user = _get_user_from_session(db, _get_session_token(request))
    if not _is_admin(user):
        raise HTTPException(403)
    where = []
    params = {}
    if type:
        where.append("type = :type"); params["type"] = type
    if user_email:
        where.append("user_id IN (SELECT id FROM users WHERE email=:email)"); params["email"] = user_email
    if start:
        where.append("created_at >= :start"); params["start"] = start
    if end:
        where.append("created_at <= :end"); params["end"] = end
    sql = "SELECT id, created_at, user_id, session_token, type, payload FROM events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit; params["offset"] = offset
    rows = db.execute(_text(sql), params).mappings().all()
    return {"items": rows}

@app.get("/admin/events.csv")
def admin_events_csv(request: Request, db=Depends(get_db), type: Optional[str] = None, user_email: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None, limit: int = 1000, offset: int = 0):
    user = _get_user_from_session(db, _get_session_token(request))
    if not _is_admin(user):
        raise HTTPException(403)
    where = []
    params = {}
    if type:
        where.append("type = :type"); params["type"] = type
    if user_email:
        where.append("user_id IN (SELECT id FROM users WHERE email=:email)"); params["email"] = user_email
    if start:
        where.append("created_at >= :start"); params["start"] = start
    if end:
        where.append("created_at <= :end"); params["end"] = end
    sql = "SELECT id, created_at, user_id, session_token, type, payload FROM events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit; params["offset"] = offset
    rows = db.execute(_text(sql), params).all()
    # Build CSV
    def esc(x):
        s = str(x) if x is not None else ''
        if any(c in s for c in [',','"','\n']):
            s = '"' + s.replace('"','""') + '"'
        return s
    header = "id,created_at,user_id,session_token,type,payload\n"
    body = "".join([f"{esc(r[0])},{esc(r[1])},{esc(r[2])},{esc(r[3])},{esc(r[4])},{esc(r[5])}\n" for r in rows])
    return PlainTextResponse(content=header+body, media_type="text/csv")

@app.get("/admin/events/summary")
def admin_events_summary(request: Request, db=Depends(get_db), start: Optional[str] = None, end: Optional[str] = None):
    user = _get_user_from_session(db, _get_session_token(request))
    if not _is_admin(user):
        raise HTTPException(403)
    params = {}
    where = []
    if start:
        where.append("created_at >= :start"); params["start"] = start
    if end:
        where.append("created_at <= :end"); params["end"] = end
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    by_type = db.execute(_text(f"SELECT type, COUNT(*) FROM events{where_sql} GROUP BY type ORDER BY COUNT(*) DESC"), params).all()
    by_day = db.execute(_text(f"SELECT DATE(created_at) as day, COUNT(*) FROM events{where_sql} GROUP BY day ORDER BY day ASC"), params).all()
    return {"by_type": [{"type": r[0], "count": r[1]} for r in by_type], "by_day": [{"day": str(r[0]), "count": r[1]} for r in by_day]}

@app.get("/admin/users")
def admin_users(request: Request, db=Depends(get_db), q: Optional[str] = None, limit: int = 100, offset: int = 0):
    user = _get_user_from_session(db, _get_session_token(request))
    if not _is_admin(user):
        raise HTTPException(403)
    if q:
        rows = db.execute(_text("SELECT id,email,name,avatar_url,created_at FROM users WHERE email ILIKE :q OR name ILIKE :q ORDER BY created_at DESC LIMIT :limit OFFSET :offset"), {"q": f"%{q}%", "limit": limit, "offset": offset}).mappings().all()
    else:
        rows = db.execute(_text("SELECT id,email,name,avatar_url,created_at FROM users ORDER BY created_at DESC LIMIT :limit OFFSET :offset"), {"limit": limit, "offset": offset}).mappings().all()
    return {"items": rows}

@app.get("/videos/{video_id}/youtube-transcript", response_model=YouTubeTranscriptResponse)
def get_youtube_transcript(video_id: uuid.UUID, db=Depends(get_db)):
    yt = crud.get_youtube_transcript(db, video_id)
    if not yt:
        raise HTTPException(404, "No YouTube transcript")
    segs = crud.list_youtube_segments(db, yt["id"])
    return YouTubeTranscriptResponse(
        video_id=video_id,
        language=yt.get("language"),
        kind=yt.get("kind"),
        full_text=yt.get("full_text"),
        segments=[YTSegment(start_ms=r[0], end_ms=r[1], text=r[2]) for r in segs],
    )

def _fmt_time_ms(ms: int) -> str:
    """Format milliseconds into SRT timestamp HH:MM:SS,mmm"""
    s, ms_rem = divmod(int(ms), 1000)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"

def _export_allowed_or_402(db, request: Request, user):
    # Pro users and admins allowed
    if user and (_is_admin(user) or (user.get("plan") or "free").lower() == settings.PRO_PLAN_NAME.lower()):
        return None
    # For free users, enforce soft daily export limit
    uid = str(user["id"]) if user else None
    if uid:
        used = db.execute(text("""
            SELECT COUNT(*) FROM events
            WHERE user_id=:u AND type='export'
              AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC')
        """), {"u": uid}).scalar_one()
        if used >= settings.FREE_DAILY_EXPORT_LIMIT:
            return JSONResponse({"error": "upgrade_required", "message": "Daily export limit reached. Upgrade to Pro."}, status_code=402)
    else:
        # Unauthed cannot export
        return JSONResponse({"error": "auth_required", "message": "Login required to export."}, status_code=401)
    return None

def _log_export(db, request: Request, user, payload: dict):
    """Record an export event for quota accounting"""
    db.execute(text("INSERT INTO events (user_id, session_token, type, payload) VALUES (:u,:t,'export',:p)"), {"u": str(user["id"]) if user else None, "t": _get_session_token(request), "p": payload})
    db.commit()

@app.get("/videos/{video_id}/youtube-transcript.srt")
def get_youtube_transcript_srt(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    gate = _export_allowed_or_402(db, request, user, redirect_to=f"{settings.FRONTEND_ORIGIN}/upgrade?redirect=/v/{video_id}")
    if gate is not None:
        return gate
    yt = crud.get_youtube_transcript(db, video_id)
    if not yt:
        raise HTTPException(404, "No YouTube transcript")
    segs = crud.list_youtube_segments(db, yt["id"])
    lines = []
    for i, (start_ms, end_ms, text) in enumerate(segs, start=1):
        lines.append(str(i))
        lines.append(f"{_fmt_time_ms(start_ms)} --> {_fmt_time_ms(end_ms)}")
        lines.append(text)
        lines.append("")
    body = "\n".join(lines)
    _log_export(db, request, user, {"format": "srt", "source": "youtube", "video_id": str(video_id)})
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}.youtube.srt"}
    return Response(content=body, media_type="text/plain", headers=headers)

@app.get("/videos/{video_id}/youtube-transcript.vtt")
def get_youtube_transcript_vtt(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    gate = _export_allowed_or_402(db, request, user, redirect_to=f"{settings.FRONTEND_ORIGIN}/upgrade?redirect=/v/{video_id}")
    if gate is not None:
        return gate
    yt = crud.get_youtube_transcript(db, video_id)
    if not yt:
        raise HTTPException(404, "No YouTube transcript")
    segs = crud.list_youtube_segments(db, yt["id"])
    def vtt_time(ms: int) -> str:
        s, ms = divmod(ms, 1000)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        # VTT uses dot for milliseconds and can omit hours if 0, but we keep HH:MM:SS.mmm
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
    lines = ["WEBVTT", ""]
    for (start_ms, end_ms, text) in segs:
        lines.append(f"{vtt_time(start_ms)} --> {vtt_time(end_ms)}")
        lines.append(text)
        lines.append("")
    body = "\n".join(lines)
    _log_export(db, request, user, {"format": "vtt", "source": "youtube", "video_id": str(video_id)})
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}.youtube.vtt"}
    return Response(content=body, media_type="text/vtt", headers=headers)

@app.get("/videos/{video_id}/transcript.srt")
def get_native_transcript_srt(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    gate = _export_allowed_or_402(db, request, user, redirect_to=f"{settings.FRONTEND_ORIGIN}/upgrade?redirect=/v/{video_id}")
    if gate is not None:
        return gate
    segs = crud.list_segments(db, video_id)
    if not segs:
        raise HTTPException(404, "No segments")
    lines = []
    for i, (start_ms, end_ms, text, _speaker) in enumerate(segs, start=1):
        lines.append(str(i))
        lines.append(f"{_fmt_time_ms(start_ms)} --> {_fmt_time_ms(end_ms)}")
        lines.append(text)
        lines.append("")
    body = "\n".join(lines)
    _log_export(db, request, user, {"format": "srt", "source": "native", "video_id": str(video_id)})
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}.srt"}
    return Response(content=body, media_type="text/plain", headers=headers)

@app.get("/videos/{video_id}/transcript.vtt")
def get_native_transcript_vtt(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    gate = _export_allowed_or_402(db, request, user, redirect_to=f"{settings.FRONTEND_ORIGIN}/upgrade?redirect=/v/{video_id}")
    if gate is not None:
        return gate
    segs = crud.list_segments(db, video_id)
    if not segs:
        raise HTTPException(404, "No segments")
    def vtt_time(ms: int) -> str:
        s, ms = divmod(ms, 1000)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
    lines = ["WEBVTT", ""]
    for (start_ms, end_ms, text, _speaker) in segs:
        lines.append(f"{vtt_time(start_ms)} --> {vtt_time(end_ms)}")
        lines.append(text)
        lines.append("")
    body = "\n".join(lines)
    _log_export(db, request, user, {"format": "vtt", "source": "native", "video_id": str(video_id)})
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}.vtt"}
    return Response(content=body, media_type="text/vtt", headers=headers)

@app.get("/videos/{video_id}/transcript.json")
def get_native_transcript_json(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    gate = _export_allowed_or_402(db, request, user, redirect_to=f"{settings.FRONTEND_ORIGIN}/upgrade?redirect=/v/{video_id}")
    if gate is not None:
        return gate
    segs = crud.list_segments(db, video_id)
    if not segs:
        raise HTTPException(404, "No segments")
    payload = [{"start_ms": r[0], "end_ms": r[1], "text": r[2], "speaker_label": r[3]} for r in segs]
    _log_export(db, request, user, {"format": "json", "source": "native", "video_id": str(video_id)})
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}.json"}
    return JSONResponse(payload, headers=headers)

@app.get("/videos/{video_id}/youtube-transcript.json")
def get_youtube_transcript_json(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    gate = _export_allowed_or_402(db, request, user, redirect_to=f"{settings.FRONTEND_ORIGIN}/upgrade?redirect=/v/{video_id}")
    if gate is not None:
        return gate
    yt = crud.get_youtube_transcript(db, video_id)
    if not yt:
        raise HTTPException(404, "No YouTube transcript")
    segs = crud.list_youtube_segments(db, yt["id"])
    payload = [{"start_ms": r[0], "end_ms": r[1], "text": r[2]} for r in segs]
    _log_export(db, request, user, {"format": "json", "source": "youtube", "video_id": str(video_id)})
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}.youtube.json"}
    return JSONResponse(payload, headers=headers)

@app.get("/videos/{video_id}/transcript.pdf")
def get_native_transcript_pdf(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    gate = _export_allowed_or_402(db, request, user, redirect_to=f"{settings.FRONTEND_ORIGIN}/upgrade?redirect=/v/{video_id}")
    if gate is not None:
        return gate
    segs = crud.list_segments(db, video_id)
    if not segs:
        raise HTTPException(404, "No segments")
    # Build PDF in-memory
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, leftMargin=0.9*inch, rightMargin=0.9*inch, topMargin=1.1*inch, bottomMargin=0.9*inch)
    styles = getSampleStyleSheet()
    # Register a serif font with priority: settings.PDF_FONT_PATH -> DejaVuSerif -> Times-Roman
    base_font = 'Times-Roman'
    if settings.PDF_FONT_PATH:
        try:
            pdfmetrics.registerFont(TTFont('CustomSerif', settings.PDF_FONT_PATH))
            base_font = 'CustomSerif'
        except Exception:
            pass
    if base_font == 'Times-Roman':
        try:
            pdfmetrics.registerFont(TTFont('DejaVuSerif', '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf'))
            base_font = 'DejaVuSerif'
        except Exception:
            pass
    heading = ParagraphStyle(name='Heading', parent=styles['Heading2'], fontName=base_font, textColor=colors.black, spaceAfter=12)
    body = ParagraphStyle(name='Body', parent=styles['BodyText'], fontName=base_font, fontSize=11, leading=15)
    time = ParagraphStyle(name='Time', parent=styles['BodyText'], fontName=base_font, fontSize=9, textColor=colors.grey, spaceAfter=2)
    story: list = []
    # Title and header/footer + metadata
    v = crud.get_video(db, video_id)
    title = (v.get('title') if v else None) or f"Transcript {video_id}"
    duration = v.get('duration_seconds') if v else None
    platform = 'YouTube'
    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    story.append(Paragraph(title, heading))
    story.append(Spacer(1, 6))
    # Segments
    for (start_ms, _end_ms, text, speaker) in segs:
        hhmmss = _fmt_time_ms(start_ms).replace(',', '.')
        ts = Paragraph(hhmmss, time)
        story.append(ts)
        content = text if text else ''
        if speaker:
            content = f"<b>{speaker}:</b> {content}"
        story.append(Paragraph(content, body))
        story.append(Spacer(1, 4))
    # Header/footer drawing
    def _header_footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont(base_font, 9)
        # Header title
        canvas.setFillColor(colors.grey)
        canvas.drawString(doc.leftMargin, doc.height + doc.topMargin - 0.6*inch, title)
        # Metadata line (right-aligned)
        meta = []
        if duration:
            h = duration // 3600; m = (duration % 3600) // 60; s = duration % 60
            meta.append(f"{h:02d}:{m:02d}:{s:02d}")
        meta.append(platform)
        meta.append(date_str)
        canvas.drawRightString(doc.width + doc.leftMargin, doc.height + doc.topMargin - 0.6*inch, " • ".join(meta))
        # Footer page number
        page = canvas.getPageNumber()
        canvas.drawRightString(doc.width + doc.leftMargin, 0.5*inch, f"Page {page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    pdf = buf.getvalue(); buf.close()
    _log_export(db, request, user, {"format": "pdf", "source": "native", "video_id": str(video_id)})
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}.pdf"}
    return Response(content=pdf, media_type="application/pdf", headers=headers)

@app.get("/search", response_model=SearchResponse)
def search(request: Request, q: str, source: str = "native", video_id: Optional[uuid.UUID] = None, limit: int = 50, offset: int = 0, db=Depends(get_db)):
    # Quota enforcement for free users: limit daily searches
    # Only applies to authenticated users on free plan; unauthenticated allowed but can be tightened later
    # Fetch user from session
    # Note: we don't block admin users
    # Enforce daily search quota for free plan
    if not q or not q.strip():
        raise HTTPException(400, "Missing query parameter 'q'")
    if source not in ("native", "youtube"):
        raise HTTPException(400, "Invalid source. Use 'native' or 'youtube'")
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be between 1 and 200")
    user = _get_user_from_session(db, _get_session_token(request))
    if user and not _is_admin(user):
        plan = (user.get("plan") or "free").lower()
        if plan == "free":
            used = db.execute(text("""
                SELECT COUNT(*) FROM events
                WHERE user_id=:u AND type='search_api'
                  AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC')
            """), {"u": str(user["id"]) }).scalar_one()
            if used >= settings.FREE_DAILY_SEARCH_LIMIT:
                return JSONResponse({
                    "error": "quota_exceeded",
                    "message": "Daily search limit reached. Upgrade to Pro for unlimited search.",
                    "plan": plan,
                    "used": used,
                    "limit": settings.FREE_DAILY_SEARCH_LIMIT,
                }, status_code=402)
            # Record this search usage
            db.execute(_text("INSERT INTO events (user_id, session_token, type, payload) VALUES (:u,:t,'search_api',:p)"), {
                "u": str(user["id"]),
                "t": _get_session_token(request),
                "p": {"q": q, "source": source}
            })
            db.commit()
    if settings.SEARCH_BACKEND == "opensearch":
        # OpenSearch path: query the selected index with a simple match query and return hits
        index = settings.OPENSEARCH_INDEX_NATIVE if source == "native" else settings.OPENSEARCH_INDEX_YOUTUBE
        query = {
            "from": offset,
            "size": limit,
            "query": {
                "bool": {
                    "should": [
                        {"multi_match": {"query": q, "type": "phrase", "fields": ["text^3", "text.shingle^4"]}},
                        {"multi_match": {"query": q, "fields": ["text^2", "text.ngram^0.5", "text.edge^1.5"]}},
                        {"prefix": {"text.edge": {"value": q.lower(), "boost": 1.2}}}
                    ],
                    "minimum_should_match": 1
                }
            },
            "highlight": {
                "fields": {"text": {"number_of_fragments": 3, "fragment_size": 180}}
            }
        }
        if video_id:
            query["query"]["bool"].setdefault("filter", []).append({"term": {"video_id": str(video_id)}})
        try:
            r = requests.post(f"{settings.OPENSEARCH_URL}/{index}/_search", json=query, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise HTTPException(500, f"OpenSearch query failed: {e}")
        hits = []
        for h in data.get("hits", {}).get("hits", []):
            src = h.get("_source", {})
            hl = h.get("highlight", {}).get("text", [src.get("text", "")])
            hits.append(SearchHit(
                id=int(src.get("id")),
                video_id=uuid.UUID(src.get("video_id")),
                start_ms=int(src.get("start_ms", 0)),
                end_ms=int(src.get("end_ms", 0)),
                snippet=hl[0]
            ))
        total = data.get("hits", {}).get("total", {}).get("value") if isinstance(data.get("hits", {}).get("total"), dict) else None
        return SearchResponse(total=total, hits=hits)
    # Default Postgres FTS path
    if source == "native":
        rows = crud.search_segments(db, q=q, video_id=str(video_id) if video_id else None, limit=limit, offset=offset)
    else:
        rows = crud.search_youtube_segments(db, q=q, video_id=str(video_id) if video_id else None, limit=limit, offset=offset)
    hits = [SearchHit(id=r["id"], video_id=r["video_id"], start_ms=r["start_ms"], end_ms=r["end_ms"], snippet=r["snippet"] or "") for r in rows]
    return SearchResponse(hits=hits)

@app.post("/admin/users/{user_id}/plan")
def admin_set_user_plan(user_id: uuid.UUID, payload: dict, request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    if not _is_admin(user):
        raise HTTPException(403)
    plan = (payload.get("plan") or "").lower()
    if plan not in ("free", settings.PRO_PLAN_NAME.lower()):
        raise HTTPException(400, f"Invalid plan. Use 'free' or '{settings.PRO_PLAN_NAME}'.")
    db.execute(_text("UPDATE users SET plan=:p, updated_at=now() WHERE id=:i"), {"p": plan, "i": str(user_id)})
    db.commit()
    return {"ok": True, "user_id": str(user_id), "plan": plan}

def _row_to_status(row):
    return JobStatus(
        id=row["id"],
        kind=row["kind"],
        state=row["state"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"]
    )
