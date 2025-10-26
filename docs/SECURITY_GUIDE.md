# Security Guide

This document describes the security features implemented in transcript-create and best practices for deployment.

## Table of Contents

1. [Authentication & Authorization](#authentication--authorization)
2. [API Key Management](#api-key-management)
3. [Session Security](#session-security)
4. [OAuth Security](#oauth-security)
5. [Rate Limiting](#rate-limiting)
6. [Security Headers](#security-headers)
7. [Audit Logging](#audit-logging)
8. [Configuration](#configuration)
9. [Best Practices](#best-practices)

## Authentication & Authorization

### Authentication Methods

The API supports two authentication methods:

1. **Session Cookies** (recommended for web applications)
   - Set after successful OAuth login
   - HttpOnly, SameSite=lax, Secure (in production)
   - Automatic expiration and refresh

2. **API Keys** (recommended for programmatic access)
   - Bearer token authentication
   - SHA-256 hashed storage
   - Configurable expiration
   - Per-user management

### Role-Based Access Control (RBAC)

Three user roles are supported:

- **user** - Default role for authenticated users
- **pro** - Pro plan subscribers (inherits user permissions)
- **admin** - Administrators (inherits pro permissions)

#### Using RBAC in Endpoints

```python
from fastapi import Depends
from app.security import require_role, ROLE_ADMIN, ROLE_PRO

@router.get("/admin/dashboard")
def admin_dashboard(user=Depends(require_role(ROLE_ADMIN))):
    """Admin-only endpoint."""
    return {"message": "Admin access granted"}

@router.get("/pro/feature")
def pro_feature(user=Depends(require_role(ROLE_PRO))):
    """Pro users and admins can access this."""
    return {"message": "Pro feature"}
```

## API Key Management

### Creating API Keys

**Endpoint:** `POST /api-keys`

```bash
curl -X POST https://api.example.com/api-keys \
  -H "Cookie: tc_session=YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My API Key",
    "expires_days": 365
  }'
```

**Response:**
```json
{
  "api_key": "tc_XxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXx",
  "key": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "name": "My API Key",
    "key_prefix": "tc_XxXxXx...",
    "created_at": "2025-10-26T04:00:00Z",
    "expires_at": "2026-10-26T04:00:00Z",
    "last_used_at": null,
    "revoked_at": null,
    "scopes": null
  }
}
```

**⚠️ Important:** The full API key is only shown once. Store it securely!

### Using API Keys

Include the API key in requests using either:

1. **Authorization header:**
   ```bash
   curl https://api.example.com/jobs \
     -H "Authorization: Bearer tc_YOUR_API_KEY"
   ```

2. **X-API-Key header:**
   ```bash
   curl https://api.example.com/jobs \
     -H "X-API-Key: tc_YOUR_API_KEY"
   ```

### Listing API Keys

```bash
curl https://api.example.com/api-keys \
  -H "Cookie: tc_session=YOUR_SESSION_TOKEN"
```

### Revoking API Keys

```bash
curl -X DELETE https://api.example.com/api-keys/KEY_ID \
  -H "Cookie: tc_session=YOUR_SESSION_TOKEN"
```

## Session Security

### Session Configuration

Sessions are configured with secure defaults:

```python
# .env configuration
SESSION_EXPIRE_HOURS=24           # Session lifetime
SESSION_REFRESH_THRESHOLD_HOURS=12  # Auto-refresh threshold
```

### Session Cookie Attributes

- **httpOnly=true** - Prevents JavaScript access (XSS protection)
- **sameSite=lax** - CSRF protection
- **secure=true** - HTTPS only (in production)
- **maxAge** - Configurable expiration

### Session Refresh

Sessions are automatically refreshed when:
- User makes an authenticated request
- Session age exceeds `SESSION_REFRESH_THRESHOLD_HOURS`
- Session is still valid (not expired)

This extends the session lifetime without requiring re-authentication.

## OAuth Security

### CSRF Protection

OAuth flows use the `state` parameter to prevent CSRF attacks:

1. Random state token generated before redirect
2. State stored in secure session
3. State validated on callback
4. One-time use (cleared after validation)

Enable/disable state validation:
```bash
# .env
OAUTH_STATE_VALIDATION=true
```

### Nonce for Replay Protection

Nonces are generated and can be used for additional replay protection in OAuth flows.

### OAuth Configuration

```bash
# Google OAuth
OAUTH_GOOGLE_CLIENT_ID=your_client_id
OAUTH_GOOGLE_CLIENT_SECRET=your_secret
OAUTH_GOOGLE_REDIRECT_URI=https://api.example.com/auth/callback/google

# Twitch OAuth
OAUTH_TWITCH_CLIENT_ID=your_client_id
OAUTH_TWITCH_CLIENT_SECRET=your_secret
OAUTH_TWITCH_REDIRECT_URI=https://api.example.com/auth/callback/twitch
```

## Rate Limiting

### Configuration

```bash
# .env
ENABLE_RATE_LIMITING=true
MAX_LOGIN_ATTEMPTS=5
LOGIN_ATTEMPT_WINDOW_MINUTES=15
```

### Default Limits

- **General endpoints:** 100 requests/minute per IP
- **Health checks:** Unlimited
- **Metrics:** Unlimited

### Rate Limit Response

When rate limited, the API returns:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/json

{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Please try again later."
}
```

## Security Headers

The following security headers are automatically added to all responses:

### Headers Applied

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000 (production only)
Content-Security-Policy: default-src 'self'; ...
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

### HSTS (HTTP Strict Transport Security)

Only enabled in production (when `ENVIRONMENT=production`):
```
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

## Audit Logging

### What is Logged

Security-relevant events are logged to the `audit_logs` table:

- Login success/failure
- Logout events
- API key creation/revocation
- Permission denied attempts
- Admin actions
- Rate limit violations

### Audit Log Structure

```sql
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id UUID REFERENCES users(id),
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    ip_address TEXT,
    user_agent TEXT,
    success BOOLEAN NOT NULL DEFAULT true,
    details JSONB NOT NULL DEFAULT '{}'
);
```

### Viewing Audit Logs

```python
from app.audit import get_audit_logs

# Get recent logs for a user
logs = get_audit_logs(
    db,
    user_id=user_id,
    limit=100,
    offset=0
)
```

### Audit Log Cleanup

Logs are retained for 90 days by default. Use the cleanup function:

```python
from app.audit import cleanup_old_audit_logs

# Remove logs older than 90 days
deleted = cleanup_old_audit_logs(db, days_to_keep=90)
```

## Configuration

### Environment Variables

```bash
# Security
ENVIRONMENT=production              # development, staging, production
SESSION_SECRET=generate_secure_key  # openssl rand -hex 32
ENABLE_RATE_LIMITING=true
SESSION_EXPIRE_HOURS=24
SESSION_REFRESH_THRESHOLD_HOURS=12
API_KEY_EXPIRE_DAYS=365
OAUTH_STATE_VALIDATION=true

# CORS
FRONTEND_ORIGIN=https://app.example.com
CORS_ALLOW_ORIGINS=https://admin.example.com,https://mobile.example.com

# Admin Access
ADMIN_EMAILS=admin@example.com,security@example.com
```

### Production Checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Generate secure `SESSION_SECRET` (min 32 bytes)
- [ ] Enable `OAUTH_STATE_VALIDATION=true`
- [ ] Configure `ADMIN_EMAILS` with actual admin emails
- [ ] Use HTTPS only (required for secure cookies)
- [ ] Set strong OAuth client secrets
- [ ] Enable `ENABLE_RATE_LIMITING=true`
- [ ] Configure proper CORS origins (don't use wildcards)
- [ ] Review and adjust session expiration times
- [ ] Set up regular audit log cleanup

## Best Practices

### Secrets Management

1. **Never commit secrets to Git**
   - Use `.env` files (gitignored)
   - Use secret managers (AWS Secrets Manager, HashiCorp Vault, etc.)

2. **Rotate secrets regularly**
   - OAuth client secrets: annually
   - API keys: set expiration dates
   - Session secrets: on security incidents

3. **Use environment-specific secrets**
   - Different secrets for dev/staging/production
   - Test mode keys in development

### API Key Security

1. **Treat API keys like passwords**
   - Never log full keys
   - Never expose in client-side code
   - Store securely (encrypted at rest)

2. **Use expiration dates**
   - Set reasonable expiration periods
   - Review and rotate regularly

3. **Revoke unused keys**
   - Audit and remove inactive keys
   - Revoke immediately if compromised

### Session Security

1. **Configure appropriate expiration**
   - Balance security vs. user convenience
   - Shorter for sensitive operations
   - Use session refresh for better UX

2. **Monitor for suspicious activity**
   - Multiple sessions from different IPs
   - Rapid session creation
   - Failed authentication attempts

3. **Force logout on security events**
   - Password changes
   - Permission changes
   - Suspicious activity detected

### CORS Configuration

1. **Whitelist specific origins**
   ```bash
   # Good
   CORS_ALLOW_ORIGINS=https://app.example.com
   
   # Bad
   CORS_ALLOW_ORIGINS=*
   ```

2. **Restrict HTTP methods**
   - Only allow necessary methods
   - Current: GET, POST, PUT, DELETE, PATCH

3. **Validate Origin header**
   - Handled automatically by CORSMiddleware
   - Never echo back Origin header

### Monitoring & Alerting

1. **Monitor audit logs**
   - Failed authentication attempts
   - Permission denied events
   - Unusual patterns

2. **Set up alerts**
   - High rate of failed logins
   - API key creation by admins
   - Rate limit violations

3. **Regular security reviews**
   - Review active API keys
   - Audit admin access
   - Check for suspicious patterns

## Support

For security issues, please contact: [security@example.com](mailto:security@example.com)

**Do not disclose security vulnerabilities publicly.**
