import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text as _text

from ..common.session import get_session_token as _get_session_token
from ..common.session import get_user_from_session as _get_user_from_session
from ..db import get_db
from ..exceptions import AuthenticationError, ValidationError

router = APIRouter(prefix="", tags=["Favorites"])


@router.get(
    "/users/me/favorites",
    summary="List user favorites",
    description="""
    Get all favorite transcript segments for the authenticated user.
    
    Optionally filter by video_id to get favorites for a specific video.
    
    **Authentication Required:** Yes
    """,
    responses={
        200: {
            "description": "List of favorites retrieved",
            "content": {
                "application/json": {
                    "example": {
                        "items": [
                            {
                                "id": "123e4567-e89b-12d3-a456-426614174000",
                                "video_id": "987e6543-e21b-34c5-b678-426614174999",
                                "start_ms": 10000,
                                "end_ms": 15000,
                                "text": "This is a favorite quote",
                                "created_at": "2025-10-25T10:30:00Z",
                            }
                        ]
                    }
                }
            },
        },
        401: {"description": "Authentication required"},
    },
)
def list_favorites(request: Request, db=Depends(get_db), video_id: uuid.UUID | None = None):
    """List favorite transcript segments."""
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise AuthenticationError()
    if video_id:
        rows = (
            db.execute(
                _text(
                    "SELECT id, video_id, start_ms, end_ms, text, created_at FROM favorites WHERE user_id=:u AND video_id=:v ORDER BY created_at DESC"  # noqa: E501
                ),
                {"u": str(user["id"]), "v": str(video_id)},
            )
            .mappings()
            .all()
        )
    else:
        rows = (
            db.execute(
                _text(
                    "SELECT id, video_id, start_ms, end_ms, text, created_at FROM favorites WHERE user_id=:u ORDER BY created_at DESC"  # noqa: E501
                ),
                {"u": str(user["id"])},
            )
            .mappings()
            .all()
        )
    return {"items": rows}


@router.post(
    "/users/me/favorites",
    summary="Add favorite segment",
    description="""
    Save a transcript segment as a favorite.
    
    Required fields:
    - `video_id`: UUID of the video
    - `start_ms`: Start time in milliseconds
    - `end_ms`: End time in milliseconds
    - `text`: The transcript text (optional)
    
    **Authentication Required:** Yes
    """,
    responses={
        200: {
            "description": "Favorite created",
            "content": {"application/json": {"example": {"id": "123e4567-e89b-12d3-a456-426614174000"}}},
        },
        400: {"description": "Invalid or missing required fields"},
        401: {"description": "Authentication required"},
    },
)
def add_favorite(payload: dict, request: Request, db=Depends(get_db)):
    """Add a favorite transcript segment."""
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise AuthenticationError()
    vid = payload.get("video_id")
    start = payload.get("start_ms")
    end = payload.get("end_ms")
    textv = payload.get("text")
    if not (vid and isinstance(start, int) and isinstance(end, int)):
        raise ValidationError("Missing or invalid required fields: video_id, start_ms, end_ms")
    fid = uuid.uuid4()
    db.execute(
        _text("INSERT INTO favorites (id,user_id,video_id,start_ms,end_ms,text) VALUES (:i,:u,:v,:s,:e,:t)"),
        {"i": str(fid), "u": str(user["id"]), "v": str(vid), "s": start, "e": end, "t": textv},
    )
    db.commit()
    return {"id": fid}


@router.delete(
    "/users/me/favorites/{favorite_id}",
    summary="Delete favorite",
    description="""
    Remove a favorite transcript segment.
    
    **Authentication Required:** Yes  
    **Authorization:** Can only delete your own favorites
    """,
    responses={
        200: {"description": "Favorite deleted", "content": {"application/json": {"example": {"ok": True}}}},
        401: {"description": "Authentication required"},
        404: {"description": "Favorite not found or not owned by user"},
    },
)
def delete_favorite(favorite_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Delete a favorite transcript segment."""
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise AuthenticationError()
    db.execute(_text("DELETE FROM favorites WHERE id=:i AND user_id=:u"), {"i": str(favorite_id), "u": str(user["id"])})
    db.commit()
    return {"ok": True}
