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
    return {"user": {"id": user["id"], "email": user.get("email"), "name": user.get("name"), "avatar_url": user.get("avatar_url")}}

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

@app.post("/auth/logout")
def auth_logout(request: Request, db=Depends(get_db)):
    tok = _get_session_token(request)
    if tok:
        db.execute(text("DELETE FROM sessions WHERE token=:t"), {"t": tok}); db.commit()
    resp = JSONResponse({"ok": True})
    _clear_session_cookie(resp)
    return resp

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
    s, ms = divmod(ms, 1000)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

@app.get("/videos/{video_id}/youtube-transcript.srt")
def get_youtube_transcript_srt(video_id: uuid.UUID, db=Depends(get_db)):
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
    return Response(content=body, media_type="text/plain")

@app.get("/videos/{video_id}/youtube-transcript.vtt")
def get_youtube_transcript_vtt(video_id: uuid.UUID, db=Depends(get_db)):
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
    return Response(content=body, media_type="text/vtt")

@app.get("/search", response_model=SearchResponse)
def search(q: str, source: str = "native", video_id: Optional[uuid.UUID] = None, limit: int = 50, offset: int = 0, db=Depends(get_db)):
    if not q or not q.strip():
        raise HTTPException(400, "Missing query parameter 'q'")
    if source not in ("native", "youtube"):
        raise HTTPException(400, "Invalid source. Use 'native' or 'youtube'")
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be between 1 and 200")
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

def _row_to_status(row):
    return JobStatus(
        id=row["id"],
        kind=row["kind"],
        state=row["state"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"]
    )
