# Structured Logging & Request Tracing - Implementation Summary

## Overview
This implementation adds comprehensive structured logging with JSON output, request tracing, and sensitive data protection to the transcript-create application.

## What Was Implemented

### 1. Core Logging Infrastructure (`app/logging_config.py`)
- **JSONFormatter**: Formats logs as structured JSON with consistent fields
- **SensitiveDataFilter**: Automatically redacts passwords, tokens, API keys, credit cards, and other sensitive data
- **Context Variables**: Track request_id, user_id, job_id, and video_id across async operations
- **StructuredLogger**: Logger adapter that automatically includes context in log messages
- **configure_logging()**: Configures logging for different services (api, worker, scripts)

### 2. API Updates
- **app/main.py**: 
  - Updated to use structured logging
  - Middleware sets request_id and user context
  - All exception handlers use structured format
  - Optional Sentry integration
  - Startup event logs service initialization

- **app/settings.py**: Added logging configuration:
  - `LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR, CRITICAL
  - `LOG_FORMAT`: json or text
  - `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`

- **app/crud.py**: Updated database retry logic to use structured logging

### 3. Worker Updates
All worker modules updated to use structured logging with appropriate context:

- **worker/loop.py**: 
  - Worker startup logged
  - Video/job context automatically set during processing
  - All operations logged with structured fields

- **worker/pipeline.py**: 
  - Pipeline stages logged (downloading, transcoding, transcribing)
  - Performance metrics (duration, segment counts)
  - YouTube metadata extraction logged

- **worker/audio.py**: ffmpeg and yt-dlp commands logged
- **worker/whisper_runner.py**: Model loading and GPU configuration logged
- **worker/diarize.py**: Diarization pipeline status and fallbacks logged
- **worker/youtube_captions.py**: Caption extraction logged

### 4. Script Updates
Updated all scripts to use structured logging:
- `scripts/backfill_fts.py`
- `scripts/backfill_youtube_captions.py`
- `scripts/opensearch_indexer.py`

### 5. Session & Auth Updates
- **app/common/session.py**: Sets user_id context when user is authenticated
- **app/routes/auth.py**: Updated to use structured logger

### 6. Testing
Created comprehensive test suite (`tests/test_logging.py`):
- 14 tests covering all logging functionality
- Tests for JSON formatting, context propagation, sensitive data filtering
- All tests passing

### 7. Documentation
- **docs/LOGGING.md**: Complete guide with:
  - Configuration instructions
  - JSON format specification
  - Usage examples
  - Best practices
  - Troubleshooting guide
  - Integration examples (CloudWatch, ELK, Prometheus)

- **Updated .env.example**: Added logging configuration examples

## Features

### Structured JSON Logging
```json
{
  "timestamp": "2025-10-25T04:00:49.671127Z",
  "level": "INFO",
  "service": "worker",
  "logger": "worker.pipeline",
  "message": "Video processing completed successfully",
  "request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "video_id": "vid_abc123",
  "extra": {
    "total_duration_seconds": 125.43,
    "segment_count": 487
  }
}
```

### Request Tracing
- Unique request_id for every API call (also in X-Request-ID header)
- User context automatically added for authenticated requests
- Job and video context in worker logs
- Full correlation across services

### Sensitive Data Protection
Automatically redacts:
- Passwords: `password="secret"` → `password=***`
- Tokens: `token=abc123` → `token=***`
- API Keys: `api_key=sk_live_123` → `api_key=***`
- Credit Cards: `4532-1234-5678-9010` → `****-****-****-****`
- Cookies and Authorization headers

### Configurable
- Log level via `LOG_LEVEL` environment variable
- Format via `LOG_FORMAT` (json or text)
- Optional Sentry integration via `SENTRY_DSN`

## Usage Examples

### API Route
```python
from app.logging_config import get_logger

logger = get_logger(__name__)

@router.post("/jobs")
def create_job(payload: JobCreate):
    logger.info(
        "Job created",
        extra={"job_kind": payload.kind, "url": payload.url}
    )
```

### Worker Processing
```python
from app.logging_config import get_logger, video_id_ctx

logger = get_logger(__name__)

def process_video(video_id):
    video_id_ctx.set(str(video_id))
    logger.info("Video processing started")
    # ... processing ...
    logger.info(
        "Video processing completed",
        extra={"duration_seconds": 125.43}
    )
    video_id_ctx.set(None)
```

### Error Logging
```python
try:
    dangerous_operation()
except Exception as e:
    logger.error(
        "Operation failed",
        extra={"operation": "dangerous_op"},
        exc_info=True
    )
```

## Configuration

### Environment Variables
```bash
# Log level
LOG_LEVEL=INFO

# Format (json for production, text for development)
LOG_FORMAT=json

# Optional Sentry integration
SENTRY_DSN=https://your-key@sentry.io/project
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

## Testing Results

All 14 tests passing:
- ✅ SensitiveDataFilter (6 tests)
- ✅ JSONFormatter (4 tests)
- ✅ StructuredLogger (2 tests)
- ✅ Configuration (2 tests)

## Security

- **CodeQL scan**: 0 alerts
- **Sensitive data protection**: Verified via tests
- **No PII in logs**: Email masking utility provided
- **Optional Sentry**: Only enabled with explicit DSN configuration

## Performance Impact

Minimal overhead:
- JSON serialization is fast (native Python json module)
- Context variables use efficient ContextVar (Python 3.7+)
- Sensitive data filtering uses pre-compiled regex patterns
- Log level filtering prevents unnecessary work

## Migration from Old Logging

Old style:
```python
logging.info("Job %s created from %s", job_id, url)
```

New style:
```python
logger.info("Job created", extra={"job_id": str(job_id), "url": url})
```

Benefits:
- Searchable by field
- Type-safe (no formatting errors)
- Parseable by log aggregators
- Consistent structure

## Integration with Monitoring

### CloudWatch Logs Insights
```
fields @timestamp, level, message, video_id
| filter level = "ERROR"
| sort @timestamp desc
```

### ELK Stack
Logs are JSON and ready for Elasticsearch ingestion via Logstash or Filebeat.

### Prometheus/Grafana
Extract metrics from structured logs:
- Error rates by service
- Processing times by video
- Queue depth tracking

## Next Steps

For production deployment:
1. Set `LOG_LEVEL=INFO` in production
2. Set `LOG_FORMAT=json` for structured output
3. Configure log rotation (e.g., logrotate, CloudWatch retention)
4. Set up centralized logging (CloudWatch, ELK, Datadog)
5. Optional: Configure Sentry for error tracking
6. Create dashboards based on log metrics

## Files Changed

### New Files
- `app/logging_config.py` (263 lines)
- `tests/test_logging.py` (256 lines)
- `docs/LOGGING.md` (366 lines)

### Modified Files
- `app/main.py` - Structured logging, middleware, Sentry
- `app/settings.py` - Logging configuration
- `app/crud.py` - Structured error logging
- `app/routes/auth.py` - Structured logger
- `app/common/session.py` - User context tracking
- `worker/loop.py` - Worker service logging
- `worker/pipeline.py` - Pipeline stage logging
- `worker/audio.py` - Command logging
- `worker/whisper_runner.py` - Model loading logs
- `worker/diarize.py` - Diarization status
- `worker/youtube_captions.py` - Caption extraction
- `scripts/backfill_fts.py` - Script logging
- `scripts/backfill_youtube_captions.py` - Script logging
- `scripts/opensearch_indexer.py` - Script logging
- `.env.example` - Logging configuration
- `requirements.txt` - Optional sentry-sdk

Total: 3 new files, 16 modified files

## Success Criteria Met

All requirements from the issue have been implemented:

✅ Standardized logging format across all services
✅ Python logging with structured JSON output
✅ Configurable log levels via environment
✅ Request ID tracking for API calls
✅ All log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
✅ Context logging (request_id, user_id, job_id, video_id)
✅ Sensitive data protection (verified via tests)
✅ Log rotation ready (standard Python logging handlers)
✅ Worker pipeline logging with metrics
✅ Error tracking integration (optional Sentry)
✅ Monitoring-ready log format
✅ All tests passing
✅ Comprehensive documentation

## Conclusion

The structured logging implementation provides a production-ready observability foundation for transcript-create. All logs are now:
- **Consistent**: Same format across all services
- **Searchable**: JSON structure enables field-based queries
- **Traceable**: Request IDs connect related operations
- **Secure**: Sensitive data automatically protected
- **Actionable**: Rich context enables debugging and monitoring
