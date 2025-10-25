# API Usage Examples

This guide provides practical code examples for common use cases with the Transcript Create API.

## Table of Contents

- [Authentication Examples](#authentication-examples)
- [Job Management](#job-management)
- [Transcript Access](#transcript-access)
- [Search Examples](#search-examples)
- [Export Examples](#export-examples)
- [Favorites Management](#favorites-management)
- [Subscription Management](#subscription-management)

## Authentication Examples

### JavaScript/Fetch

```javascript
// Initiate Google login
window.location.href = 'https://api.example.com/auth/login/google';

// After redirect back to your app, check auth status
async function getCurrentUser() {
  const response = await fetch('https://api.example.com/auth/me', {
    credentials: 'include', // Important: include cookies
  });
  const data = await response.json();
  return data.user;
}

// Logout
async function logout() {
  const response = await fetch('https://api.example.com/auth/logout', {
    method: 'POST',
    credentials: 'include',
  });
  return response.json();
}
```

### Python/Requests

```python
import requests

# Create session to handle cookies
session = requests.Session()

# Login (in practice, this requires browser OAuth flow)
# After OAuth, your session will have the cookie

# Check authentication
response = session.get('https://api.example.com/auth/me')
user = response.json().get('user')

if user:
    print(f"Logged in as {user['name']}")
else:
    print("Not authenticated")

# Logout
session.post('https://api.example.com/auth/logout')
```

### cURL

```bash
# Login requires browser for OAuth
# After login, export session cookie
export SESSION_TOKEN="your_session_token"

# Check authentication
curl https://api.example.com/auth/me \
  -H "Cookie: tc_session=$SESSION_TOKEN"

# Logout
curl -X POST https://api.example.com/auth/logout \
  -H "Cookie: tc_session=$SESSION_TOKEN"
```

## Job Management

### Create and Monitor a Job

#### JavaScript

```javascript
async function transcribeVideo(videoUrl) {
  // Create job
  const createResponse = await fetch('https://api.example.com/jobs', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify({
      url: videoUrl,
      kind: 'single',
    }),
  });
  
  const job = await createResponse.json();
  console.log(`Job created: ${job.id}`);
  
  // Poll for completion
  while (true) {
    const statusResponse = await fetch(
      `https://api.example.com/jobs/${job.id}`,
      { credentials: 'include' }
    );
    const status = await statusResponse.json();
    
    console.log(`Job state: ${status.state}`);
    
    if (status.state === 'completed') {
      console.log('Job completed successfully!');
      return status;
    } else if (status.state === 'failed') {
      throw new Error(`Job failed: ${status.error}`);
    }
    
    // Wait 10 seconds before checking again
    await new Promise(resolve => setTimeout(resolve, 10000));
  }
}

// Usage
transcribeVideo('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
  .then(() => console.log('Transcription complete'))
  .catch(err => console.error('Error:', err));
```

#### Python

```python
import time
import requests

def transcribe_video(video_url, session):
    # Create job
    response = session.post(
        'https://api.example.com/jobs',
        json={
            'url': video_url,
            'kind': 'single',
        }
    )
    job = response.json()
    job_id = job['id']
    print(f"Job created: {job_id}")
    
    # Poll for completion
    while True:
        response = session.get(f'https://api.example.com/jobs/{job_id}')
        status = response.json()
        
        print(f"Job state: {status['state']}")
        
        if status['state'] == 'completed':
            print("Job completed successfully!")
            return status
        elif status['state'] == 'failed':
            raise Exception(f"Job failed: {status['error']}")
        
        time.sleep(10)  # Wait 10 seconds

# Usage
session = requests.Session()
# Assume session is authenticated
transcribe_video('https://www.youtube.com/watch?v=dQw4w9WgXcQ', session)
```

### Transcribe a Channel

```bash
# Create channel job
curl -X POST https://api.example.com/jobs \
  -H "Content-Type: application/json" \
  -H "Cookie: tc_session=$SESSION_TOKEN" \
  -d '{
    "url": "https://www.youtube.com/@channelname",
    "kind": "channel"
  }'
```

## Transcript Access

### Get Full Transcript

#### TypeScript

```typescript
interface Segment {
  start_ms: number;
  end_ms: number;
  text: string;
  speaker_label: string | null;
}

interface Transcript {
  video_id: string;
  segments: Segment[];
}

async function getTranscript(videoId: string): Promise<Transcript> {
  const response = await fetch(
    `https://api.example.com/videos/${videoId}/transcript`,
    { credentials: 'include' }
  );
  
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }
  
  return response.json();
}

// Format transcript as plain text
function formatTranscript(transcript: Transcript): string {
  return transcript.segments
    .map(seg => {
      const time = formatTime(seg.start_ms);
      const speaker = seg.speaker_label ? `${seg.speaker_label}: ` : '';
      return `[${time}] ${speaker}${seg.text}`;
    })
    .join('\n');
}

function formatTime(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  return `${hours}:${String(minutes % 60).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}
```

### Get YouTube Captions

```python
def get_youtube_captions(video_id, session):
    response = session.get(
        f'https://api.example.com/videos/{video_id}/youtube-transcript'
    )
    
    if response.status_code == 503:
        print("YouTube captions not available")
        return None
    
    response.raise_for_status()
    return response.json()

# Usage
captions = get_youtube_captions('123e4567-e89b-12d3-a456-426614174000', session)
if captions:
    print(f"Language: {captions['language']}")
    print(f"Type: {captions['kind']}")
    print(f"Segments: {len(captions['segments'])}")
```

## Search Examples

### Basic Search

```javascript
async function searchTranscripts(query, options = {}) {
  const params = new URLSearchParams({
    q: query,
    source: options.source || 'native',
    limit: options.limit || 50,
    offset: options.offset || 0,
  });
  
  if (options.videoId) {
    params.set('video_id', options.videoId);
  }
  
  const response = await fetch(
    `https://api.example.com/search?${params}`,
    { credentials: 'include' }
  );
  
  return response.json();
}

// Usage
const results = await searchTranscripts('machine learning', {
  source: 'native',
  limit: 10,
});

console.log(`Found ${results.total} results`);
results.hits.forEach(hit => {
  console.log(`Video ${hit.video_id} at ${hit.start_ms}ms:`);
  console.log(hit.snippet);
});
```

### Paginated Search

```python
def search_all(query, session, page_size=50):
    """Search with automatic pagination."""
    all_hits = []
    offset = 0
    
    while True:
        response = session.get(
            'https://api.example.com/search',
            params={
                'q': query,
                'source': 'native',
                'limit': page_size,
                'offset': offset,
            }
        )
        data = response.json()
        
        hits = data['hits']
        all_hits.extend(hits)
        
        if len(hits) < page_size:
            break  # No more results
        
        offset += page_size
    
    return all_hits

# Usage
all_results = search_all('python programming', session)
print(f"Total results: {len(all_results)}")
```

### Search Within a Video

```bash
# Search within specific video
curl "https://api.example.com/search?q=introduction&video_id=123e4567-e89b-12d3-a456-426614174000" \
  -H "Cookie: tc_session=$SESSION_TOKEN"
```

## Export Examples

### Download as SRT

```javascript
async function downloadSRT(videoId) {
  const response = await fetch(
    `https://api.example.com/videos/${videoId}/transcript.srt`,
    { credentials: 'include' }
  );
  
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  
  const a = document.createElement('a');
  a.href = url;
  a.download = `transcript-${videoId}.srt`;
  a.click();
  
  window.URL.revokeObjectURL(url);
}
```

### Download Multiple Formats

```python
def export_transcript(video_id, formats, session, output_dir='.'):
    """Download transcript in multiple formats."""
    import os
    
    for fmt in formats:
        endpoint = f'https://api.example.com/videos/{video_id}/transcript.{fmt}'
        response = session.get(endpoint)
        
        if response.status_code == 200:
            filename = os.path.join(output_dir, f'transcript-{video_id}.{fmt}')
            with open(filename, 'wb') as f:
                f.write(response.content)
            print(f"Downloaded {filename}")
        else:
            print(f"Failed to download {fmt}: {response.status_code}")

# Usage
export_transcript(
    '123e4567-e89b-12d3-a456-426614174000',
    ['srt', 'vtt', 'json', 'pdf'],
    session,
    output_dir='/tmp/transcripts'
)
```

### Export with Error Handling

```typescript
async function safeExport(videoId: string, format: string): Promise<Blob | null> {
  try {
    const response = await fetch(
      `https://api.example.com/videos/${videoId}/transcript.${format}`,
      { credentials: 'include' }
    );
    
    if (response.status === 401) {
      console.error('Authentication required');
      return null;
    }
    
    if (response.status === 402) {
      console.error('Export quota exceeded - upgrade to Pro');
      return null;
    }
    
    if (response.status === 503) {
      console.error('Transcript not ready yet');
      return null;
    }
    
    return await response.blob();
  } catch (error) {
    console.error('Export failed:', error);
    return null;
  }
}
```

## Favorites Management

### Save and List Favorites

```javascript
// Save a favorite segment
async function saveFavorite(videoId, startMs, endMs, text) {
  const response = await fetch('https://api.example.com/users/me/favorites', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      video_id: videoId,
      start_ms: startMs,
      end_ms: endMs,
      text: text,
    }),
  });
  
  return response.json();
}

// List all favorites
async function listFavorites(videoId = null) {
  const url = new URL('https://api.example.com/users/me/favorites');
  if (videoId) {
    url.searchParams.set('video_id', videoId);
  }
  
  const response = await fetch(url, { credentials: 'include' });
  const data = await response.json();
  return data.items;
}

// Delete a favorite
async function deleteFavorite(favoriteId) {
  await fetch(`https://api.example.com/users/me/favorites/${favoriteId}`, {
    method: 'DELETE',
    credentials: 'include',
  });
}
```

## Subscription Management

### Create Checkout Session

```javascript
async function upgradeToPro(period = 'monthly') {
  const response = await fetch('https://api.example.com/billing/checkout-session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ period }),
  });
  
  const data = await response.json();
  
  // Redirect to Stripe checkout
  window.location.href = data.url;
}
```

### Access Billing Portal

```javascript
async function manageBilling() {
  const response = await fetch('https://api.example.com/billing/portal', {
    credentials: 'include',
  });
  
  const data = await response.json();
  
  // Redirect to Stripe portal
  window.location.href = data.url;
}
```

## Error Handling

### Comprehensive Error Handler

```typescript
interface ApiError {
  error: string;
  message: string;
  details?: Record<string, any>;
}

async function apiRequest<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(url, {
    ...options,
    credentials: 'include',
  });
  
  if (!response.ok) {
    const error: ApiError = await response.json();
    
    switch (response.status) {
      case 400:
        throw new Error(`Validation error: ${error.message}`);
      case 401:
        throw new Error('Authentication required');
      case 403:
        throw new Error('Access denied');
      case 404:
        throw new Error('Resource not found');
      case 429:
        throw new Error(`Rate limit exceeded: ${error.message}`);
      case 503:
        throw new Error(`Service unavailable: ${error.message}`);
      default:
        throw new Error(`API error: ${error.message}`);
    }
  }
  
  return response.json();
}
```

## Rate Limit Handling

```python
import time

def api_request_with_retry(url, session, max_retries=3):
    """Make API request with automatic retry on rate limits."""
    for attempt in range(max_retries):
        response = session.get(url)
        
        if response.status_code == 429:
            # Rate limited
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                raise Exception("Max retries exceeded")
        
        response.raise_for_status()
        return response.json()
    
    raise Exception("Request failed after retries")
```

## Related Documentation

- [Getting Started](getting-started.md) - API basics
- [API Reference](api-reference.md) - Complete endpoint documentation
- [Authentication](authentication.md) - OAuth and sessions
- [Webhooks](webhooks.md) - Stripe webhook handling
