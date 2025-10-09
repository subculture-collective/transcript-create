from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text as _text
import uuid
from ..db import get_db
from ..common.session import get_session_token as _get_session_token, get_user_from_session as _get_user_from_session

router = APIRouter()

@router.get("/users/me/favorites")
def list_favorites(request: Request, db=Depends(get_db), video_id: uuid.UUID | None = None):
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise HTTPException(401)
    if video_id:
        rows = db.execute(_text("SELECT id, video_id, start_ms, end_ms, text, created_at FROM favorites WHERE user_id=:u AND video_id=:v ORDER BY created_at DESC"), {"u": str(user["id"]), "v": str(video_id)}).mappings().all()
    else:
        rows = db.execute(_text("SELECT id, video_id, start_ms, end_ms, text, created_at FROM favorites WHERE user_id=:u ORDER BY created_at DESC"), {"u": str(user["id"]) }).mappings().all()
    return {"items": rows}

@router.post("/users/me/favorites")
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

@router.delete("/users/me/favorites/{favorite_id}")
def delete_favorite(favorite_id: uuid.UUID, request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise HTTPException(401)
    db.execute(_text("DELETE FROM favorites WHERE id=:i AND user_id=:u"), {"i": str(favorite_id), "u": str(user["id"])})
    db.commit()
    return {"ok": True}
