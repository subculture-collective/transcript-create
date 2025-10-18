from fastapi import APIRouter, Depends, Request
from sqlalchemy import text as _text

from ..common.session import get_session_token as _get_session_token
from ..common.session import get_user_from_session as _get_user_from_session
from ..db import get_db

router = APIRouter()

@router.post("/events")
def ingest_event(payload: dict, request: Request, db=Depends(get_db)):
    tok = _get_session_token(request)
    user = _get_user_from_session(db, tok)
    etype = payload.get("type") or "unknown"
    data = payload.get("payload") or {}
    db.execute(_text("INSERT INTO events (user_id, session_token, type, payload) VALUES (:u,:t,:ty,:p)"), {"u": str(user["id"]) if user else None, "t": tok, "ty": etype, "p": data})
    db.commit()
    return {"ok": True}

@router.post("/events/batch")
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
