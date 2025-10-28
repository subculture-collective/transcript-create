# Transcript Create API Client SDKs

Official client libraries for the Transcript Create API. Choose the SDK that matches your preferred programming language.

## Available SDKs

### Python SDK
[![PyPI](https://img.shields.io/pypi/v/transcript-create-client.svg)](https://pypi.org/project/transcript-create-client/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Full-featured async Python client with Pydantic models and comprehensive error handling.

- **Installation**: `pip install transcript-create-client`
- **Documentation**: [clients/python/README.md](python/README.md)
- **Key Features**:
  - Async/await support with httpx
  - Full type hints with Pydantic
  - Automatic retries with exponential backoff
  - Client-side and adaptive rate limiting
  - Custom exception classes
  - Job polling support
  - 85% test coverage

**Quick Example**:
```python
from transcript_create_client import TranscriptClient

async with TranscriptClient(base_url="http://localhost:8000") as client:
    job = await client.create_job("https://youtube.com/watch?v=...", "single")
    completed = await client.wait_for_completion(job.id)
    transcript = await client.get_transcript(job.id)
```

---

### JavaScript/TypeScript SDK
[![npm](https://img.shields.io/npm/v/@transcript-create/sdk.svg)](https://www.npmjs.com/package/@transcript-create/sdk)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-blue.svg)](https://www.typescriptlang.org/)

Universal TypeScript/JavaScript client that works in Node.js and browsers.

- **Installation**: `npm install @transcript-create/sdk`
- **Documentation**: [clients/javascript/README.md](javascript/README.md)
- **Key Features**:
  - Full TypeScript support with complete type definitions
  - Promise-based async API
  - Automatic retries with exponential backoff
  - Client-side and adaptive rate limiting
  - Custom error classes
  - Tree-shakeable ESM and CJS builds
  - Browser and Node.js support

**Quick Example**:
```typescript
import { TranscriptClient } from '@transcript-create/sdk';

const client = new TranscriptClient({ baseUrl: 'http://localhost:8000' });
const job = await client.createJob('https://youtube.com/watch?v=...', 'single');
const completed = await client.waitForCompletion(job.id);
const transcript = await client.getTranscript(job.id);
```

---

## Feature Comparison

| Feature | Python | JavaScript/TypeScript |
|---------|--------|----------------------|
| Async/await | ✅ | ✅ |
| Type safety | ✅ (Pydantic) | ✅ (TypeScript) |
| Retry logic | ✅ | ✅ |
| Rate limiting | ✅ Adaptive | ✅ Adaptive |
| Error handling | ✅ Custom exceptions | ✅ Custom error classes |
| Job polling | ✅ | ✅ |
| Browser support | ❌ | ✅ |
| Unit tests | ✅ 21 tests, 85% coverage | ✅ 13 tests |

## Common Use Cases

### Creating and Monitoring Jobs

All SDKs support creating transcription jobs and waiting for completion:

**Python**:
```python
job = await client.create_job(url, kind="single")
completed = await client.wait_for_completion(job.id, timeout=3600)
```

**JavaScript**:
```typescript
const job = await client.createJob(url, 'single');
const completed = await client.waitForCompletion(job.id, { timeout: 3600000 });
```

### Searching Transcripts

**Python**:
```python
results = await client.search(
    query="machine learning",
    source="native",
    limit=50
)
```

**JavaScript**:
```typescript
const results = await client.search({
  query: 'machine learning',
  source: 'native',
  limit: 50
});
```

### Exporting Transcripts

**Python**:
```python
srt = await client.export_srt(video_id)
vtt = await client.export_vtt(video_id)
pdf = await client.export_pdf(video_id)
```

**JavaScript**:
```typescript
const srtBlob = await client.exportSRT(videoId);
const vttBlob = await client.exportVTT(videoId);
const pdfBlob = await client.exportPDF(videoId);
```

## Configuration

Both SDKs support similar configuration options:

| Option | Description | Python | JavaScript |
|--------|-------------|--------|------------|
| Base URL | API endpoint | `base_url` | `baseUrl` |
| API Key | Authentication | `api_key` | `apiKey` |
| Timeout | Request timeout | `timeout` | `timeout` |
| Max Retries | Retry attempts | `max_retries` | `maxRetries` |
| Rate Limit | Requests/second | `rate_limit` | `rateLimit` |

## Error Handling

Both SDKs provide similar error hierarchies:

- `APIError` - Base error class
- `AuthenticationError` - Auth failures
- `InvalidAPIKeyError` - Invalid API key
- `NotFoundError` - Resource not found
- `TranscriptNotFoundError` - Transcript not found
- `ValidationError` - Request validation failed
- `RateLimitError` - Rate limit exceeded
- `QuotaExceededError` - API quota exceeded
- `ServerError` - Server errors (5xx)
- `NetworkError` - Network failures
- `TimeoutError` - Request timeout

## Contributing

Contributions to the SDKs are welcome! Please see:

- [Python SDK Development](python/README.md#development)
- [JavaScript SDK Development](javascript/README.md#development)
- [Main Contributing Guide](../CONTRIBUTING.md)

## Publishing

### Python SDK

```bash
# Tag and push
git tag python-sdk-v0.1.0
git push origin python-sdk-v0.1.0

# GitHub Actions will automatically publish to PyPI
```

### JavaScript SDK

```bash
# Tag and push
git tag javascript-sdk-v0.1.0
git push origin javascript-sdk-v0.1.0

# GitHub Actions will automatically publish to npm
```

## Support

- 📖 [API Documentation](../README.md#api-reference)
- 🐛 [Issue Tracker](https://github.com/subculture-collective/transcript-create/issues)
- 💬 [Discussions](https://github.com/subculture-collective/transcript-create/discussions)

## License

Apache License 2.0 - see [LICENSE](../LICENSE)
