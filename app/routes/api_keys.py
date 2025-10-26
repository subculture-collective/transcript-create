"""API key management endpoints."""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from ..audit import ACTION_API_KEY_CREATED, ACTION_API_KEY_REVOKED, log_audit_from_request
from ..db import get_db
from ..exceptions import AuthorizationError, NotFoundError, ValidationError
from ..logging_config import get_logger
from ..security import generate_api_key, get_user_required
from ..settings import settings

logger = get_logger(__name__)

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


class CreateAPIKeyRequest(BaseModel):
    """Request to create a new API key."""
    name: str = Field(..., description="Human-readable name for the API key", min_length=1, max_length=100)
    expires_days: Optional[int] = Field(
        default=None,
        description="Number of days until the key expires. None = never expires",
        ge=1,
        le=3650,  # Max 10 years
    )
    scopes: Optional[str] = Field(default=None, description="Comma-separated list of scopes (future use)")


class APIKeyResponse(BaseModel):
    """Response containing API key details."""
    id: str
    name: str
    key_prefix: str
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    revoked_at: Optional[datetime]
    scopes: Optional[str]


class CreateAPIKeyResponse(BaseModel):
    """Response when creating a new API key."""
    api_key: str = Field(..., description="The full API key - save this, it won't be shown again!")
    key: APIKeyResponse


@router.get(
    "",
    summary="List API keys",
    description="""
    List all API keys for the authenticated user.
    
    Returns a list of API keys with their metadata. The full key value is never
    returned after creation for security reasons.
    """,
    response_model=list[APIKeyResponse],
)
def list_api_keys(request: Request, db=Depends(get_db), user=Depends(get_user_required)):
    """List all API keys for the current user."""
    user_id = user.get("id")
    
    result = db.execute(
        text("""
            SELECT id, name, key_prefix, created_at, expires_at, last_used_at, revoked_at, scopes
            FROM api_keys
            WHERE user_id = :user_id
            ORDER BY created_at DESC
        """),
        {"user_id": str(user_id)}
    ).mappings().all()
    
    return [dict(row) for row in result]


@router.post(
    "",
    summary="Create API key",
    description="""
    Create a new API key for the authenticated user.
    
    **Important:** The full API key is only returned once at creation time.
    Store it securely - you won't be able to retrieve it again.
    """,
    response_model=CreateAPIKeyResponse,
    status_code=201,
)
def create_api_key(
    request: Request,
    body: CreateAPIKeyRequest,
    db=Depends(get_db),
    user=Depends(get_user_required),
):
    """Create a new API key for the current user."""
    user_id = user.get("id")
    
    # Generate the API key
    api_key, api_key_hash = generate_api_key()
    key_prefix = api_key[:10] + "..."  # Show first 10 chars
    
    # Calculate expiration
    expires_at = None
    if body.expires_days:
        expires_at = datetime.utcnow() + timedelta(days=body.expires_days)
    elif settings.API_KEY_EXPIRE_DAYS:
        # Use default expiration from settings
        expires_at = datetime.utcnow() + timedelta(days=settings.API_KEY_EXPIRE_DAYS)
    
    # Insert into database
    key_id = uuid.uuid4()
    db.execute(
        text("""
            INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix, expires_at, scopes)
            VALUES (:id, :user_id, :name, :key_hash, :key_prefix, :expires_at, :scopes)
        """),
        {
            "id": str(key_id),
            "user_id": str(user_id),
            "name": body.name,
            "key_hash": api_key_hash,
            "key_prefix": key_prefix,
            "expires_at": expires_at,
            "scopes": body.scopes,
        }
    )
    db.commit()
    
    # Log audit event
    log_audit_from_request(
        db, request,
        ACTION_API_KEY_CREATED,
        user_id=user_id,
        resource_type="api_key",
        resource_id=str(key_id),
        details={"name": body.name, "expires_at": expires_at.isoformat() if expires_at else None}
    )
    
    logger.info(
        "API key created",
        extra={
            "user_id": str(user_id),
            "key_id": str(key_id),
            "name": body.name,
        }
    )
    
    # Retrieve the created key
    key_data = db.execute(
        text("""
            SELECT id, name, key_prefix, created_at, expires_at, last_used_at, revoked_at, scopes
            FROM api_keys
            WHERE id = :id
        """),
        {"id": str(key_id)}
    ).mappings().first()
    
    return {
        "api_key": api_key,
        "key": dict(key_data),
    }


@router.delete(
    "/{key_id}",
    summary="Revoke API key",
    description="""
    Revoke an API key, making it unusable for future requests.
    
    This operation cannot be undone. Revoked keys cannot be reactivated.
    """,
)
def revoke_api_key(
    key_id: str,
    request: Request,
    db=Depends(get_db),
    user=Depends(get_user_required),
):
    """Revoke an API key."""
    user_id = user.get("id")
    
    # Verify the key belongs to the user
    key = db.execute(
        text("""
            SELECT id, name, user_id, revoked_at
            FROM api_keys
            WHERE id = :id
        """),
        {"id": key_id}
    ).mappings().first()
    
    if not key:
        raise NotFoundError("API key not found")
    
    if str(key["user_id"]) != str(user_id):
        raise AuthorizationError("You don't have permission to revoke this API key")
    
    if key["revoked_at"]:
        raise ValidationError("API key is already revoked")
    
    # Revoke the key
    db.execute(
        text("""
            UPDATE api_keys
            SET revoked_at = now()
            WHERE id = :id
        """),
        {"id": key_id}
    )
    db.commit()
    
    # Log audit event
    log_audit_from_request(
        db, request,
        ACTION_API_KEY_REVOKED,
        user_id=user_id,
        resource_type="api_key",
        resource_id=key_id,
        details={"name": key["name"]}
    )
    
    logger.info(
        "API key revoked",
        extra={
            "user_id": str(user_id),
            "key_id": key_id,
            "name": key["name"],
        }
    )
    
    return {"ok": True, "message": "API key revoked successfully"}
