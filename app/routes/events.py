from fastapi import APIRouter, Depends, Request
from sqlalchemy import text as _text

from ..common.session import get_session_token as _get_session_token
from ..common.session import get_user_from_session as _get_user_from_session
from ..db import get_db

router = APIRouter(prefix="", tags=["Events"])


@router.post(
    "/events",
    summary="Track client event",
    description="""
    Track a client-side event for analytics.
    
    Events are stored with optional user association for authenticated users.
    
    Request body:
    ```json
    {
        "type": "event_type",
        "payload": {"custom": "data"}
    }
    ```
    """,
    responses={200: {"description": "Event tracked", "content": {"application/json": {"example": {"ok": True}}}}},
)
def ingest_event(payload: dict, request: Request, db=Depends(get_db)):
    """Ingest a client-side event."""
    tok = _get_session_token(request)
    user = _get_user_from_session(db, tok)
    etype = payload.get("type") or "unknown"
    data = payload.get("payload") or {}
    db.execute(
        _text("INSERT INTO events (user_id, session_token, type, payload) VALUES (:u,:t,:ty,:p)"),
        {"u": str(user["id"]) if user else None, "t": tok, "ty": etype, "p": data},
    )
    db.commit()
    return {"ok": True}


@router.post(
    "/events/batch",
    summary="Track multiple events",
    description="""
    Track multiple client-side events in a single request.
    
    Request body:
    ```json
    {
        "events": [
            {"type": "event1", "payload": {}},
            {"type": "event2", "payload": {}}
        ]
    }
    ```
    """,
    responses={
        200: {
            "description": "Events tracked",
            "content": {"application/json": {"example": {"ok": True, "count": 2}}},
        }
    },
)
def ingest_events_batch(payload: dict, request: Request, db=Depends(get_db)):
    """Ingest multiple client-side events in batch."""
    tok = _get_session_token(request)
    user = _get_user_from_session(db, tok)
    events = payload.get("events") or []
    for e in events:
        etype = e.get("type") or "unknown"
        data = e.get("payload") or {}
        db.execute(
            _text("INSERT INTO events (user_id, session_token, type, payload) VALUES (:u,:t,:ty,:p)"),
            {"u": str(user["id"]) if user else None, "t": tok, "ty": etype, "p": data},
        )
    db.commit()
    return {"ok": True, "count": len(events)}
