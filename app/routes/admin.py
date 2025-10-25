import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import text as _text

from ..common.session import get_session_token as _get_session_token
from ..common.session import get_user_from_session as _get_user_from_session
from ..common.session import is_admin as _is_admin
from ..db import get_db
from ..exceptions import AuthorizationError, ValidationError

router = APIRouter()


@router.get("/admin/events")
def admin_events(
    request: Request,
    db=Depends(get_db),
    type: str | None = None,
    user_email: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    user = _get_user_from_session(db, _get_session_token(request))
    if not _is_admin(user):
        raise AuthorizationError("Admin access required")
    where = []
    params: dict = {}
    if type:
        where.append("type = :type")
        params["type"] = type
    if user_email:
        where.append("user_id IN (SELECT id FROM users WHERE email=:email)")
        params["email"] = user_email
    if start:
        where.append("created_at >= :start")
        params["start"] = start
    if end:
        where.append("created_at <= :end")
        params["end"] = end
    sql = "SELECT id, created_at, user_id, session_token, type, payload FROM events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset
    rows = db.execute(_text(sql), params).mappings().all()
    return {"items": rows}


@router.get("/admin/events.csv")
def admin_events_csv(
    request: Request,
    db=Depends(get_db),
    type: str | None = None,
    user_email: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 1000,
    offset: int = 0,
):
    user = _get_user_from_session(db, _get_session_token(request))
    if not _is_admin(user):
        raise AuthorizationError("Admin access required")
    where = []
    params: dict = {}
    if type:
        where.append("type = :type")
        params["type"] = type
    if user_email:
        where.append("user_id IN (SELECT id FROM users WHERE email=:email)")
        params["email"] = user_email
    if start:
        where.append("created_at >= :start")
        params["start"] = start
    if end:
        where.append("created_at <= :end")
        params["end"] = end
    sql = "SELECT id, created_at, user_id, session_token, type, payload FROM events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset
    rows = db.execute(_text(sql), params).all()

    def esc(x):
        s = str(x) if x is not None else ""
        if any(c in s for c in [",", '"', "\n"]):
            s = '"' + s.replace('"', '""') + '"'
        return s

    header = "id,created_at,user_id,session_token,type,payload\n"
    body = "".join([f"{esc(r[0])},{esc(r[1])},{esc(r[2])},{esc(r[3])},{esc(r[4])},{esc(r[5])}\n" for r in rows])
    return PlainTextResponse(content=header + body, media_type="text/csv")


@router.get("/admin/events/summary")
def admin_events_summary(request: Request, db=Depends(get_db), start: str | None = None, end: str | None = None):
    user = _get_user_from_session(db, _get_session_token(request))
    if not _is_admin(user):
        raise AuthorizationError("Admin access required")
    params: dict = {}
    where: list[str] = []
    if start:
        where.append("created_at >= :start")
        params["start"] = start
    if end:
        where.append("created_at <= :end")
        params["end"] = end
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    by_type = db.execute(
        _text(f"SELECT type, COUNT(*) FROM events{where_sql} GROUP BY type ORDER BY COUNT(*) DESC"), params
    ).all()
    by_day = db.execute(
        _text(f"SELECT DATE(created_at) as day, COUNT(*) FROM events{where_sql} GROUP BY day ORDER BY day ASC"), params
    ).all()
    return {
        "by_type": [{"type": r[0], "count": r[1]} for r in by_type],
        "by_day": [{"day": str(r[0]), "count": r[1]} for r in by_day],
    }


@router.post("/admin/users/{user_id}/plan")
def admin_set_user_plan(user_id: uuid.UUID, payload: dict, request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    if not _is_admin(user):
        raise AuthorizationError("Admin access required")
    from ..settings import settings as _settings

    plan = (payload.get("plan") or "").lower()
    if plan not in ("free", _settings.PRO_PLAN_NAME.lower()):
        raise ValidationError(f"Invalid plan. Use 'free' or '{_settings.PRO_PLAN_NAME}'.", field="plan")
    db.execute(_text("UPDATE users SET plan=:p, updated_at=now() WHERE id=:i"), {"p": plan, "i": str(user_id)})
    db.commit()
    return {"ok": True, "user_id": str(user_id), "plan": plan}
