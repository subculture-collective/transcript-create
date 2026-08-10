"""Audit logging for security events and user actions."""

import json
from typing import Any, Optional
from uuid import UUID

from fastapi import Request
from sqlalchemy import text

from .db import SessionLocal
from .logging_config import get_logger

logger = get_logger(__name__)

# Audit action types
ACTION_LOGIN_SUCCESS = "login_success"
ACTION_LOGIN_FAILED = "login_failed"
ACTION_LOGOUT = "logout"
ACTION_SESSION_REFRESH = "session_refresh"
ACTION_SESSION_REVOKED = "session_revoked"
ACTION_SESSIONS_REVOKED = "sessions_revoked"
ACTION_PROFILE_UPDATED = "profile_updated"
ACTION_API_KEY_CREATED = "api_key_created"
ACTION_API_KEY_REVOKED = "api_key_revoked"
ACTION_API_KEY_USED = "api_key_used"
ACTION_PERMISSION_DENIED = "permission_denied"
ACTION_RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
ACTION_ADMIN_ACTION = "admin_action"
ACTION_USER_DATA_EXPORT = "user_data_export"
ACTION_IDENTITY_LINKED = "identity_linked"
ACTION_IDENTITY_UNLINKED = "identity_unlinked"
ACTION_IDENTITY_COLLISION = "identity_collision"
ACTION_ACCOUNTS_MERGED = "accounts_merged"
ACTION_BOOTSTRAP_ADMIN_PROMOTED = "bootstrap_admin_promoted"
ACTION_USER_DATA_DELETION = "user_data_deletion"


def write_audit_event(
    db,
    action: str,
    user_id: Optional[UUID] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    success: bool = True,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
):
    """Write an audit event into the current transaction without finalizing it."""
    db.execute(
        text("""
            INSERT INTO audit_logs
            (user_id, action, resource_type, resource_id, success, details, ip_address, user_agent)
            VALUES (
                :user_id, :action, :resource_type, :resource_id,
                :success, CAST(:details AS JSONB), :ip_address, :user_agent
            )
        """),
        {
            "user_id": str(user_id) if user_id else None,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "success": success,
            "details": json.dumps(details or {}),
            "ip_address": ip_address,
            "user_agent": user_agent,
        },
    )


def log_audit_event(
    db,
    action: str,
    user_id: Optional[UUID] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    success: bool = True,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
):
    """Best-effort durable audit write in an independent transaction.

    Args:
        db: Database session
        action: Action type (e.g., "login_success", "api_key_created")
        user_id: UUID of the user performing the action
        resource_type: Type of resource affected (e.g., "video", "job")
        resource_id: ID of the resource affected
        success: Whether the action was successful
        details: Additional JSON details about the event
        ip_address: Client IP address
        user_agent: Client user agent string
    """
    del db  # Compatibility parameter; never enlist the caller transaction.
    independent_db = SessionLocal()
    try:
        write_audit_event(
            independent_db, action, user_id, resource_type, resource_id, success, details, ip_address, user_agent
        )
        independent_db.commit()
    except Exception as exc:
        independent_db.rollback()
        logger.warning("Best-effort audit write failed", extra={"action": action, "error_type": type(exc).__name__})
    finally:
        independent_db.close()


def write_audit_from_request(
    db,
    request: Request,
    action: str,
    user_id: Optional[UUID] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    success: bool = True,
    details: Optional[dict] = None,
):
    """Write request audit metadata in the caller's active transaction."""
    write_audit_event(
        db,
        action,
        user_id,
        resource_type,
        resource_id,
        success,
        details,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


def log_audit_from_request(
    db,
    request: Request,
    action: str,
    user_id: Optional[UUID] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    success: bool = True,
    details: Optional[dict] = None,
):
    """
    Log an audit event, extracting request metadata automatically.

    Args:
        db: Database session
        request: FastAPI request object
        action: Action type
        user_id: UUID of the user performing the action
        resource_type: Type of resource affected
        resource_id: ID of the resource affected
        success: Whether the action was successful
        details: Additional JSON details about the event
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    log_audit_event(
        db=db,
        action=action,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        success=success,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def get_audit_logs(
    db,
    user_id: Optional[UUID] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    Retrieve audit logs with optional filtering.

    Args:
        db: Database session
        user_id: Filter by user ID
        action: Filter by action type
        resource_type: Filter by resource type
        limit: Maximum number of records to return
        offset: Number of records to skip

    Returns:
        List of audit log records
    """
    query = """
        SELECT
            id, created_at, user_id, action, resource_type, resource_id,
            ip_address, user_agent, success, details
        FROM audit_logs
        WHERE 1=1
    """
    params: dict[str, Any] = {}

    if user_id:
        query += " AND user_id = :user_id"
        params["user_id"] = str(user_id)

    if action:
        query += " AND action = :action"
        params["action"] = action

    if resource_type:
        query += " AND resource_type = :resource_type"
        params["resource_type"] = resource_type

    query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    result = db.execute(text(query), params).mappings().all()
    return [dict(row) for row in result]


def cleanup_old_audit_logs(db, days_to_keep: int = 90):
    """
    Remove audit logs older than the specified number of days.

    This should be called periodically (e.g., via a scheduled task) to prevent
    the audit logs table from growing indefinitely.

    Args:
        db: Database session
        days_to_keep: Number of days to retain audit logs (default: 90)

    Returns:
        Number of records deleted
    """
    try:
        result = db.execute(
            text("""
                DELETE FROM audit_logs
                WHERE created_at < now() - make_interval(days => :days)
                RETURNING id
            """),
            {"days": days_to_keep},
        )
        deleted_count = result.rowcount
        db.commit()

        logger.info("Cleaned up old audit logs", extra={"deleted_count": deleted_count, "days_to_keep": days_to_keep})

        return deleted_count
    except Exception as exc:
        logger.error("Failed to cleanup audit logs", extra={"error_type": type(exc).__name__})
        db.rollback()
        return 0
