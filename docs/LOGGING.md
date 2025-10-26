# Structured Logging & Observability

This document describes the structured logging system implemented in transcript-create.

## Overview

The application uses structured JSON logging with correlation IDs for request tracing across API and worker services. All logs are formatted consistently and ready for aggregation by centralized logging systems like CloudWatch, ELK, or Datadog.

## Features

- **Structured JSON Output**: All logs are formatted as JSON with consistent fields
- **Request Tracing**: Unique request IDs track API calls end-to-end
- **Context Propagation**: Request ID, user ID, job ID, and video ID are automatically included in logs
- **Sensitive Data Protection**: Passwords, tokens, API keys, and PII are automatically redacted
- **Configurable Log Levels**: Control verbosity via environment variables
- **Optional Sentry Integration**: Error tracking and performance monitoring
- **Service Identification**: Logs are tagged with service name (api, worker, script)

## Configuration

### Environment Variables

Set these in your `.env` file:

```bash
# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# Log format: 'json' for structured logs, 'text' for plain text (dev only)
LOG_FORMAT=json

# Optional Sentry integration
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

### Log Levels

- **DEBUG**: Detailed diagnostic info (polling, model loading, chunk processing)
- **INFO**: Significant events (job created, video completed, API requests)
- **WARNING**: Unexpected but handled situations (retries, fallbacks, missing captions)
- **ERROR**: Errors requiring attention (job failures, database errors)
- **CRITICAL**: System-level failures (service unavailable, startup failures)

## JSON Log Format

Each log entry is a JSON object with the following structure:

```json
{
  "timestamp": "2025-10-25T03:45:12.123456Z",
  "level": "INFO",
  "service": "api",
  "logger": "app.main",
  "message": "Video processing completed successfully",
  "request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "user_id": "usr_abc123",
  "job_id": "job_xyz789",
  "video_id": "vid_def456",
  "extra": {
    "total_duration_seconds": 125.43,
    "segment_count": 487
  }
}
```

### Standard Fields

- `timestamp`: ISO 8601 UTC timestamp
- `level`: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `service`: Service name (api, worker, script.*)
- `logger`: Python module name
- `message`: Human-readable log message (sanitized)

### Context Fields (when available)

- `request_id`: Unique ID for API requests (also in X-Request-ID header)
- `user_id`: Authenticated user ID
- `job_id`: Current job being processed
- `video_id`: Current video being processed

### Additional Fields

- `extra`: Custom fields passed via `logger.info("msg", extra={...})`
- `exception`: Stack trace (for ERROR/CRITICAL with exceptions)
- `exc_type`: Exception class name
- `location`: File, line, function (for non-INFO logs)

## Usage Examples

### API Routes

```python
from app.logging_config import get_logger

logger = get_logger(__name__)

@router.post("/jobs")
def create_job(payload: JobCreate):
    logger.info(
        "Job created",
        extra={
            "job_kind": payload.kind,
            "url": payload.url,
        }
    )
```

The request_id and user_id are automatically included from context.

### Worker Processing

```python
from app.logging_config import get_logger, video_id_ctx

logger = get_logger(__name__)

def process_video(video_id):
    # Set context for all logs in this scope
    video_id_ctx.set(str(video_id))
    
    logger.info("Video processing started")
    # ... processing ...
    logger.info(
        "Video processing completed",
        extra={"duration_seconds": 125.43}
    )
    
    # Clear context when done
    video_id_ctx.set(None)
```

### Error Logging

```python
try:
    process_dangerous_operation()
except Exception as e:
    logger.error(
        "Operation failed",
        extra={"operation": "dangerous_op", "error": str(e)},
        exc_info=True  # Include stack trace
    )
```

## Sensitive Data Protection

The logging system automatically redacts sensitive information:

- **Passwords**: `password="secret"` → `password=***`
- **Tokens**: `token=abc123` → `token=***`
- **API Keys**: `api_key=sk_live_123` → `api_key=***`
- **Secrets**: `secret=xyz` → `secret=***`
- **Authorization Headers**: `Authorization: Bearer abc` → `Authorization: Bearer ***`
- **Cookies**: `cookie: session=abc` → `cookie: ***`
- **Credit Cards**: `4532-1234-5678-9010` → `****-****-****-****`

### Email Masking

Use `SensitiveDataFilter.mask_email()` to safely log email addresses:

```python
from app.logging_config import SensitiveDataFilter

masked = SensitiveDataFilter.mask_email("user@example.com")
# Returns: "us***@example.com"
```

## Request Tracing

### End-to-End Flow

1. **API Request**: Middleware generates unique request_id
2. **Response Header**: X-Request-ID header sent to client
3. **Database Operations**: request_id in all query logs
4. **Worker Processing**: video_id and job_id added when processing
5. **Error Tracking**: All exceptions include full context

### Correlation Example

Search logs by request_id to trace a complete request:

```bash
# JSON logs - filter by request_id
cat api.log | jq 'select(.request_id == "f47ac10b...")'

# Or with centralized logging (e.g., CloudWatch Insights)
fields @timestamp, level, message, extra
| filter request_id = "f47ac10b..."
| sort @timestamp asc
```

## Sentry Integration (Optional)

To enable error tracking:

1. Install Sentry SDK:

   ```bash
   pip install sentry-sdk==2.19.2
   ```

2. Configure in `.env`:

   ```bash
   SENTRY_DSN=https://your-key@sentry.io/project-id
   SENTRY_ENVIRONMENT=production
   SENTRY_TRACES_SAMPLE_RATE=0.1  # 10% of transactions
   ```

3. Errors are automatically captured and sent to Sentry with:
   - Full stack traces
   - Request context (headers, URL, method)
   - User information (if authenticated)
   - Custom tags (service, video_id, job_id)

## Centralized Logging

### CloudWatch Logs

Structure your log groups by service:

```
/aws/ecs/transcript-create/api
/aws/ecs/transcript-create/worker
```

Query with CloudWatch Logs Insights:

```
fields @timestamp, level, message, request_id, video_id
| filter level = "ERROR"
| sort @timestamp desc
| limit 50
```

### ELK Stack (Elasticsearch, Logstash, Kibana)

Logstash configuration:

```ruby
input {
  file {
    path => "/var/log/transcript-create/*.log"
    codec => "json"
  }
}

filter {
  # JSON is already parsed, just add index
  mutate {
    add_field => { "[@metadata][index]" => "transcript-create" }
  }
}

output {
  elasticsearch {
    hosts => ["localhost:9200"]
    index => "%{[@metadata][index]}-%{+YYYY.MM.dd}"
  }
}
```

### Prometheus/Grafana

While logs are in JSON, you can extract metrics:

```python
# Count log entries by level
sum(rate(logs_total{level="ERROR", service="worker"}[5m]))

# P95 processing time
histogram_quantile(0.95, 
  rate(processing_duration_seconds_bucket{service="worker"}[5m]))
```

## Monitoring Dashboards

### Key Metrics to Track

From logs, you can extract:

- **Job Completion Rate**: INFO logs with "completed successfully"
- **Error Rate**: ERROR/CRITICAL log count by service
- **Average Processing Time**: Parse `duration_seconds` from extra fields
- **Queue Depth**: Count "No pending videos" DEBUG logs vs "Picked video" INFO logs

### Sample Queries

**Failed jobs in last hour:**

```
level: ERROR AND message: "failed" AND @timestamp >= now-1h
```

**Processing times by video:**

```
message: "Video processing completed" 
| stats avg(extra.total_duration_seconds) by video_id
```

**Top errors:**

```
level: ERROR 
| stats count() by exc_type, service
| sort count desc
```

## Testing

Run logging tests:

```bash
pytest tests/test_logging.py -v
```

Tests cover:

- JSON formatting
- Context propagation
- Sensitive data redaction
- Logger factory
- Configuration

## Best Practices

1. **Use Structured Extra Fields**: Instead of string formatting, use extra:

   ```python
   # Good
   logger.info("Job completed", extra={"job_id": job_id, "duration": 42})
   
   # Avoid
   logger.info(f"Job {job_id} completed in {42}s")
   ```

2. **Set Context Early**: Set context vars at the start of operations:

   ```python
   video_id_ctx.set(str(video_id))
   try:
       # All logs here include video_id automatically
       process_video(video_id)
   finally:
       video_id_ctx.set(None)
   ```

3. **Include Useful Metadata**: Add performance metrics, counts, IDs:

   ```python
   logger.info(
       "Batch processed",
       extra={
           "batch_size": len(items),
           "duration_ms": elapsed * 1000,
           "success_count": successes,
           "error_count": errors,
       }
   )
   ```

4. **Log Boundaries**: Always log at operation start/end:

   ```python
   logger.info("Video processing started")
   try:
       process()
       logger.info("Video processing completed successfully")
   except Exception as e:
       logger.error("Video processing failed", exc_info=True)
       raise
   ```

5. **Use Appropriate Levels**:
   - DEBUG: Polling loops, conditional branches
   - INFO: State transitions, completions
   - WARNING: Fallbacks, retries, degraded functionality
   - ERROR: Operation failures, user-facing errors
   - CRITICAL: Service unavailable, startup failures

## Migration from Old Logging

The old logging used string formatting:

```python
# Old
logging.info("Job %s created from %s", job_id, url)
```

New structured logging:

```python
# New
logger.info("Job created", extra={"job_id": str(job_id), "url": url})
```

Benefits:

- Searchable by field (e.g., filter by job_id)
- Type-safe (no formatting errors)
- Parseable by log aggregators
- Consistent structure across services

## Troubleshooting

### Logs not appearing

Check LOG_LEVEL in .env:

```bash
echo $LOG_LEVEL  # Should be INFO or DEBUG
```

### JSON parsing errors

Ensure LOG_FORMAT=json:

```bash
cat app.log | jq .  # Should parse without errors
```

### Missing context fields

Context is not persisted across async boundaries. Make sure to set context in each worker/thread:

```python
# In each async task
request_id_ctx.set(request_id)
```

### Sentry not capturing errors

1. Check SENTRY_DSN is set
2. Install sentry-sdk: `pip install sentry-sdk`
3. Verify network access to sentry.io
4. Check logs for "Sentry initialized" message

## See Also

- Python logging docs: <https://docs.python.org/3/library/logging.html>
- Structured logging best practices: <https://www.structlog.org/>
- Sentry Python SDK: <https://docs.sentry.io/platforms/python/>
- CloudWatch Logs Insights: <https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/>
