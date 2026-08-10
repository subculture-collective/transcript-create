"""Self-service profile, identity, and session endpoints."""

from datetime import datetime
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from ..accounts import (
    FinalAdminError,
    delete_prepared_account,
    discard_prepared_account_deletion,
    list_identities,
    prepare_account_deletion,
    unlink_identity,
    update_profile,
)
from ..audit import (
    ACTION_IDENTITY_UNLINKED,
    ACTION_PROFILE_UPDATED,
    ACTION_SESSION_REVOKED,
    ACTION_SESSIONS_REVOKED,
    ACTION_USER_DATA_DELETION,
    write_audit_event,
)
from ..common.session import clear_session_cookie, get_session_token
from ..db import get_db
from ..exceptions import DatabaseError, NotFoundError
from ..security import require_auth

router = APIRouter(prefix="/account", tags=["Account"])


class ProfileUpdate(BaseModel):
    name: str
    avatar_url: str | None = Field(default=None, max_length=2048)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not 1 <= len(value) <= 100:
            raise ValueError("Name must be between 1 and 100 characters")
        return value

    @field_validator("avatar_url", mode="before")
    @classmethod
    def validate_avatar(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError("Avatar URL must be an absolute https URL")
        return value


class AccountUserResponse(BaseModel):
    id: UUID
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    role: str | None = None
    plan: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IdentityResponse(BaseModel):
    id: UUID
    provider: str
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class SessionResponse(BaseModel):
    id: UUID
    user_agent: str
    created_at: datetime | None = None
    last_seen_at: datetime | None = None
    expires_at: datetime | None = None
    current: bool


class AccountResponse(BaseModel):
    user: AccountUserResponse
    identities: list[IdentityResponse]
    sessions: list[SessionResponse]


class ProfileResponse(BaseModel):
    user: AccountUserResponse


class IdentitiesResponse(BaseModel):
    identities: list[IdentityResponse]


class LinkResponse(BaseModel):
    authorization_url: str


class SessionsResponse(BaseModel):
    sessions: list[SessionResponse]


class OkResponse(BaseModel):
    ok: bool


class RevokedResponse(BaseModel):
    revoked: int


class AccountDeletionRequest(BaseModel):
    confirmation: Literal["DELETE"]


class AccountDeletionResponse(BaseModel):
    deleted: bool


def _user_response(user: dict) -> dict:
    return {
        key: user.get(key) for key in ("id", "email", "name", "avatar_url", "role", "plan", "created_at", "updated_at")
    }


def _identity_response(identity: dict) -> dict:
    return {
        "id": identity["id"],
        "provider": identity["provider"],
        "email": identity.get("provider_email"),
        "name": identity.get("provider_name"),
        "avatar_url": identity.get("provider_avatar_url"),
        "created_at": identity.get("created_at"),
        "last_login_at": identity.get("last_login_at"),
    }


def _session_response(session: dict, current_hash: str) -> dict:
    user_agent = session.get("user_agent") or "Unknown device"
    return {
        "id": session["id"],
        "user_agent": user_agent.split(" ", 1)[0][:100],
        "created_at": session.get("created_at"),
        "last_seen_at": session.get("last_seen_at"),
        "expires_at": session.get("expires_at"),
        "current": session["token_hash"] == current_hash,
    }


def _sessions(db, user_id, token: str) -> list[dict]:
    from ..accounts import session_token_hash

    rows = (
        db.execute(
            text(
                "SELECT id, token_hash, user_agent, created_at, last_seen_at, expires_at FROM sessions WHERE user_id=:user_id AND (expires_at IS NULL OR expires_at > now()) ORDER BY created_at DESC"
            ),
            {"user_id": str(user_id)},
        )
        .mappings()
        .all()
    )
    current_hash = session_token_hash(token)
    return [_session_response(dict(row), current_hash) for row in rows]


@router.get("", response_model=AccountResponse)
def get_account(request: Request, db=Depends(get_db), user=Depends(require_auth)):
    token = get_session_token(request) or ""
    return {
        "user": _user_response(user),
        "identities": [_identity_response(row) for row in list_identities(db, user["id"])],
        "sessions": _sessions(db, user["id"], token),
    }


@router.patch("", response_model=ProfileResponse)
def patch_account(body: ProfileUpdate, request: Request, db=Depends(get_db), user=Depends(require_auth)):
    try:
        updated = update_profile(db, user["id"], name=body.name, avatar_url=body.avatar_url)
        write_audit_event(
            db,
            ACTION_PROFILE_UPDATED,
            user_id=user["id"],
            resource_type="user",
            resource_id=str(user["id"]),
            details={"fields": ["name", "avatar_url"]},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise DatabaseError("Profile could not be updated") from None
    return {"user": _user_response(updated)}


@router.get("/identities", response_model=IdentitiesResponse)
def get_identities(db=Depends(get_db), user=Depends(require_auth)):
    return {"identities": [_identity_response(row) for row in list_identities(db, user["id"])]}


@router.post("/identities/{provider}/link", response_model=LinkResponse)
async def link_provider(provider: str, request: Request, db=Depends(get_db), user=Depends(require_auth)):
    from .auth import _start_oauth_link

    return {"authorization_url": await _start_oauth_link(request, db, provider, user["id"])}


@router.post("/identities/{provider}/merge", response_model=LinkResponse)
async def merge_provider(provider: str, request: Request, db=Depends(get_db), user=Depends(require_auth)):
    """Start a fresh OAuth proof before merging a separately created account."""
    from .auth import _start_oauth_link

    return {"authorization_url": await _start_oauth_link(request, db, provider, user["id"], merge=True)}


@router.delete("/identities/{provider}", response_model=OkResponse)
def delete_identity(provider: str, request: Request, db=Depends(get_db), user=Depends(require_auth)):
    exists = db.execute(
        text("SELECT 1 FROM user_identities WHERE user_id=:user_id AND provider=:provider"),
        {"user_id": str(user["id"]), "provider": provider},
    ).first()
    if not exists:
        raise NotFoundError("Identity not found")
    unlink_identity(db, user["id"], provider)
    write_audit_event(
        db,
        ACTION_IDENTITY_UNLINKED,
        user_id=user["id"],
        details={"provider": provider},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return {"ok": True}


@router.get("/sessions", response_model=SessionsResponse)
def get_sessions(request: Request, db=Depends(get_db), user=Depends(require_auth)):
    return {"sessions": _sessions(db, user["id"], get_session_token(request) or "")}


@router.delete("/sessions", response_model=RevokedResponse)
def revoke_sessions(request: Request, keep_current: bool = Query(True), db=Depends(get_db), user=Depends(require_auth)):
    from ..accounts import session_token_hash

    current_hash = session_token_hash(get_session_token(request) or "")
    query = "DELETE FROM sessions WHERE user_id=:user_id"
    params = {"user_id": str(user["id"])}
    if keep_current:
        query += " AND token_hash != :token_hash"
        params["token_hash"] = current_hash
    try:
        revoked = db.execute(text(query + " RETURNING id"), params).rowcount
        write_audit_event(
            db,
            ACTION_SESSIONS_REVOKED,
            user_id=user["id"],
            resource_type="session",
            details={"keep_current": keep_current, "revoked": revoked},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise DatabaseError("Sessions could not be revoked") from None
    response = JSONResponse({"revoked": revoked})
    if not keep_current:
        clear_session_cookie(response)
    return response


@router.delete("/sessions/{session_id}", response_model=OkResponse)
def revoke_session(session_id: UUID, request: Request, db=Depends(get_db), user=Depends(require_auth)):
    from ..accounts import session_token_hash

    row = (
        db.execute(
            text("DELETE FROM sessions WHERE id=:id AND user_id=:user_id RETURNING token_hash"),
            {"id": str(session_id), "user_id": str(user["id"])},
        )
        .mappings()
        .first()
    )
    if not row:
        raise NotFoundError("Session not found")
    try:
        write_audit_event(
            db,
            ACTION_SESSION_REVOKED,
            user_id=user["id"],
            resource_type="session",
            resource_id=str(session_id),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise DatabaseError("Session could not be revoked") from None
    response = JSONResponse({"ok": True})
    if row["token_hash"] == session_token_hash(get_session_token(request) or ""):
        clear_session_cookie(response)
    return response


@router.delete("", response_model=AccountDeletionResponse)
def remove_account(body: AccountDeletionRequest, request: Request, db=Depends(get_db), user=Depends(require_auth)):
    """Delete the authenticated account in one request-owned transaction."""
    del body
    prepared = None
    try:
        prepared = prepare_account_deletion(db, user["id"])
        # The prepared context holds the account and ownership locks. The scrub
        # below retains the operational fact while removing identity data.
        write_audit_event(
            db,
            ACTION_USER_DATA_DELETION,
            user_id=user["id"],
            resource_type="user",
            resource_id=str(user["id"]),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        delete_prepared_account(db, prepared)
        prepared = None
        db.commit()
    except FinalAdminError:
        try:
            db.rollback()
        finally:
            discard_prepared_account_deletion(prepared)
        raise
    except Exception:
        try:
            db.rollback()
        finally:
            discard_prepared_account_deletion(prepared)
        raise DatabaseError("Account could not be deleted") from None
    response = JSONResponse({"deleted": True})
    clear_session_cookie(response)
    return response
