"""
Health check and readiness probe endpoints.

Provides comprehensive health monitoring for:
- Basic liveness/readiness probes for Kubernetes
- Detailed component health checks (database, OpenSearch, storage, worker)
- Health metrics for Prometheus
- Version information
"""

import asyncio
import os
import shutil
import socket
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..db import engine
from ..logging_config import get_logger
from ..settings import settings

logger = get_logger(__name__)

router = APIRouter(prefix="", tags=["Health"])

# Version information
from ..version import get_version, get_git_commit, get_build_date

VERSION = get_version()
GIT_COMMIT = get_git_commit()
BUILD_DATE = get_build_date()

# Health check metrics
from prometheus_client import Counter, Gauge, Histogram

health_check_status = Gauge(
    "health_check_status",
    "Health check status (1=healthy, 0=unhealthy)",
    ["component"],
)

health_check_duration_seconds = Histogram(
    "health_check_duration_seconds",
    "Health check duration in seconds",
    ["component"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

health_check_total = Counter(
    "health_check_total",
    "Total health checks performed",
    ["component", "status"],
)


async def check_database() -> Dict[str, Any]:
    """
    Check database health by running a simple query and measuring latency.
    
    Returns:
        Dict with status, latency_ms, and optional error
    """
    start_time = time.time()
    try:
        with engine.connect() as conn:
            # Simple query to check connectivity
            conn.execute(text("SELECT 1"))
            
            # Check read permissions
            conn.execute(text("SELECT COUNT(*) FROM jobs LIMIT 1"))
            
            # Check connection pool status
            pool_size = engine.pool.size()
            checked_in = engine.pool.checkedin()
            
            latency_ms = (time.time() - start_time) * 1000
            
            health_check_status.labels(component="database").set(1)
            health_check_duration_seconds.labels(component="database").observe(time.time() - start_time)
            health_check_total.labels(component="database", status="healthy").inc()
            
            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "pool_size": pool_size,
                "pool_checked_in": checked_in,
            }
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error("Database health check failed", extra={"error": str(e)}, exc_info=True)
        
        health_check_status.labels(component="database").set(0)
        health_check_duration_seconds.labels(component="database").observe(time.time() - start_time)
        health_check_total.labels(component="database", status="unhealthy").inc()
        
        return {
            "status": "unhealthy",
            "latency_ms": round(latency_ms, 2),
            "error": str(e),
        }


async def check_opensearch() -> Dict[str, Any]:
    """
    Check OpenSearch health if enabled.
    
    Returns:
        Dict with status, latency_ms, and optional error
    """
    if settings.SEARCH_BACKEND != "opensearch":
        return {"status": "disabled"}
    
    start_time = time.time()
    try:
        import requests
        
        # Build auth if credentials are provided
        auth = None
        if settings.OPENSEARCH_USER and settings.OPENSEARCH_PASSWORD:
            auth = (settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD)
        
        # Check cluster health
        url = f"{settings.OPENSEARCH_URL}/_cluster/health"
        response = requests.get(
            url,
            auth=auth,
            timeout=settings.HEALTH_CHECK_TIMEOUT,
            verify=False,  # OpenSearch often uses self-signed certs in dev
        )
        response.raise_for_status()
        
        health_data = response.json()
        cluster_status = health_data.get("status", "unknown")
        
        latency_ms = (time.time() - start_time) * 1000
        
        # OpenSearch cluster status: green, yellow, red
        is_healthy = cluster_status in ["green", "yellow"]
        
        health_check_status.labels(component="opensearch").set(1 if is_healthy else 0)
        health_check_duration_seconds.labels(component="opensearch").observe(time.time() - start_time)
        health_check_total.labels(component="opensearch", status="healthy" if is_healthy else "unhealthy").inc()
        
        return {
            "status": "healthy" if is_healthy else "degraded",
            "latency_ms": round(latency_ms, 2),
            "cluster_status": cluster_status,
            "number_of_nodes": health_data.get("number_of_nodes"),
        }
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error("OpenSearch health check failed", extra={"error": str(e)}, exc_info=True)
        
        health_check_status.labels(component="opensearch").set(0)
        health_check_duration_seconds.labels(component="opensearch").observe(time.time() - start_time)
        health_check_total.labels(component="opensearch", status="unhealthy").inc()
        
        return {
            "status": "unhealthy",
            "latency_ms": round(latency_ms, 2),
            "error": str(e),
        }


async def check_storage() -> Dict[str, Any]:
    """
    Check storage health (disk space and write permissions).
    
    Returns:
        Dict with status, free_gb, and optional error
    """
    start_time = time.time()
    try:
        workdir = settings.WORKDIR
        
        # Check if directory exists
        if not os.path.exists(workdir):
            try:
                os.makedirs(workdir, exist_ok=True)
            except Exception as e:
                health_check_status.labels(component="storage").set(0)
                health_check_total.labels(component="storage", status="unhealthy").inc()
                return {
                    "status": "unhealthy",
                    "error": f"Cannot create workdir: {e}",
                }
        
        # Check disk space
        stat = shutil.disk_usage(workdir)
        free_gb = stat.free / (1024 ** 3)
        total_gb = stat.total / (1024 ** 3)
        used_gb = stat.used / (1024 ** 3)
        
        # Check write permissions
        test_file = os.path.join(workdir, ".health_check_test")
        write_error = None
        try:
            with open(test_file, "w") as f:
                f.write("health check")
            os.remove(test_file)
            can_write = True
        except Exception as e:
            can_write = False
            write_error = str(e)
        
        is_healthy = free_gb >= settings.HEALTH_CHECK_DISK_MIN_FREE_GB and can_write
        
        health_check_status.labels(component="storage").set(1 if is_healthy else 0)
        health_check_duration_seconds.labels(component="storage").observe(time.time() - start_time)
        health_check_total.labels(component="storage", status="healthy" if is_healthy else "unhealthy").inc()
        
        result = {
            "status": "healthy" if is_healthy else "unhealthy",
            "free_gb": round(free_gb, 2),
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "can_write": can_write,
        }
        
        if not can_write:
            result["error"] = f"Cannot write to workdir: {write_error}"
        elif free_gb < settings.HEALTH_CHECK_DISK_MIN_FREE_GB:
            result["error"] = f"Low disk space: {free_gb:.2f}GB < {settings.HEALTH_CHECK_DISK_MIN_FREE_GB}GB"
        
        return result
    except Exception as e:
        logger.error("Storage health check failed", extra={"error": str(e)}, exc_info=True)
        
        health_check_status.labels(component="storage").set(0)
        health_check_duration_seconds.labels(component="storage").observe(time.time() - start_time)
        health_check_total.labels(component="storage", status="unhealthy").inc()
        
        return {
            "status": "unhealthy",
            "error": str(e),
        }


async def check_worker() -> Dict[str, Any]:
    """
    Check worker health by examining heartbeat table.
    
    Returns:
        Dict with status, jobs_pending, last_heartbeat, and optional error
    """
    start_time = time.time()
    try:
        with engine.connect() as conn:
            # Check for pending jobs
            pending_count = conn.execute(
                text("SELECT COUNT(*) FROM videos WHERE state = 'pending'")
            ).scalar_one()
            
            # Check for stuck jobs (in progress states for too long)
            stuck_count = conn.execute(
                text("""
                    SELECT COUNT(*) FROM videos 
                    WHERE state IN ('downloading', 'transcoding', 'transcribing', 'diarizing', 'persisting')
                    AND updated_at < now() - make_interval(secs => :seconds)
                """),
                {"seconds": settings.RESCUE_STUCK_AFTER_SECONDS}
            ).scalar_one()
            
            # Check worker heartbeat
            heartbeat_result = conn.execute(
                text("""
                    SELECT worker_id, last_seen, metrics
                    FROM worker_heartbeat
                    ORDER BY last_seen DESC
                    LIMIT 1
                """)
            ).fetchone()
            
            result = {
                "jobs_pending": pending_count,
                "jobs_stuck": stuck_count,
            }
            
            if heartbeat_result:
                worker_id, last_seen, metrics = heartbeat_result
                seconds_since = (datetime.now(timezone.utc) - last_seen).total_seconds()
                
                result["last_heartbeat"] = last_seen.isoformat()
                result["seconds_since_heartbeat"] = round(seconds_since, 2)
                result["worker_id"] = worker_id
                
                is_stale = seconds_since > settings.HEALTH_CHECK_WORKER_STALE_SECONDS
                
                if is_stale:
                    result["status"] = "degraded"
                    result["error"] = f"Worker heartbeat is stale ({seconds_since:.0f}s > {settings.HEALTH_CHECK_WORKER_STALE_SECONDS}s)"
                    health_check_status.labels(component="worker").set(0)
                    health_check_total.labels(component="worker", status="degraded").inc()
                else:
                    result["status"] = "healthy"
                    health_check_status.labels(component="worker").set(1)
                    health_check_total.labels(component="worker", status="healthy").inc()
            else:
                result["status"] = "degraded"
                result["error"] = "No worker heartbeat found"
                health_check_status.labels(component="worker").set(0)
                health_check_total.labels(component="worker", status="degraded").inc()
            
            health_check_duration_seconds.labels(component="worker").observe(time.time() - start_time)
            return result
            
    except Exception as e:
        logger.error("Worker health check failed", extra={"error": str(e)}, exc_info=True)
        
        health_check_status.labels(component="worker").set(0)
        health_check_duration_seconds.labels(component="worker").observe(time.time() - start_time)
        health_check_total.labels(component="worker", status="unhealthy").inc()
        
        return {
            "status": "unhealthy",
            "error": str(e),
        }


@router.get(
    "/health",
    summary="Basic health check",
    description="Simple endpoint that returns 200 OK if the service is running. Used by load balancers.",
    responses={
        200: {
            "description": "Service is healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "timestamp": "2025-10-25T23:00:00.000000Z"
                    }
                }
            },
        }
    },
)
async def health_check():
    """
    Basic health check endpoint.
    
    Returns 200 OK if the service is running and responding.
    No authentication required. Minimal overhead.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/live",
    summary="Liveness probe",
    description="Kubernetes liveness probe. Checks if the process is alive and responding. Minimal overhead.",
    responses={
        200: {
            "description": "Service is alive",
            "content": {
                "application/json": {
                    "example": {
                        "status": "alive",
                        "timestamp": "2025-10-25T23:00:00.000000Z"
                    }
                }
            },
        }
    },
)
async def liveness_probe():
    """
    Liveness probe for Kubernetes.
    
    Simple check that the process is alive and responding.
    Does not check dependencies. Minimal overhead.
    """
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/ready",
    summary="Readiness probe",
    description="Kubernetes readiness probe. Checks if the service can accept traffic by verifying critical dependencies.",
    responses={
        200: {
            "description": "Service is ready to accept traffic",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ready",
                        "timestamp": "2025-10-25T23:00:00.000000Z",
                        "checks": {
                            "database": {"status": "healthy", "latency_ms": 5}
                        }
                    }
                }
            },
        },
        503: {
            "description": "Service is not ready (dependencies unavailable)",
            "content": {
                "application/json": {
                    "example": {
                        "status": "not_ready",
                        "timestamp": "2025-10-25T23:00:00.000000Z",
                        "checks": {
                            "database": {"status": "unhealthy", "error": "Connection refused"}
                        }
                    }
                }
            },
        }
    },
)
async def readiness_probe():
    """
    Readiness probe for Kubernetes.
    
    Checks if the service can accept traffic by verifying critical dependencies.
    Returns 200 if ready, 503 if not ready.
    """
    checks = {}
    is_ready = True
    
    # Parse critical components
    critical_components = [c.strip() for c in settings.HEALTH_CHECK_CRITICAL_COMPONENTS.split(",") if c.strip()]
    
    # Always check database as it's essential
    if "database" in critical_components or not critical_components:
        db_check = await check_database()
        checks["database"] = db_check
        if db_check["status"] != "healthy":
            is_ready = False
    
    # Check other critical components
    if "opensearch" in critical_components and settings.SEARCH_BACKEND == "opensearch":
        os_check = await check_opensearch()
        checks["opensearch"] = os_check
        if os_check["status"] == "unhealthy":
            is_ready = False
    
    if "storage" in critical_components:
        storage_check = await check_storage()
        checks["storage"] = storage_check
        if storage_check["status"] == "unhealthy":
            is_ready = False
    
    result = {
        "status": "ready" if is_ready else "not_ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
    
    if is_ready:
        return result
    else:
        return JSONResponse(status_code=503, content=result)


@router.get(
    "/health/detailed",
    summary="Detailed health check",
    description="Comprehensive health check of all components including database, OpenSearch, storage, and worker status.",
    responses={
        200: {
            "description": "All components are healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "timestamp": "2025-10-25T23:00:00.000000Z",
                        "checks": {
                            "database": {"status": "healthy", "latency_ms": 5},
                            "opensearch": {"status": "healthy", "latency_ms": 12},
                            "storage": {"status": "healthy", "free_gb": 120},
                            "worker": {"status": "healthy", "jobs_pending": 3}
                        }
                    }
                }
            },
        },
        503: {
            "description": "One or more critical components are unhealthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "unhealthy",
                        "timestamp": "2025-10-25T23:00:00.000000Z",
                        "checks": {
                            "database": {"status": "unhealthy", "error": "Connection refused"}
                        }
                    }
                }
            },
        }
    },
)
async def detailed_health_check():
    """
    Detailed health check endpoint.
    
    Checks all components and returns comprehensive status information.
    Returns 200 if all healthy or only degraded, 503 if any critical component is unhealthy.
    """
    # Run all checks concurrently
    db_check_task = asyncio.create_task(check_database())
    os_check_task = asyncio.create_task(check_opensearch())
    storage_check_task = asyncio.create_task(check_storage())
    worker_check_task = asyncio.create_task(check_worker())
    
    # Wait for all checks to complete
    db_check = await db_check_task
    os_check = await os_check_task
    storage_check = await storage_check_task
    worker_check = await worker_check_task
    
    checks = {
        "database": db_check,
        "opensearch": os_check,
        "storage": storage_check,
        "worker": worker_check,
    }
    
    # Determine overall status
    critical_components = [c.strip() for c in settings.HEALTH_CHECK_CRITICAL_COMPONENTS.split(",") if c.strip()]
    
    has_unhealthy = False
    has_degraded = False
    
    for component, check in checks.items():
        if check["status"] == "unhealthy":
            # Check if this component is critical
            if component in critical_components or not critical_components:
                has_unhealthy = True
        elif check["status"] == "degraded":
            has_degraded = True
    
    if has_unhealthy:
        overall_status = "unhealthy"
        status_code = 503
    elif has_degraded:
        overall_status = "degraded"
        status_code = 200
    else:
        overall_status = "healthy"
        status_code = 200
    
    result = {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
    
    if status_code == 503:
        return JSONResponse(status_code=503, content=result)
    else:
        return result


@router.get(
    "/version",
    summary="Version information",
    description="Returns version information including API version, git commit, and build date.",
    responses={
        200: {
            "description": "Version information",
            "content": {
                "application/json": {
                    "example": {
                        "version": "0.1.0",
                        "git_commit": "abc123def",
                        "build_date": "2025-10-25T23:00:00Z"
                    }
                }
            },
        }
    },
)
async def version_info():
    """
    Version information endpoint.
    
    Returns the API version, git commit hash, and build date.
    No authentication required.
    """
    return {
        "version": VERSION,
        "git_commit": GIT_COMMIT,
        "build_date": BUILD_DATE,
    }
