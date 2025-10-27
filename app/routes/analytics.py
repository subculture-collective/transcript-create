"""Admin analytics endpoints for dashboard metrics and system health."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from ..db import get_db
from ..security import ROLE_ADMIN, require_role

router = APIRouter(prefix="/admin/dashboard", tags=["Admin"])


@router.get(
    "/metrics",
    summary="Get dashboard metrics (Admin)",
    description="""
    Get key metrics for the admin dashboard.

    **Admin Only:** Requires admin privileges

    Returns:
    - Total jobs (all time, today, this week)
    - Total videos transcribed
    - Total users (free vs pro)
    - Active sessions
    - Search queries today
    - Export requests today
    """,
    responses={
        200: {
            "description": "Dashboard metrics",
            "content": {
                "application/json": {
                    "example": {
                        "jobs": {
                            "total": 1500,
                            "today": 42,
                            "this_week": 287,
                            "pending": 12,
                            "in_progress": 3,
                        },
                        "videos": {
                            "total": 3245,
                            "completed": 3100,
                            "failed": 145,
                        },
                        "users": {
                            "total": 567,
                            "free": 520,
                            "pro": 47,
                            "signups_today": 8,
                            "signups_this_week": 56,
                        },
                        "sessions": {
                            "active": 89,
                        },
                        "searches": {
                            "today": 234,
                            "this_week": 1876,
                        },
                        "exports": {
                            "today": 45,
                            "this_week": 312,
                        },
                    }
                }
            },
        },
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
    },
)
def get_dashboard_metrics(
    request: Request,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    """Get key metrics for the admin dashboard."""
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)

    # Jobs metrics
    jobs_total = db.execute(text("SELECT COUNT(*) FROM jobs")).scalar()
    jobs_today = db.execute(
        text("SELECT COUNT(*) FROM jobs WHERE created_at >= :today"),
        {"today": today}
    ).scalar()
    jobs_this_week = db.execute(
        text("SELECT COUNT(*) FROM jobs WHERE created_at >= :week_ago"),
        {"week_ago": week_ago}
    ).scalar()
    jobs_pending = db.execute(
        text("SELECT COUNT(*) FROM videos WHERE state = 'pending'")
    ).scalar()
    jobs_in_progress = db.execute(
        text("SELECT COUNT(*) FROM videos WHERE state IN ('downloading', 'transcoding', 'transcribing')")
    ).scalar()

    # Videos metrics
    videos_total = db.execute(text("SELECT COUNT(*) FROM videos")).scalar()
    videos_completed = db.execute(
        text("SELECT COUNT(*) FROM videos WHERE state = 'completed'")
    ).scalar()
    videos_failed = db.execute(
        text("SELECT COUNT(*) FROM videos WHERE state = 'failed'")
    ).scalar()

    # Users metrics
    users_total = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
    users_free = db.execute(
        text("SELECT COUNT(*) FROM users WHERE plan = 'free'")
    ).scalar()
    users_pro = db.execute(
        text("SELECT COUNT(*) FROM users WHERE plan != 'free'")
    ).scalar()
    signups_today = db.execute(
        text("SELECT COUNT(*) FROM users WHERE created_at >= :today"),
        {"today": today}
    ).scalar()
    signups_this_week = db.execute(
        text("SELECT COUNT(*) FROM users WHERE created_at >= :week_ago"),
        {"week_ago": week_ago}
    ).scalar()

    # Active sessions (sessions not expired)
    sessions_active = db.execute(
        text("SELECT COUNT(*) FROM sessions WHERE expires_at > :now"),
        {"now": now}
    ).scalar()

    # Search queries from events table
    searches_today = db.execute(
        text("SELECT COUNT(*) FROM events WHERE type = 'search' AND created_at >= :today"),
        {"today": today}
    ).scalar()
    searches_this_week = db.execute(
        text("SELECT COUNT(*) FROM events WHERE type = 'search' AND created_at >= :week_ago"),
        {"week_ago": week_ago}
    ).scalar()

    # Export requests from events table
    exports_today = db.execute(
        text("SELECT COUNT(*) FROM events WHERE type = 'export' AND created_at >= :today"),
        {"today": today}
    ).scalar()
    exports_this_week = db.execute(
        text("SELECT COUNT(*) FROM events WHERE type = 'export' AND created_at >= :week_ago"),
        {"week_ago": week_ago}
    ).scalar()

    return {
        "jobs": {
            "total": jobs_total or 0,
            "today": jobs_today or 0,
            "this_week": jobs_this_week or 0,
            "pending": jobs_pending or 0,
            "in_progress": jobs_in_progress or 0,
        },
        "videos": {
            "total": videos_total or 0,
            "completed": videos_completed or 0,
            "failed": videos_failed or 0,
        },
        "users": {
            "total": users_total or 0,
            "free": users_free or 0,
            "pro": users_pro or 0,
            "signups_today": signups_today or 0,
            "signups_this_week": signups_this_week or 0,
        },
        "sessions": {
            "active": sessions_active or 0,
        },
        "searches": {
            "today": searches_today or 0,
            "this_week": searches_this_week or 0,
        },
        "exports": {
            "today": exports_today or 0,
            "this_week": exports_this_week or 0,
        },
    }


@router.get(
    "/charts/jobs-over-time",
    summary="Get jobs over time chart data (Admin)",
    description="""
    Get time series data for jobs created over time.

    **Admin Only:** Requires admin privileges

    Query Parameters:
    - `period`: 'daily' (default), 'weekly', or 'monthly'
    - `days`: Number of days to look back (default: 30)
    """,
    responses={
        200: {
            "description": "Time series data",
            "content": {
                "application/json": {
                    "example": {
                        "labels": ["2025-10-20", "2025-10-21", "2025-10-22"],
                        "data": [15, 23, 18],
                    }
                }
            },
        },
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
    },
)
def get_jobs_over_time(
    request: Request,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
    period: str = "daily",
    days: int = 30,
):
    """Get jobs created over time."""
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)

    if period == "daily":
        query = text("""
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM jobs
            WHERE created_at >= :start_date
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """)
    elif period == "weekly":
        query = text("""
            SELECT DATE_TRUNC('week', created_at) as date, COUNT(*) as count
            FROM jobs
            WHERE created_at >= :start_date
            GROUP BY DATE_TRUNC('week', created_at)
            ORDER BY date ASC
        """)
    elif period == "monthly":
        query = text("""
            SELECT DATE_TRUNC('month', created_at) as date, COUNT(*) as count
            FROM jobs
            WHERE created_at >= :start_date
            GROUP BY DATE_TRUNC('month', created_at)
            ORDER BY date ASC
        """)
    else:
        return {"error": "Invalid period. Use 'daily', 'weekly', or 'monthly'"}

    rows = db.execute(query, {"start_date": start_date}).all()

    return {
        "labels": [str(row[0]) for row in rows],
        "data": [row[1] for row in rows],
    }


@router.get(
    "/charts/job-status-breakdown",
    summary="Get job status breakdown (Admin)",
    description="""
    Get breakdown of jobs by status.

    **Admin Only:** Requires admin privileges
    """,
    responses={
        200: {
            "description": "Job status breakdown",
            "content": {
                "application/json": {
                    "example": {
                        "labels": ["completed", "failed", "pending", "in_progress"],
                        "data": [1500, 45, 12, 3],
                    }
                }
            },
        },
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
    },
)
def get_job_status_breakdown(
    request: Request,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    """Get breakdown of videos by status."""
    query = text("""
        SELECT state, COUNT(*) as count
        FROM videos
        GROUP BY state
        ORDER BY count DESC
    """)

    rows = db.execute(query).all()

    return {
        "labels": [row[0] for row in rows],
        "data": [row[1] for row in rows],
    }


@router.get(
    "/charts/export-format-breakdown",
    summary="Get export format breakdown (Admin)",
    description="""
    Get breakdown of exports by format.

    **Admin Only:** Requires admin privileges
    """,
    responses={
        200: {
            "description": "Export format breakdown",
            "content": {
                "application/json": {
                    "example": {
                        "labels": ["srt", "vtt", "json", "pdf"],
                        "data": [450, 320, 180, 150],
                    }
                }
            },
        },
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
    },
)
def get_export_format_breakdown(
    request: Request,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
    days: int = 30,
):
    """Get breakdown of exports by format from events."""
    start_date = datetime.utcnow() - timedelta(days=days)

    query = text("""
        SELECT 
            payload->>'format' as format,
            COUNT(*) as count
        FROM events
        WHERE type = 'export'
          AND created_at >= :start_date
          AND payload->>'format' IS NOT NULL
        GROUP BY format
        ORDER BY count DESC
    """)

    rows = db.execute(query, {"start_date": start_date}).all()

    return {
        "labels": [row[0] or "unknown" for row in rows],
        "data": [row[1] for row in rows],
    }


@router.get(
    "/search-analytics",
    summary="Get search analytics (Admin)",
    description="""
    Get search analytics including popular terms and performance.

    **Admin Only:** Requires admin privileges
    """,
    responses={
        200: {
            "description": "Search analytics",
            "content": {
                "application/json": {
                    "example": {
                        "popular_terms": [
                            {"term": "python tutorial", "count": 45},
                            {"term": "react hooks", "count": 32},
                        ],
                        "zero_result_searches": 12,
                        "avg_results_per_query": 8.5,
                        "avg_query_time_ms": 145,
                    }
                }
            },
        },
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
    },
)
def get_search_analytics(
    request: Request,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
    days: int = 30,
):
    """Get search analytics."""
    start_date = datetime.utcnow() - timedelta(days=days)

    # Popular search terms from user_searches table if it exists
    popular_terms = []
    try:
        query = text("""
            SELECT query, COUNT(*) as count
            FROM user_searches
            WHERE created_at >= :start_date
            GROUP BY query
            ORDER BY count DESC
            LIMIT 20
        """)
        rows = db.execute(query, {"start_date": start_date}).all()
        popular_terms = [{"term": row[0], "count": row[1]} for row in rows]
    except Exception:
        # Table might not exist or be empty
        pass

    # Zero result searches
    zero_results = 0
    avg_results = 0
    avg_time = 0
    try:
        zero_results = db.execute(
            text("""
                SELECT COUNT(*) FROM user_searches
                WHERE created_at >= :start_date AND result_count = 0
            """),
            {"start_date": start_date}
        ).scalar() or 0

        stats = db.execute(
            text("""
                SELECT AVG(result_count), AVG(query_time_ms)
                FROM user_searches
                WHERE created_at >= :start_date
            """),
            {"start_date": start_date}
        ).first()

        if stats:
            avg_results = float(stats[0]) if stats[0] else 0
            avg_time = float(stats[1]) if stats[1] else 0
    except Exception:
        pass

    return {
        "popular_terms": popular_terms,
        "zero_result_searches": zero_results,
        "avg_results_per_query": round(avg_results, 1),
        "avg_query_time_ms": round(avg_time, 0),
    }


@router.get(
    "/system-health",
    summary="Get system health metrics (Admin)",
    description="""
    Get system health metrics including database and worker status.

    **Admin Only:** Requires admin privileges
    """,
    responses={
        200: {
            "description": "System health metrics",
            "content": {
                "application/json": {
                    "example": {
                        "database": {
                            "status": "healthy",
                            "total_size_mb": 1024,
                            "connections": 12,
                        },
                        "workers": {
                            "active_jobs": 3,
                            "avg_processing_time_seconds": 245,
                            "error_rate_percent": 2.5,
                        },
                        "queue": {
                            "pending": 12,
                            "oldest_pending_minutes": 15,
                        },
                    }
                }
            },
        },
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
    },
)
def get_system_health(
    request: Request,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    """Get system health metrics."""
    # Database metrics
    db_status = "healthy"
    total_size_mb = 0
    connections = 0

    try:
        # Get database size
        size_result = db.execute(
            text("SELECT pg_database_size(current_database()) / (1024*1024)")
        ).scalar()
        total_size_mb = int(size_result) if size_result else 0

        # Get connection count
        conn_result = db.execute(
            text("SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database()")
        ).scalar()
        connections = int(conn_result) if conn_result else 0
    except Exception:
        db_status = "error"

    # Worker metrics
    active_jobs = db.execute(
        text("SELECT COUNT(*) FROM videos WHERE state IN ('downloading', 'transcoding', 'transcribing')")
    ).scalar() or 0

    # Calculate average processing time from completed videos in last 7 days
    avg_time_result = db.execute(
        text("""
            SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at)))
            FROM videos
            WHERE state = 'completed'
              AND updated_at >= NOW() - INTERVAL '7 days'
        """)
    ).scalar()
    avg_processing_time = int(avg_time_result) if avg_time_result else 0

    # Error rate
    completed_week = db.execute(
        text("SELECT COUNT(*) FROM videos WHERE state = 'completed' AND updated_at >= NOW() - INTERVAL '7 days'")
    ).scalar() or 0
    failed_week = db.execute(
        text("SELECT COUNT(*) FROM videos WHERE state = 'failed' AND updated_at >= NOW() - INTERVAL '7 days'")
    ).scalar() or 0
    total_week = completed_week + failed_week
    error_rate = (failed_week / total_week * 100) if total_week > 0 else 0

    # Queue metrics
    pending = db.execute(
        text("SELECT COUNT(*) FROM videos WHERE state = 'pending'")
    ).scalar() or 0

    oldest_pending_result = db.execute(
        text("""
            SELECT EXTRACT(EPOCH FROM (NOW() - MIN(created_at))) / 60
            FROM videos
            WHERE state = 'pending'
        """)
    ).scalar()
    oldest_pending_minutes = int(oldest_pending_result) if oldest_pending_result else 0

    return {
        "database": {
            "status": db_status,
            "total_size_mb": total_size_mb,
            "connections": connections,
        },
        "workers": {
            "active_jobs": active_jobs,
            "avg_processing_time_seconds": avg_processing_time,
            "error_rate_percent": round(error_rate, 1),
        },
        "queue": {
            "pending": pending,
            "oldest_pending_minutes": oldest_pending_minutes,
        },
    }
