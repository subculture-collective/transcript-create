# OAuth Exception Handling Improvements

## Overview

This document describes the improvements made to OAuth exception handling in response to review feedback on PR #80.

## Problem Statement

The original code in PR #80 had broad exception handling in OAuth callbacks that obscured the root cause of errors:

```python
except Exception as e:
    if isinstance(e, (ValidationError, ExternalServiceError)):
        raise
    raise ExternalServiceError("Google OAuth", str(e))
```

This approach had several issues:
1. The original exception type was lost
2. No logging of the actual error for debugging
3. All errors got the same generic treatment
4. Authlib-specific errors weren't distinguished from other errors

## Solution

### 1. Import Specific Exception Types

Added imports for authlib-specific exceptions:

```python
import logging

logger = logging.getLogger(__name__)

try:
    from authlib.common.errors import AuthlibBaseError
    from authlib.integrations.starlette_client import OAuth
    from authlib.oauth2.rfc6749.errors import OAuth2Error
except Exception:
    OAuth = None
    AuthlibBaseError = None
    OAuth2Error = None
```

### 2. Improved Exception Handling Order

Reordered exception handling to be more specific:

```python
try:
    # OAuth flow code...
    pass
except (ValidationError, ExternalServiceError):
    # Re-raise our custom exceptions without modification
    raise
except Exception as e:
    # Log the original exception with full context for debugging
    logger.error(
        "Google OAuth callback error: %s | type=%s",
        str(e),
        type(e).__name__,
        exc_info=True,
    )
    # Determine if it's an authlib-specific error
    error_type = type(e).__name__
    if AuthlibBaseError and isinstance(e, AuthlibBaseError):
        # Provide more specific error message for OAuth protocol errors
        raise ExternalServiceError(
            "Google OAuth",
            f"OAuth protocol error: {str(e)}",
            details={"error_type": error_type, "error": str(e)},
        )
    # For all other exceptions, wrap with generic message
    raise ExternalServiceError(
        "Google OAuth",
        f"Authentication failed: {str(e)}",
        details={"error_type": error_type},
    )
```

### 3. Enhanced ExternalServiceError

Updated `ExternalServiceError` to properly merge additional details:

```python
class ExternalServiceError(AppError):
    """Raised when an external service fails."""

    def __init__(self, service: str, message: str, details: Optional[Dict[str, Any]] = None):
        error_details = {"service": service}
        if details:
            error_details.update(details)
        super().__init__(
            error_code="external_service_error",
            message=f"{service} error: {message}",
            status_code=503,
            details=error_details,
        )
```

## Benefits

### 1. Better Debugging

The original exception type is now:
- Logged to server logs with full stack trace
- Included in error details as `error_type` field
- Visible to developers debugging issues

Example error response:
```json
{
  "error": "external_service_error",
  "message": "Google OAuth error: OAuth protocol error: state mismatch",
  "details": {
    "service": "Google OAuth",
    "error_type": "MismatchingStateError",
    "error": "state mismatch"
  }
}
```

### 2. Specific Error Messages

Different error messages for different scenarios:
- **OAuth protocol errors**: "OAuth protocol error: {specific error}"
- **General failures**: "Authentication failed: {error}"

### 3. Comprehensive Logging

Server logs now include:
```
ERROR Google OAuth callback error: state mismatch | type=MismatchingStateError
Traceback (most recent call last):
  ...
authlib.common.errors.MismatchingStateError: state mismatch
```

### 4. Cleaner Code

The explicit exception ordering makes the code's intent clear:
1. First, let our custom exceptions through unchanged
2. Then, catch and log all other exceptions
3. Provide specific handling for OAuth errors
4. Provide generic handling for everything else

## Testing

Updated tests to expect the new error response format:

```python
@patch("app.routes.auth.OAuth", None)
def test_auth_login_google_no_oauth(self, client: TestClient):
    """Test Google login when OAuth is not available."""
    response = client.get("/auth/login/google")
    assert response.status_code == 503
    data = response.json()
    assert data["error"] == "external_service_error"
    assert "Authentication library not installed" in data["message"]
```

## Files Modified

1. **app/routes/auth.py**
   - Added logging import and logger
   - Imported authlib exception types
   - Improved exception handling in `auth_callback_google` and `auth_callback_twitch`

2. **app/exceptions.py**
   - Updated `ExternalServiceError` to merge details properly

3. **tests/test_routes_auth.py**
   - Updated tests to expect new error response format (503 with structured JSON)

## Compliance

- ✅ All linting checks pass (ruff)
- ✅ Import ordering follows project conventions
- ✅ Code follows existing patterns in the codebase
- ✅ Tests updated to match new behavior

## Related Issues

- Addresses review comment on PR #80: https://github.com/subculture-collective/transcript-create/pull/80#discussion_r2462339927
- Based on comprehensive error handling system in PR #80
