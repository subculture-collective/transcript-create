"""Security utilities including RBAC, authentication helpers, and security functions."""

import hashlib
import secrets
from typing import Optional

from fastapi import Depends, Request
from sqlalchemy import text

from .common.session import get_session_token, get_user_from_session
from .db import get_db
from .exceptions import AuthenticationError, AuthorizationError
from .logging_config import get_logger

logger = get_logger(__name__)

# Role definitions
ROLE_USER = "user"
ROLE_PRO = "pro"
ROLE_ADMIN = "admin"

# Permission hierarchy: higher roles inherit lower role permissions
ROLE_HIERARCHY = {
    ROLE_USER: 0,
    ROLE_PRO: 1,
    ROLE_ADMIN: 2,
}


def get_user_role(user: Optional[dict]) -> str:
    """Get user role from user dict. Returns 'user' by default."""
    if not user:
        return ROLE_USER

    # Admin check (from ADMIN_EMAILS env var)
    from .common.session import is_admin
    if is_admin(user):
        return ROLE_ADMIN

    # Pro plan check
    plan = user.get("plan", "free")
    if plan == "pro":
        return ROLE_PRO

    return ROLE_USER


def has_role(user: Optional[dict], required_role: str) -> bool:
    """Check if user has the required role or higher."""
    if not user and required_role != ROLE_USER:
        return False

    user_role = get_user_role(user)
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 0)

    return user_level >= required_level


def require_auth(request: Request, db=Depends(get_db)):
    """Dependency that requires authentication. Returns user dict or raises."""
    token = get_session_token(request)
    user = get_user_from_session(db, token)

    if not user:
        logger.warning("Authentication required but no valid session", extra={
            "path": request.url.path,
            "method": request.method,
        })
        raise AuthenticationError("Authentication required")

    return user


def require_role(required_role: str):
    """
    Dependency factory that requires a specific role or higher.

    Usage:
        @router.get("/admin/dashboard")
        def admin_dashboard(user=Depends(require_role(ROLE_ADMIN))):
            ...
    """
    def role_dependency(request: Request, db=Depends(get_db)):
        user = require_auth(request, db)

        if not has_role(user, required_role):
            user_role = get_user_role(user)
            logger.warning(
                "Authorization failed: insufficient role",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "user_id": user.get("id"),
                    "user_role": user_role,
                    "required_role": required_role,
                }
            )
            raise AuthorizationError(f"This endpoint requires {required_role} role or higher")

        return user

    return role_dependency


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key and its hash.

    Returns:
        tuple[str, str]: (api_key, api_key_hash)
        - api_key: The plaintext key to show to the user (only once)
        - api_key_hash: The hashed key to store in the database

    Note:
        SHA-256 is appropriate here because we're hashing cryptographically-random
        API keys (not user passwords). API keys are generated with secrets.token_urlsafe()
        and have 256 bits of entropy, making them resistant to brute force attacks.
        For user passwords, use bcrypt, scrypt, or argon2 instead.
    """
    # Generate a secure random API key (32 bytes = 256 bits)
    api_key = f"tc_{secrets.token_urlsafe(32)}"

    # Hash the API key for storage
    # SHA-256 is safe for hashing random tokens (not passwords)
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()  # nosec B324

    return api_key, api_key_hash


def verify_api_key(db, api_key: str) -> Optional[dict]:
    """
    Verify an API key and return the associated user.

    Args:
        db: Database session
        api_key: The plaintext API key from the request

    Returns:
        User dict if valid, None otherwise
    """
    if not api_key or not api_key.startswith("tc_"):
        return None

    # Hash the provided key
    # SHA-256 is safe for hashing random tokens (not passwords)
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()  # nosec B324

    # Look up the key in the database
    result = db.execute(
        text("""
            SELECT u.*, k.id as api_key_id, k.name as api_key_name
            FROM api_keys k
            JOIN users u ON u.id = k.user_id
            WHERE k.key_hash = :hash
              AND k.revoked_at IS NULL
              AND (k.expires_at IS NULL OR k.expires_at > now())
        """),
        {"hash": api_key_hash}
    ).mappings().first()

    if result:
        # Update last used timestamp
        db.execute(
            text("UPDATE api_keys SET last_used_at = now() WHERE id = :id"),
            {"id": result["api_key_id"]}
        )
        db.commit()

        logger.info(
            "API key authenticated",
            extra={
                "user_id": result["id"],
                "api_key_name": result["api_key_name"],
            }
        )

        return dict(result)

    return None


def get_user_optional(request: Request, db=Depends(get_db)) -> Optional[dict]:
    """
    Get the current user from session cookie or API key header (optional).
    Returns None if not authenticated.

    Supports:
    - Session cookie authentication
    - API key via Authorization header: "Bearer tc_..."
    - API key via X-API-Key header
    """
    # Try session cookie first
    token = get_session_token(request)
    user = get_user_from_session(db, token)
    if user:
        return user

    # Try API key authentication
    auth_header = request.headers.get("Authorization", "")
    api_key_header = request.headers.get("X-API-Key", "")

    api_key = None
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]
    elif api_key_header:
        api_key = api_key_header

    if api_key:
        user = verify_api_key(db, api_key)
        if user:
            return user

    return None


def get_user_required(request: Request, db=Depends(get_db)) -> dict:
    """
    Get the current user (required). Raises AuthenticationError if not authenticated.
    Supports both session and API key authentication.
    """
    user = get_user_optional(request, db)
    if not user:
        raise AuthenticationError("Authentication required")
    return user


def validate_state_token(state: str, request: Request) -> bool:
    """
    Validate OAuth state parameter to prevent CSRF attacks.

    The state should be stored in the session before redirecting to OAuth provider,
    and validated when the callback is received.

    Args:
        state: The state parameter from OAuth callback
        request: The FastAPI request object

    Returns:
        bool: True if valid, False otherwise
    """
    # Get the stored state from session
    # Note: This requires session storage which we'll implement
    stored_state = request.session.get("oauth_state")

    if not stored_state or stored_state != state:
        logger.warning(
            "OAuth state validation failed",
            extra={
                "provided_state": state[:10] + "..." if state else None,
                "has_stored_state": bool(stored_state),
            }
        )
        return False

    # Clear the state after use (one-time token)
    request.session.pop("oauth_state", None)
    return True


def generate_oauth_state() -> str:
    """Generate a secure random state parameter for OAuth."""
    return secrets.token_urlsafe(32)


def generate_nonce() -> str:
    """Generate a secure random nonce for OAuth replay protection."""
    return secrets.token_urlsafe(32)
