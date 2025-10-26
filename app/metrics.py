"""
Prometheus metrics definitions for the API service.

This module defines all metrics collected by the API service including:
- HTTP request metrics (duration, count, in-flight)
- Business metrics (jobs, videos, searches, exports)
- Database metrics (connections, query duration, errors)
"""

from prometheus_client import Counter, Gauge, Histogram, Summary
from prometheus_client import REGISTRY, CollectorRegistry, generate_latest
from prometheus_client.multiprocess import MultiProcessCollector
from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST
import os


# Use multi-process mode if PROMETHEUS_MULTIPROC_DIR is set (for uvicorn workers)
if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
    # Clear existing collectors from default registry
    REGISTRY._collector_to_names.clear()
    REGISTRY._names_to_collectors.clear()
    # Use multiprocess collector
    MultiProcessCollector(REGISTRY)


# HTTP Request Metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0),
)

http_requests_in_flight = Gauge(
    "http_requests_in_flight",
    "Number of HTTP requests currently being processed",
    ["method", "endpoint"],
)

# Business Metrics - Jobs
jobs_created_total = Counter(
    "jobs_created_total",
    "Total number of transcription jobs created",
    ["kind"],  # single or channel
)

jobs_completed_total = Counter(
    "jobs_completed_total",
    "Total number of transcription jobs completed successfully",
    ["kind"],
)

jobs_failed_total = Counter(
    "jobs_failed_total",
    "Total number of transcription jobs that failed",
    ["kind"],
)

# Business Metrics - Videos
videos_transcribed_total = Counter(
    "videos_transcribed_total",
    "Total number of videos successfully transcribed",
)

videos_failed_total = Counter(
    "videos_failed_total",
    "Total number of videos that failed transcription",
)

# Business Metrics - Search
search_queries_total = Counter(
    "search_queries_total",
    "Total number of search queries executed",
    ["backend"],  # postgres or opensearch
)

# Business Metrics - Exports
exports_total = Counter(
    "exports_total",
    "Total number of transcript exports",
    ["format"],  # srt, vtt, json, pdf
)

# Database Metrics
db_connections_active = Gauge(
    "db_connections_active",
    "Number of active database connections",
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

db_errors_total = Counter(
    "db_errors_total",
    "Total number of database errors",
    ["error_type"],
)

# Cache Metrics
cache_hits_total = Counter(
    "cache_hits_total",
    "Total number of cache hits",
    ["cache_type"],  # video, segments, search, etc.
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total number of cache misses",
    ["cache_type"],
)

cache_size_bytes = Gauge(
    "cache_size_bytes",
    "Current cache size in bytes",
)

cache_keys_total = Gauge(
    "cache_keys_total",
    "Total number of keys in cache",
)

# System Metrics (Application-level)
app_info = Gauge(
    "app_info",
    "Application information",
    ["version", "python_version"],
)


def setup_app_info():
    """Set application information metric."""
    import sys
    app_info.labels(version="0.1.0", python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}").set(1)
