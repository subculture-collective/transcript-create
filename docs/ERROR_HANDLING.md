# Error Handling & Validation System

## Overview

This document describes the comprehensive error handling and validation system implemented for the transcript-create application. The system provides consistent, user-friendly error messages while maintaining security by not exposing internal implementation details.

## Architecture

### Custom Exceptions (`app/exceptions.py`)

All custom exceptions inherit from `AppError` (formerly `AppException`), which provides:

- **Consistent error format**: Every error has a `error_code`, `message`, `status_code`, and optional `details`
- **JSON serialization**: `to_dict()` method for easy API responses
- **HTTP status code mapping**: Each exception knows its appropriate HTTP status code

#### Available Exceptions

| Exception | Status Code | Usage |
|-----------|-------------|-------|
| `JobNotFoundError` | 404 | When a job cannot be found by ID |
| `VideoNotFoundError` | 404 | When a video cannot be found by ID |
| `InvalidURLError` | 400 | When a URL is invalid or not supported |
| `QuotaExceededError` | 402 | When user exceeds their quota |
| `TranscriptNotReadyError` | 409 | When transcript is requested but not ready |
| `DatabaseError` | 500 | When database operations fail |
| `ExternalServiceError` | 503 | When external services (Stripe, OAuth, etc.) fail |
| `AuthenticationError` | 401 | When authentication is required but not provided |
| `AuthorizationError` | 403 | When user lacks required permissions |
| `ValidationError` | 422 | When input validation fails |
| `RateLimitError` | 429 | When rate limits are exceeded |
| `DuplicateJobError` | 409 | When attempting to create duplicate jobs |

### Exception Handlers (`app/main.py`)

Centralized exception handlers convert exceptions to consistent JSON responses:

1. **AppError Handler**: Handles all custom application exceptions
2. **RequestValidationError Handler**: Handles Pydantic validation errors
3. **SQLAlchemy Handler**: Handles database errors without exposing SQL details
4. **General Exception Handler**: Catches all unhandled exceptions

### Error Response Format

All errors follow a consistent JSON structure:

```json
{
  "error": "error_code",
  "message": "Human-readable error message",
  "details": {
    "field": "optional_field_name",
    "additional": "context"
  }
}
```

### Request Tracking

Every request gets a unique `X-Request-ID` header for tracing:

```python
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```

## Input Validation

### Pydantic Schemas (`app/schemas.py`)

Enhanced with validators:

#### JobCreate Schema

- **URL validation**: Ensures URLs are valid HTTP/HTTPS URLs
- **YouTube URL validation**: Custom validator ensures only YouTube URLs are accepted
- **Kind validation**: Uses `Literal["single", "channel"]` for type safety

```python
class JobCreate(BaseModel):
    url: HttpUrl
    kind: Literal["single", "channel"] = "single"

    @field_validator("url")
    @classmethod
    def validate_youtube_url(cls, v: HttpUrl) -> HttpUrl:
        # Validates against YouTube URL patterns
```

#### SearchQuery Schema

Validates search parameters:

```python
class SearchQuery(BaseModel):
    q: str = Field(..., min_length=1, max_length=500)
    source: Literal["native", "youtube"] = "native"
    video_id: Optional[uuid.UUID] = None
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)
```

## Database Error Handling (`app/crud.py`)

### Retry Logic

All database operations are wrapped with a retry decorator that:

- Detects transient errors (connection issues, timeouts, deadlocks)
- Retries up to 3 times with exponential backoff
- Logs retry attempts for debugging
- Re-raises non-transient errors immediately

```python
@_retry_on_transient_error
def create_job(db, kind: str, url: str):
    # Database operation
```

### Error Sanitization

- SQL errors are caught by the global exception handler
- Internal details are logged server-side
- Users receive generic "database error" messages
- Connection errors return 503 (Service Unavailable)

## Route Updates

All route files have been updated to use custom exceptions:

- **`app/routes/jobs.py`**: Uses `JobNotFoundError`
- **`app/routes/videos.py`**: Uses `VideoNotFoundError`, `TranscriptNotReadyError`
- **`app/routes/search.py`**: Uses `ValidationError`, `QuotaExceededError`, `ExternalServiceError`
- **`app/routes/billing.py`**: Uses `AuthenticationError`, `ExternalServiceError`, `ValidationError`
- **`app/routes/auth.py`**: Uses `ExternalServiceError`, `ValidationError`
- **`app/routes/favorites.py`**: Uses `AuthenticationError`, `ValidationError`
- **`app/routes/exports.py`**: Uses `TranscriptNotReadyError`
- **`app/routes/admin.py`**: Uses `AuthorizationError`, `ValidationError`

## Logging

### Structured Logging

All errors are logged with context:

```python
logger.warning(
    "Application error: %s | path=%s request_id=%s details=%s",
    exc.message,
    request.url.path,
    request_id,
    exc.details,
)
```

### Sensitive Data Protection

- SQL details are not exposed to users
- Authentication tokens are not logged
- Personal information is sanitized

## Testing

### Unit Tests (`tests/test_exceptions.py`)

- Tests all exception types
- Verifies error codes and status codes
- Tests serialization with `to_dict()`
- Validates detail fields

### Integration Tests (`tests/test_error_handling.py`)

- Tests error response format across all endpoints
- Validates HTTP status codes
- Tests request ID tracking
- Tests YouTube URL validation
- Tests transcript error scenarios

### Running Tests

```bash
# Run all exception tests
pytest tests/test_exceptions.py -v

# Run error handling integration tests
pytest tests/test_error_handling.py -v

# Run schema validation tests
pytest tests/test_schemas.py -v
```

## Usage Examples

### Raising Custom Exceptions

```python
from app.exceptions import JobNotFoundError, ValidationError

# In route handlers
@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, db=Depends(get_db)):
    job = crud.fetch_job(db, job_id)
    if not job:
        raise JobNotFoundError(str(job_id))
    return job
```

### Handling External Service Errors

```python
from app.exceptions import ExternalServiceError

try:
    response = requests.post(external_api_url, json=data)
    response.raise_for_status()
except requests.exceptions.RequestException as e:
    raise ExternalServiceError("External API", str(e))
```

### Input Validation

```python
from app.exceptions import ValidationError

if not payload.get("required_field"):
    raise ValidationError(
        "Required field is missing",
        field="required_field"
    )
```

## HTTP Status Code Reference

| Code | Description | Use Case |
|------|-------------|----------|
| 400 | Bad Request | Invalid input, malformed data |
| 401 | Unauthorized | Authentication required |
| 402 | Payment Required | Quota exceeded, upgrade needed |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 409 | Conflict | Duplicate resource, state conflict |
| 422 | Unprocessable Entity | Validation errors |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Unexpected server errors |
| 503 | Service Unavailable | Database/external service unavailable |

## Best Practices

### Do's ✅

- Always use custom exceptions instead of `HTTPException`
- Provide user-friendly error messages
- Include relevant context in `details` field
- Log errors with request IDs for tracing
- Use specific exception types for different scenarios

### Don'ts ❌

- Don't expose internal implementation details (SQL, stack traces)
- Don't log sensitive information (passwords, tokens)
- Don't use generic error messages without context
- Don't raise `HTTPException` directly (use custom exceptions)
- Don't include raw exception messages in user responses

## Future Improvements

Potential enhancements:

1. **Rate Limiting**: Implement per-endpoint rate limiting with `RateLimitError`
2. **Error Analytics**: Track error patterns for debugging
3. **Localization**: Support multiple languages for error messages
4. **Error Monitoring**: Integration with monitoring services (Sentry, etc.)
5. **Retry Strategies**: More sophisticated retry logic for different error types

## References

- FastAPI Error Handling: <https://fastapi.tiangolo.com/tutorial/handling-errors/>
- RFC 7807 Problem Details: <https://tools.ietf.org/html/rfc7807>
- Pydantic Validation: <https://docs.pydantic.dev/latest/concepts/validators/>
