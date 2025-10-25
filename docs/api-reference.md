# API Reference

Complete reference documentation for all Transcript Create API endpoints.

## Base URL

```
https://api.example.com
```

All endpoints use HTTPS. The API accepts JSON request bodies and returns JSON responses.

## Authentication

Most endpoints require authentication via session cookies. See [Authentication Guide](authentication.md) for details.

Include cookies in requests:
- JavaScript: `credentials: 'include'`
- cURL: `-H "Cookie: tc_session=..."`
- Python requests: Use `Session()` object

## Table of Contents

- [Health Check](#health-check)
- [Jobs](#jobs)
- [Videos](#videos)
- [Search](#search)
- [Exports](#exports)
- [Authentication](#authentication-1)
- [Billing](#billing)
- [Favorites](#favorites)
- [Events](#events)
- [Admin](#admin)

---

## Health Check

### GET /health

Check if the API service is running.

**Authentication:** Not required

**Response 200:**
```json
{
  "status": "ok"
}
```

---

## Jobs

Create and monitor transcription jobs for YouTube videos and channels.

### POST /jobs

Create a new transcription job.

**Authentication:** Required

**Request Body:**
```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "kind": "single"
}
```

**Parameters:**
- `url` (string, required): YouTube video or channel URL
- `kind` (string, optional): `"single"` or `"channel"` (default: `"single"`)

**Response 200:**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "kind": "single",
  "state": "pending",
  "error": null,
  "created_at": "2025-10-25T10:30:00Z",
  "updated_at": "2025-10-25T10:30:00Z"
}
```

**Job States:**
- `pending`: Job created, waiting to be processed
- `expanded`: Videos identified (for channel jobs)
- `completed`: All videos transcribed
- `failed`: An error occurred

**Errors:**
- `422`: Invalid URL or parameters

### GET /jobs/{job_id}

Get the status of a transcription job.

**Authentication:** Required

**Path Parameters:**
- `job_id` (UUID): Job identifier

**Response 200:**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "kind": "single",
  "state": "completed",
  "error": null,
  "created_at": "2025-10-25T10:30:00Z",
  "updated_at": "2025-10-25T10:35:00Z"
}
```

**Errors:**
- `404`: Job not found

---

## Videos

Access video information and transcripts.

### GET /videos

List all videos with pagination.

**Authentication:** Required

**Query Parameters:**
- `limit` (integer, optional): Max results (1-100, default: 50)
- `offset` (integer, optional): Pagination offset (default: 0)

**Response 200:**
```json
[
  {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "youtube_id": "dQw4w9WgXcQ",
    "title": "Example Video",
    "duration_seconds": 212
  }
]
```

### GET /videos/{video_id}

Get information about a specific video.

**Authentication:** Required

**Path Parameters:**
- `video_id` (UUID): Video identifier

**Response 200:**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "youtube_id": "dQw4w9WgXcQ",
  "title": "Example Video",
  "duration_seconds": 212
}
```

**Errors:**
- `404`: Video not found

### GET /videos/{video_id}/transcript

Get Whisper-generated transcript for a video.

**Authentication:** Required

**Path Parameters:**
- `video_id` (UUID): Video identifier

**Response 200:**
```json
{
  "video_id": "123e4567-e89b-12d3-a456-426614174000",
  "segments": [
    {
      "start_ms": 1000,
      "end_ms": 3500,
      "text": "Hello and welcome to this video",
      "speaker_label": "Speaker 1"
    }
  ]
}
```

**Errors:**
- `404`: Video not found
- `503`: Transcript not ready (still processing)

### GET /videos/{video_id}/youtube-transcript

Get YouTube's native closed captions.

**Authentication:** Required

**Path Parameters:**
- `video_id` (UUID): Video identifier

**Response 200:**
```json
{
  "video_id": "123e4567-e89b-12d3-a456-426614174000",
  "language": "en",
  "kind": "asr",
  "full_text": "Full transcript text...",
  "segments": [
    {
      "start_ms": 1000,
      "end_ms": 3500,
      "text": "Hello and welcome"
    }
  ]
}
```

**Errors:**
- `404`: Video not found
- `503`: YouTube captions not available

---

## Search

Full-text search across transcripts.

### GET /search

Search transcripts with filtering and pagination.

**Authentication:** Required

**Query Parameters:**
- `q` (string, required): Search query (1-500 chars)
- `source` (string, optional): `"native"` or `"youtube"` (default: `"native"`)
- `video_id` (UUID, optional): Filter to specific video
- `limit` (integer, optional): Max results (1-200, default: 50)
- `offset` (integer, optional): Pagination offset (default: 0)

**Response 200:**
```json
{
  "total": 42,
  "hits": [
    {
      "id": 12345,
      "video_id": "123e4567-e89b-12d3-a456-426614174000",
      "start_ms": 45000,
      "end_ms": 48500,
      "snippet": "This is an example of <em>search term</em> in context"
    }
  ]
}
```

**Errors:**
- `400`: Empty query or invalid parameters
- `429`: Rate limit exceeded (free plan)
- `503`: Search backend unavailable

**Rate Limits:**
- Free plan: 100 searches per day
- Pro plan: Unlimited

---

## Exports

Export transcripts in various formats.

### GET /videos/{video_id}/transcript.srt

Export Whisper transcript as SubRip subtitle file.

**Authentication:** Required  
**Format:** SRT

**Response 200:** Text file download

**Errors:**
- `401`: Authentication required
- `402`: Export quota exceeded (free plan)
- `503`: Transcript not ready

### GET /videos/{video_id}/transcript.vtt

Export Whisper transcript as WebVTT subtitle file.

**Authentication:** Required  
**Format:** VTT

**Response 200:** Text file download

### GET /videos/{video_id}/transcript.json

Export Whisper transcript as JSON.

**Authentication:** Required  
**Format:** JSON

**Response 200:**
```json
[
  {
    "start_ms": 1000,
    "end_ms": 3500,
    "text": "Hello world",
    "speaker_label": "Speaker 1"
  }
]
```

### GET /videos/{video_id}/transcript.pdf

Export Whisper transcript as formatted PDF document.

**Authentication:** Required  
**Format:** PDF

**Response 200:** PDF file download

**Features:**
- Timestamps for each segment
- Speaker labels
- Video metadata (title, duration)
- Page numbers

### GET /videos/{video_id}/youtube-transcript.srt

Export YouTube captions as SRT.

**Authentication:** Required

### GET /videos/{video_id}/youtube-transcript.vtt

Export YouTube captions as VTT.

**Authentication:** Required

### GET /videos/{video_id}/youtube-transcript.json

Export YouTube captions as JSON.

**Authentication:** Required

**Rate Limits:**
- Free plan: Limited exports per day
- Pro plan: Unlimited

---

## Authentication

OAuth 2.0 authentication and session management.

### GET /auth/me

Get current authenticated user information.

**Authentication:** Optional

**Response 200 (authenticated):**
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

**Response 200 (not authenticated):**
```json
{
  "user": null
}
```

### GET /auth/login/google

Initiate Google OAuth login flow.

**Authentication:** Not required

**Response:** Redirect to Google OAuth consent screen

### GET /auth/callback/google

OAuth callback endpoint (called by Google).

**Authentication:** OAuth code in query params

**Response:** Redirect to frontend with session cookie set

### GET /auth/login/twitch

Initiate Twitch OAuth login flow.

**Authentication:** Not required

**Response:** Redirect to Twitch OAuth consent screen

### GET /auth/callback/twitch

OAuth callback endpoint (called by Twitch).

**Authentication:** OAuth code in query params

**Response:** Redirect to frontend with session cookie set

### POST /auth/logout

Logout and invalidate session.

**Authentication:** Required

**Response 200:**
```json
{
  "ok": true
}
```

---

## Billing

Stripe subscription management (Pro plan).

### POST /billing/checkout-session

Create Stripe checkout session for Pro subscription.

**Authentication:** Required

**Request Body:**
```json
{
  "period": "monthly"
}
```

**Parameters:**
- `period` (string, optional): `"monthly"` or `"yearly"` (default: `"monthly"`)

**Response 200:**
```json
{
  "id": "cs_test_123",
  "url": "https://checkout.stripe.com/pay/cs_test_123"
}
```

**Errors:**
- `401`: Authentication required
- `503`: Stripe not configured

### GET /billing/portal

Get Stripe customer portal URL for managing subscription.

**Authentication:** Required

**Response 200:**
```json
{
  "url": "https://billing.stripe.com/session/123"
}
```

**Errors:**
- `400`: No Stripe customer account
- `401`: Authentication required
- `503`: Stripe not configured

### POST /stripe/webhook

Stripe webhook endpoint for subscription events.

**Authentication:** Stripe webhook signature

**Request Body:** Stripe event payload

**Response 200:**
```json
{
  "received": true
}
```

**Errors:**
- `400`: Invalid webhook signature
- `503`: Stripe not configured

---

## Favorites

Manage favorite transcript segments.

### GET /users/me/favorites

List user's favorite segments.

**Authentication:** Required

**Query Parameters:**
- `video_id` (UUID, optional): Filter by video

**Response 200:**
```json
{
  "items": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "video_id": "987e6543-e21b-34c5-b678-426614174999",
      "start_ms": 10000,
      "end_ms": 15000,
      "text": "Favorite quote",
      "created_at": "2025-10-25T10:30:00Z"
    }
  ]
}
```

### POST /users/me/favorites

Add a favorite segment.

**Authentication:** Required

**Request Body:**
```json
{
  "video_id": "987e6543-e21b-34c5-b678-426614174999",
  "start_ms": 10000,
  "end_ms": 15000,
  "text": "Favorite quote"
}
```

**Response 200:**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000"
}
```

**Errors:**
- `400`: Missing required fields
- `401`: Authentication required

### DELETE /users/me/favorites/{favorite_id}

Delete a favorite segment.

**Authentication:** Required

**Path Parameters:**
- `favorite_id` (UUID): Favorite identifier

**Response 200:**
```json
{
  "ok": true
}
```

---

## Events

Client-side event tracking for analytics.

### POST /events

Track a single event.

**Authentication:** Optional (associates with user if authenticated)

**Request Body:**
```json
{
  "type": "video_view",
  "payload": {
    "video_id": "123e4567-e89b-12d3-a456-426614174000"
  }
}
```

**Response 200:**
```json
{
  "ok": true
}
```

### POST /events/batch

Track multiple events in one request.

**Authentication:** Optional

**Request Body:**
```json
{
  "events": [
    {
      "type": "page_view",
      "payload": {"page": "/home"}
    },
    {
      "type": "search",
      "payload": {"query": "example"}
    }
  ]
}
```

**Response 200:**
```json
{
  "ok": true,
  "count": 2
}
```

---

## Admin

Administrative endpoints (admin access required).

### GET /admin/events

List tracked events with filtering.

**Authentication:** Admin required

**Query Parameters:**
- `type` (string, optional): Filter by event type
- `user_email` (string, optional): Filter by user email
- `start` (string, optional): Filter after timestamp
- `end` (string, optional): Filter before timestamp
- `limit` (integer, optional): Max results (default: 100)
- `offset` (integer, optional): Pagination offset (default: 0)

**Response 200:**
```json
{
  "items": [...]
}
```

**Errors:**
- `403`: Admin access required

### GET /admin/events.csv

Export events as CSV.

**Authentication:** Admin required

**Query Parameters:** Same as `/admin/events`

**Response 200:** CSV file download

### GET /admin/events/summary

Get event statistics.

**Authentication:** Admin required

**Query Parameters:**
- `start` (string, optional): Filter after timestamp
- `end` (string, optional): Filter before timestamp

**Response 200:**
```json
{
  "by_type": [
    {"type": "search", "count": 150}
  ],
  "by_day": [
    {"day": "2025-10-25", "count": 42}
  ]
}
```

### POST /admin/users/{user_id}/plan

Set a user's subscription plan.

**Authentication:** Admin required

**Path Parameters:**
- `user_id` (UUID): User identifier

**Request Body:**
```json
{
  "plan": "pro"
}
```

**Parameters:**
- `plan` (string): `"free"` or `"pro"`

**Response 200:**
```json
{
  "ok": true,
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "plan": "pro"
}
```

**Errors:**
- `400`: Invalid plan value
- `403`: Admin access required

---

## Error Responses

All errors follow this format:

```json
{
  "error": "error_code",
  "message": "Human-readable message",
  "details": {}
}
```

### Common HTTP Status Codes

- `200`: Success
- `400`: Bad Request - Invalid parameters
- `401`: Unauthorized - Authentication required
- `402`: Payment Required - Quota exceeded
- `403`: Forbidden - Insufficient permissions
- `404`: Not Found - Resource doesn't exist
- `422`: Unprocessable Entity - Validation error
- `429`: Too Many Requests - Rate limit exceeded
- `500`: Internal Server Error - Server error
- `503`: Service Unavailable - Service/resource not ready

---

## Related Documentation

- [Getting Started](getting-started.md) - Quick start guide
- [Authentication](authentication.md) - OAuth setup and usage
- [Webhooks](webhooks.md) - Stripe webhook integration
- [Examples](examples.md) - Code examples in multiple languages
