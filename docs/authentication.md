# Authentication Guide

This guide explains how authentication works in the Transcript Create API.

## Overview

Transcript Create uses OAuth 2.0 for user authentication with support for:
- Google OAuth
- Twitch OAuth

After successful authentication, the API uses session cookies to maintain user state.

## OAuth Flow

### Google OAuth

#### 1. Initiate Login

Redirect users to the Google login endpoint:

```
GET /auth/login/google
```

This redirects to Google's OAuth consent screen where users authorize your application.

#### 2. OAuth Callback

After user consent, Google redirects back to:

```
GET /auth/callback/google?code=...&state=...
```

The API automatically:
1. Exchanges the authorization code for an access token
2. Fetches user profile information
3. Creates or updates the user in the database
4. Creates a session and sets a cookie
5. Redirects to the frontend application

#### 3. Session Cookie

The response sets a secure HTTP-only cookie:

```
Set-Cookie: tc_session=<token>; HttpOnly; Secure; SameSite=Lax; Max-Age=604800
```

This cookie is automatically sent with subsequent requests to authenticate the user.

### Twitch OAuth

The Twitch OAuth flow works identically to Google:

#### 1. Initiate Login
```
GET /auth/login/twitch
```

#### 2. OAuth Callback
```
GET /auth/callback/twitch?code=...&state=...
```

Same automatic processing as Google OAuth.

## Session Management

### Check Authentication Status

Get information about the currently authenticated user:

```bash
curl https://api.example.com/auth/me \
  -H "Cookie: tc_session=your_session_token"
```

Response when authenticated:
```json
{
  "user": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "email": "user@example.com",
    "name": "John Doe",
    "avatar_url": "https://example.com/avatar.jpg",
    "plan": "free",
    "searches_used_today": 5,
    "search_limit": 100
  }
}
```

Response when not authenticated:
```json
{
  "user": null
}
```

### Logout

Invalidate the current session:

```bash
curl -X POST https://api.example.com/auth/logout \
  -H "Cookie: tc_session=your_session_token"
```

Response:
```json
{
  "ok": true
}
```

This clears the session cookie and removes the session from the database.

## User Plans

Users have one of two plans:

### Free Plan
- Limited daily searches (100 by default)
- Limited daily exports
- Full transcription access

### Pro Plan
- Unlimited searches
- Unlimited exports
- Priority processing
- Managed via Stripe subscription

Check plan details:
```bash
curl https://api.example.com/auth/me
```

The response includes:
- `plan`: "free" or "pro"
- `searches_used_today`: Current daily usage (free only)
- `search_limit`: Daily quota (free only)

## Configuration

### Environment Variables

Configure OAuth providers with these environment variables:

```bash
# Google OAuth
OAUTH_GOOGLE_CLIENT_ID=your_google_client_id
OAUTH_GOOGLE_CLIENT_SECRET=your_google_client_secret
OAUTH_GOOGLE_REDIRECT_URI=https://api.example.com/auth/callback/google

# Twitch OAuth
OAUTH_TWITCH_CLIENT_ID=your_twitch_client_id
OAUTH_TWITCH_CLIENT_SECRET=your_twitch_client_secret
OAUTH_TWITCH_REDIRECT_URI=https://api.example.com/auth/callback/twitch

# Frontend
FRONTEND_ORIGIN=https://app.example.com
```

### OAuth Setup

#### Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google+ API
4. Create OAuth 2.0 credentials
5. Add authorized redirect URI: `https://api.example.com/auth/callback/google`
6. Copy Client ID and Client Secret to environment variables

#### Twitch OAuth Setup

1. Go to [Twitch Developer Console](https://dev.twitch.tv/console)
2. Register a new application
3. Add OAuth redirect URL: `https://api.example.com/auth/callback/twitch`
4. Set category to "Website Integration"
5. Copy Client ID and Client Secret to environment variables

## Security Considerations

### Session Tokens

Session tokens are:
- 32-byte URL-safe random strings
- Stored securely in the database
- Expire after 7 days of inactivity
- HTTP-only cookies (not accessible via JavaScript)
- Secure flag (HTTPS only in production)
- SameSite=Lax to prevent CSRF

### User Data

User information stored includes:
- OAuth provider (Google/Twitch)
- OAuth subject ID (unique user identifier from provider)
- Email address
- Display name
- Avatar URL

Sensitive data like OAuth tokens are not stored permanently.

### CORS Configuration

The API restricts cross-origin requests to the configured frontend origin:

```python
CORS_ORIGINS = [settings.FRONTEND_ORIGIN]
```

## Error Handling

### Authentication Errors

**401 Unauthorized** - Authentication required
```json
{
  "error": "authentication_required",
  "message": "You must be logged in to access this resource",
  "details": {}
}
```

**403 Forbidden** - Insufficient permissions
```json
{
  "error": "authorization_error",
  "message": "You do not have permission to access this resource",
  "details": {}
}
```

### OAuth Errors

**503 Service Unavailable** - OAuth library not configured
```json
{
  "error": "external_service_error",
  "message": "OAuth authentication is not available",
  "details": {
    "service": "OAuth"
  }
}
```

**500 Internal Server Error** - OAuth flow failed
```json
{
  "error": "external_service_error",
  "message": "Authentication failed with Google/Twitch",
  "details": {
    "service": "Google OAuth"
  }
}
```

## Testing Authentication

### Development Testing

In development, you can manually set session cookies:

```bash
# Create a session in the database manually
# Then use the token in requests:
curl https://api.example.com/auth/me \
  -H "Cookie: tc_session=your_test_token"
```

### Integration Testing

Use the test client with cookie support:

```python
from fastapi.testclient import TestClient

client = TestClient(app)
response = client.post("/auth/login/google")
# Follow redirect, handle OAuth mock
response = client.get("/auth/me")
assert response.json()["user"] is not None
```

## Admin Access

Admin users have additional privileges:

- Access to `/admin/*` endpoints
- View event analytics
- Manage user plans
- Export event data

Admin status is set via the `is_admin` flag in the users table.

## Related Documentation

- [Getting Started](getting-started.md) - Basic API usage
- [Webhooks](webhooks.md) - Stripe webhook authentication
- [Examples](examples.md) - Code examples with authentication
