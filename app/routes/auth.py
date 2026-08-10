import uuid
from hashlib import sha256
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import text

from ..accounts import (
    AccountMergeConflictError,
    IdentityConflictError,
    create_session,
    link_identity,
    merge_account_identity,
    session_token_hash,
    sign_in_identity,
)
from ..audit import (
    ACTION_ACCOUNTS_MERGED,
    ACTION_IDENTITY_COLLISION,
    ACTION_IDENTITY_LINKED,
    ACTION_LOGIN_FAILED,
    ACTION_LOGIN_SUCCESS,
    ACTION_LOGOUT,
    log_audit_from_request,
    write_audit_event,
)
from ..auth.providers import exchange_and_normalize_profile, get_provider, register_provider
from ..common.session import clear_session_cookie as _clear_session_cookie
from ..common.session import get_session_token as _get_session_token
from ..common.session import get_user_from_session as _get_user_from_session
from ..common.session import refresh_session as _refresh_session
from ..common.session import set_session_cookie as _set_session_cookie
from ..common.session import should_refresh_session as _should_refresh_session
from ..db import get_db
from ..exceptions import DatabaseError, ExternalServiceError, ValidationError
from ..logging_config import get_logger
from ..policy import capabilities_for_role
from ..security import generate_nonce, generate_oauth_state, get_user_role
from ..settings import settings

logger = get_logger(__name__)

try:
    from authlib.common.errors import AuthlibBaseError
    from authlib.integrations.starlette_client import OAuth
    from authlib.oauth2.rfc6749.errors import OAuth2Error
except Exception:
    OAuth = None
    AuthlibBaseError = None
    OAuth2Error = None

router = APIRouter(prefix="", tags=["Auth"])


class AuthMeUserResponse(BaseModel):
    id: uuid.UUID
    email: str | None
    name: str | None
    avatar_url: str | None
    plan: str


class AuthMeResponse(BaseModel):
    user: AuthMeUserResponse | None
    role: Literal["user", "moderator", "admin"] | None
    capabilities: list[str]


class CsrfTokenResponse(BaseModel):
    csrf_token: str


def _new_oauth():
    if not OAuth:
        return None
    oauth = OAuth()
    register_provider(oauth, get_provider("twitch"))
    return oauth


def _hash_oauth_value(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


async def _start_oauth_login(request: Request, db, provider_name: str, *, intent: str = "login", link_user_id=None):
    if not OAuth:
        raise ExternalServiceError("OAuth", "Authentication library not installed")
    provider = get_provider(provider_name)
    if not provider.enabled:
        raise ExternalServiceError(provider.name.title(), "Provider is not configured")
    state, nonce = generate_oauth_state(), generate_nonce()
    try:
        # Keep a small, indexed cleanup batch in the same transaction as the
        # new binding so it cannot interfere with a successful initiation.
        db.execute(text("""
            DELETE FROM oauth_requests
            WHERE id IN (
                SELECT id FROM oauth_requests
                WHERE expires_at <= now()
                ORDER BY expires_at
                LIMIT 100
            )
        """))
        db.execute(
            text("""
            INSERT INTO oauth_requests
                (state_hash, nonce_hash, provider, intent, link_user_id, expires_at)
            VALUES
                (:state_hash, :nonce_hash, :provider, :intent, :link_user_id,
                 now() + interval '10 minutes')
        """),
            {
                "state_hash": _hash_oauth_value(state),
                "nonce_hash": _hash_oauth_value(nonce),
                "provider": provider.name,
                "intent": intent,
                "link_user_id": str(link_user_id) if link_user_id else None,
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(
            "OAuth request persistence failed", extra={"provider": provider_name, "error_type": type(exc).__name__}
        )
        raise DatabaseError("Authentication could not be started") from None
    # Authlib's session state supports its protocol checks; this durable row is
    # authoritative for provider binding and single use.
    request.session["oauth_state"] = state
    request.session["oauth_nonce"] = nonce
    oauth = OAuth()
    register_provider(oauth, provider)
    try:
        return await getattr(oauth, provider.name).authorize_redirect(
            request, provider.redirect_uri, state=state, nonce=nonce
        )
    except Exception as exc:
        # Provider failures may include authorization URLs, state, or nonce in
        # their messages.  Keep every outward-facing sink to stable metadata.
        logger.error(
            "OAuth initiation failed",
            extra={"provider": provider.name, "error_type": type(exc).__name__},
        )
        log_audit_from_request(
            db,
            request,
            ACTION_LOGIN_FAILED,
            success=False,
            details={"provider": provider.name, "reason": "provider_initiation_failed"},
        )
        raise ExternalServiceError(
            provider.name.title(),
            "Authentication could not be started",
            details={"code": "oauth_initiation_failed"},
        ) from None


async def _start_oauth_link(request: Request, db, provider_name: str, user_id, *, merge: bool = False) -> str:
    response = await _start_oauth_login(
        request,
        db,
        provider_name,
        intent="merge" if merge else "link",
        link_user_id=user_id,
    )
    location = response.headers["location"]
    if not isinstance(location, str):
        raise RuntimeError("OAuth provider did not return a redirect location")
    return location


def _consume_oauth_request(db, request: Request, provider_name: str):
    state = request.query_params.get("state")
    if not state:
        raise ValidationError("Invalid OAuth state parameter")
    try:
        row = (
            db.execute(
                text("""
            UPDATE oauth_requests SET consumed_at = now()
            WHERE state_hash = :state_hash AND consumed_at IS NULL AND expires_at > now()
            RETURNING *
        """),
                {"state_hash": _hash_oauth_value(state)},
            )
            .mappings()
            .first()
        )
        if not row:
            db.rollback()
            raise ValidationError("Invalid OAuth state parameter")
        # The consume must survive any later provider or account failure.
        db.commit()
    except ValidationError:
        raise
    except Exception as exc:
        db.rollback()
        logger.error(
            "OAuth state consumption failed", extra={"provider": provider_name, "error_type": type(exc).__name__}
        )
        raise DatabaseError("Authentication state could not be verified") from None
    if row["provider"] != provider_name:
        raise ValidationError("Invalid OAuth state parameter")
    if row["intent"] in {"link", "merge"}:
        user = _get_user_from_session(db, _get_session_token(request))
        if not user or str(user["id"]) != str(row["link_user_id"]):
            raise ValidationError("Invalid OAuth state parameter")
    return row


@router.get(
    "/auth/me",
    summary="Get current user",
    response_model=AuthMeResponse,
    description="""
    Get the currently authenticated user's profile and account metadata.
    Returns `{"user": null}` if not authenticated.
    """,
    responses={
        200: {
            "description": "User information retrieved successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "authenticated": {
                            "value": {
                                "user": {
                                    "id": "123e4567-e89b-12d3-a456-426614174000",
                                    "email": "user@example.com",
                                    "name": "John Doe",
                                    "avatar_url": "https://example.com/avatar.jpg",
                                    "plan": "free",
                                },
                                "role": "user",
                                "capabilities": ["archive:read"],
                            }
                        },
                    }
                }
            },
        }
    },
)
def auth_me(request: Request, db=Depends(get_db)):
    """Get current authenticated user information."""
    token = _get_session_token(request)
    user = _get_user_from_session(db, token)

    # Check if session should be refreshed
    if user and token and _should_refresh_session(db, token):
        _refresh_session(db, token)

    if not user:
        return {"user": None, "role": None, "capabilities": []}
    plan = user.get("plan") or "free"
    role = get_user_role(user)
    return {
        "user": {
            "id": user["id"],
            "email": user.get("email"),
            "name": user.get("name"),
            "avatar_url": user.get("avatar_url"),
            "plan": plan,
        },
        "role": role,
        "capabilities": list(capabilities_for_role(role)),
    }


@router.get("/auth/csrf", response_model=CsrfTokenResponse)
def auth_csrf(request: Request, db=Depends(get_db)):
    """Return a token bound to the currently valid HttpOnly session cookie."""
    from ..common.session import get_user_from_session
    from ..csrf import csrf_token

    token = _get_session_token(request)
    if not token or not get_user_from_session(db, token):
        from ..exceptions import AuthenticationError

        raise AuthenticationError("Authentication required")
    return {"csrf_token": csrf_token(token)}


@router.get(
    "/auth/login/google",
    summary="Login with Google",
    description="""
    Initiate OAuth 2.0 login flow with Google.

    Redirects to Google's OAuth consent screen. After authorization,
    Google redirects back to /auth/callback/google.
    """,
    responses={
        307: {"description": "Redirect to Google OAuth consent screen"},
        503: {"description": "OAuth library not configured"},
    },
)
async def auth_login_google(request: Request, db=Depends(get_db)):
    """Initiate Google OAuth login."""
    return await _start_oauth_login(request, db, "google")


@router.get(
    "/auth/login/twitch",
    summary="Login with Twitch",
    description="""
    Initiate OAuth 2.0 login flow with Twitch.

    Redirects to Twitch's OAuth consent screen. After authorization,
    Twitch redirects back to /auth/callback/twitch.
    """,
    responses={
        307: {"description": "Redirect to Twitch OAuth consent screen"},
        503: {"description": "OAuth library not configured"},
    },
)
async def auth_login_twitch(request: Request, db=Depends(get_db)):
    """Initiate Twitch OAuth login."""
    return await _start_oauth_login(request, db, "twitch")


async def _oauth_callback(request: Request, db, provider_name: str):
    if not OAuth:
        raise ExternalServiceError("OAuth", "Authentication library not installed")
    provider = get_provider(provider_name)
    if not provider.enabled:
        raise ExternalServiceError(provider.name.title(), "Provider is not configured")
    try:
        binding = _consume_oauth_request(db, request, provider_name)
    except ValidationError:
        log_audit_from_request(
            db,
            request,
            ACTION_LOGIN_FAILED,
            success=False,
            details={"provider": provider_name, "reason": "state_validation_failed"},
        )
        raise
    except DatabaseError:
        log_audit_from_request(
            db,
            request,
            ACTION_LOGIN_FAILED,
            success=False,
            details={"provider": provider_name, "reason": "state_persistence_failed"},
        )
        raise
    request.session.pop("oauth_state", None)
    request.session.pop("oauth_nonce", None)
    try:
        oauth = OAuth()
        register_provider(oauth, provider)
        client = getattr(oauth, provider_name)
        profile = await exchange_and_normalize_profile(client, provider, request, binding["nonce_hash"])
    except (ValidationError, ExternalServiceError):
        log_audit_from_request(
            db,
            request,
            ACTION_LOGIN_FAILED,
            success=False,
            details={"provider": provider_name, "reason": "profile_validation_failed"},
        )
        raise
    except Exception as exc:
        logger.error("OAuth callback failed", extra={"provider": provider_name, "error_type": type(exc).__name__})
        log_audit_from_request(
            db,
            request,
            ACTION_LOGIN_FAILED,
            success=False,
            details={"provider": provider_name, "reason": "provider_callback_failed"},
        )
        raise ExternalServiceError(
            provider.name.title(), "Authentication failed", details={"code": "oauth_callback_failed"}
        )
    try:
        if binding["intent"] == "merge":
            user_id = binding["link_user_id"]
            merged = merge_account_identity(
                db,
                user_id,
                profile,
                user_agent=request.headers.get("user-agent"),
                ip_address=request.client.host if request.client else None,
            )
            write_audit_event(
                db,
                ACTION_ACCOUNTS_MERGED,
                user_id=user_id,
                resource_type="user",
                resource_id=str(user_id),
                details={"provider": provider_name, "source_user_id": merged.source_user_id},
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            db.commit()
            response = RedirectResponse(url=f"{settings.FRONTEND_ORIGIN.rstrip('/')}/account?merged={provider_name}")
            _set_session_cookie(response, merged.session_token)
            return response

        if binding["intent"] == "link":
            user_id = binding["link_user_id"]
            link_identity(db, user_id, profile)
            write_audit_event(
                db,
                ACTION_IDENTITY_LINKED,
                user_id=user_id,
                details={"provider": provider_name},
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            db.commit()
            return RedirectResponse(url=f"{settings.FRONTEND_ORIGIN.rstrip('/')}/account?linked={provider_name}")

        result = sign_in_identity(db, profile)
        session_token = create_session(
            db,
            result.user["id"],
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        write_audit_event(
            db,
            ACTION_LOGIN_SUCCESS,
            user_id=result.user["id"],
            success=True,
            details={"provider": provider_name},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    except (AccountMergeConflictError, IdentityConflictError):
        db.rollback()
        # A collision is meaningful operationally but does not disclose who
        # owns the identity to the linking account.
        try:
            write_audit_event(
                db,
                ACTION_IDENTITY_COLLISION,
                user_id=binding.get("link_user_id"),
                success=False,
                details={"provider": provider_name},
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            db.commit()
        except Exception:
            db.rollback()
        if binding["intent"] in {"link", "merge"}:
            error = "account_merge_conflict" if binding["intent"] == "merge" else "identity_conflict"
            return RedirectResponse(
                url=f"{settings.FRONTEND_ORIGIN.rstrip('/')}/account?error={error}&provider={provider_name}"
            )
        raise DatabaseError("Authentication could not be completed") from None
    except Exception as exc:
        db.rollback()
        # Never let SQLAlchemy render statement parameters (including the raw
        # legacy session token) to a client or log sink.
        logger.error(
            "OAuth account persistence failed", extra={"provider": provider_name, "error_type": type(exc).__name__}
        )
        log_audit_from_request(
            db,
            request,
            ACTION_LOGIN_FAILED,
            success=False,
            details={"provider": provider_name, "reason": "account_persistence_failed"},
        )
        raise DatabaseError("Authentication could not be completed") from None
    response = RedirectResponse(url=f"{settings.FRONTEND_ORIGIN.rstrip('/')}/")
    _set_session_cookie(response, session_token)
    return response


@router.get("/auth/callback/google")
async def auth_callback_google(request: Request, db=Depends(get_db)):
    return await _oauth_callback(request, db, "google")


@router.get("/auth/callback/twitch")
async def auth_callback_twitch(request: Request, db=Depends(get_db)):
    return await _oauth_callback(request, db, "twitch")


@router.post(
    "/auth/logout",
    summary="Logout",
    description="""
    Logout the current user by invalidating their session.

    Clears the session cookie and removes the session from the database.
    """,
    responses={
        200: {
            "description": "Logged out successfully",
            "content": {"application/json": {"example": {"ok": True}}},
        }
    },
)
def auth_logout(request: Request, db=Depends(get_db)):
    """Logout and invalidate session."""
    tok = _get_session_token(request)
    user = _get_user_from_session(db, tok) if tok else None

    if tok:
        try:
            db.execute(
                text("DELETE FROM sessions WHERE token_hash=:token_hash"), {"token_hash": session_token_hash(tok)}
            )
            if user:
                write_audit_event(
                    db,
                    ACTION_LOGOUT,
                    user_id=user.get("id"),
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("Logout persistence failed", extra={"error_type": type(exc).__name__})
            raise DatabaseError("Logout could not be completed") from None

    resp = JSONResponse({"ok": True})
    _clear_session_cookie(resp)
    return resp
