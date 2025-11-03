# Transcript Create Python Client

[![PyPI version](https://badge.fury.io/py/transcript-create-client.svg)](https://badge.fury.io/py/transcript-create-client)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Official Python client library for the [Transcript Create API](https://github.com/subculture-collective/transcript-create). Create searchable, exportable transcripts from YouTube videos with Whisper transcription and optional speaker diarization.

## Features

- ✨ **Async/await support** - Built with `httpx` for modern async Python
- 🔄 **Automatic retries** - Exponential backoff with configurable retry logic
- 🚦 **Rate limiting** - Client-side rate limiting with adaptive adjustment
- 📝 **Type hints** - Full type annotations with Pydantic models
- 🎯 **Custom exceptions** - Clear error handling with specific exception types
- ⏱️ **Job polling** - Built-in support for waiting on job completion
- 📤 **Multiple export formats** - SRT, VTT, PDF, and JSON

## Installation

```bash
pip install transcript-create-client
```

For development:

```bash
pip install transcript-create-client[dev]
```

## Quick Start

```python
import asyncio
from transcript_create_client import TranscriptClient

async def main():
    async with TranscriptClient(base_url="http://localhost:8000") as client:
        # Create a transcription job
        job = await client.create_job(
            url="https://youtube.com/watch?v=dQw4w9WgXcQ",
            kind="single"
        )
        print(f"Created job: {job.id}")

        # Wait for completion
        completed_job = await client.wait_for_completion(job.id, timeout=3600)
        print(f"Job completed: {completed_job.state}")

        # Get the transcript
        transcript = await client.get_transcript(completed_job.id)
        for segment in transcript.segments:
            print(f"[{segment.start_ms}ms] {segment.text}")

asyncio.run(main())
```

## Usage Examples

### Creating Jobs

```python
# Single video
job = await client.create_job(
    url="https://youtube.com/watch?v=VIDEO_ID",
    kind="single"
)

# Entire channel
job = await client.create_job(
    url="https://youtube.com/@channel",
    kind="channel"
)
```

### Checking Job Status

```python
# Get current status
job = await client.get_job(job_id)
print(f"State: {job.state}")

# Wait for completion with polling
job = await client.wait_for_completion(
    job_id,
    timeout=3600,  # Maximum wait time in seconds
    poll_interval=5.0  # Check every 5 seconds
)
```

### Getting Transcripts

```python
# Get raw Whisper transcript (default)
transcript = await client.get_transcript(video_id)
for segment in transcript.segments:
    speaker = segment.speaker_label or "Unknown"
    print(f"[{speaker}] {segment.text}")

# Get cleaned transcript with filler removal and punctuation
cleaned = await client.get_transcript(video_id, mode="cleaned")
for segment in cleaned.segments:
    print(f"Raw: {segment.text_raw}")
    print(f"Cleaned: {segment.text_cleaned}")
    print(f"Stats: {cleaned.stats}")

# Get fully formatted transcript
formatted = await client.get_transcript(video_id, mode="formatted")
print(formatted.text)  # Formatted text with speaker labels and paragraphs
print(f"Format: {formatted.format}")  # inline/dialogue/structured

# Get YouTube captions
yt_transcript = await client.get_youtube_transcript(video_id)
print(yt_transcript.full_text)
```

**Transcript Modes:**

The `get_transcript` method supports three modes:

1. **`raw`** (default): Raw Whisper segments without processing
   - Returns: `TranscriptResponse` with list of `Segment` objects
   - Use when you need unmodified transcription output

2. **`cleaned`**: Segments with cleanup applied
   - Returns: `CleanedTranscriptResponse` with list of `CleanedSegment` objects
   - Features: Filler removal, punctuation, normalization
   - Each segment includes both `text_raw` and `text_cleaned`
   - Response includes cleanup statistics and configuration

3. **`formatted`**: Fully formatted text output
   - Returns: `FormattedTranscriptResponse` with single `text` field
   - Features: Speaker labels, paragraph structure, sentence segmentation
   - Best for human-readable output or document generation

### Searching

```python
# Search native transcripts
results = await client.search(
    query="machine learning",
    source="native",
    limit=50
)

for hit in results.hits:
    print(f"Video: {hit.video_id}")
    print(f"Time: {hit.start_ms}ms - {hit.end_ms}ms")
    print(f"Snippet: {hit.snippet}")

# Search YouTube captions
results = await client.search(
    query="python",
    source="youtube",
    video_id=specific_video_id  # Optional: limit to specific video
)
```

### Exporting

```python
# Export as SRT
srt_content = await client.export_srt(video_id)
with open("transcript.srt", "wb") as f:
    f.write(srt_content)

# Export as VTT
vtt_content = await client.export_vtt(video_id)

# Export as PDF
pdf_content = await client.export_pdf(video_id)
with open("transcript.pdf", "wb") as f:
    f.write(pdf_content)
```

## Configuration

### Client Options

```python
client = TranscriptClient(
    base_url="https://api.example.com",
    api_key="your-api-key",  # Optional: if authentication required
    timeout=30.0,  # Request timeout in seconds
    max_retries=3,  # Maximum retry attempts
    rate_limit=10.0,  # Max requests per second
    adaptive_rate_limiting=True,  # Adjust rate based on 429 responses
)
```

### Custom Retry Configuration

```python
from transcript_create_client.retry import RetryConfig

retry_config = RetryConfig(
    max_retries=5,
    initial_delay=1.0,
    max_delay=60.0,
    exponential_base=2.0,
    jitter=True,
    retryable_status_codes={408, 429, 500, 502, 503, 504}
)

client = TranscriptClient(
    base_url="https://api.example.com",
    retry_config=retry_config
)
```

## Error Handling

The client provides specific exception types for different error scenarios:

```python
from transcript_create_client import (
    APIError,
    AuthenticationError,
    InvalidAPIKeyError,
    NotFoundError,
    TranscriptNotFoundError,
    ValidationError,
    RateLimitError,
    QuotaExceededError,
    NetworkError,
    TimeoutError,
)

try:
    transcript = await client.get_transcript(video_id)
except TranscriptNotFoundError:
    print("Transcript hasn't been generated yet")
except QuotaExceededError:
    print("API quota exceeded - upgrade your plan")
except RateLimitError as e:
    print(f"Rate limited - retry after {e.retry_after} seconds")
except ValidationError as e:
    print(f"Invalid request: {e.message}")
    print(f"Details: {e.details}")
except APIError as e:
    print(f"API error: {e.message} (status: {e.status_code})")
```

## Advanced Usage

### Manual Resource Management

```python
client = TranscriptClient(base_url="https://api.example.com")

try:
    await client._ensure_client()  # Initialize HTTP client
    job = await client.create_job(url="...", kind="single")
finally:
    await client.close()  # Clean up resources
```

### Batch Processing

```python
async def process_videos(video_urls):
    async with TranscriptClient() as client:
        jobs = []
        
        # Create all jobs
        for url in video_urls:
            job = await client.create_job(url=url)
            jobs.append(job)
        
        # Wait for all completions
        completed = await asyncio.gather(
            *[client.wait_for_completion(job.id) for job in jobs],
            return_exceptions=True
        )
        
        # Process results
        for job, result in zip(jobs, completed):
            if isinstance(result, Exception):
                print(f"Job {job.id} failed: {result}")
            else:
                print(f"Job {job.id} completed")
```

## Development

### Setup

```bash
cd clients/python
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=transcript_create_client --cov-report=html

# Run specific test file
pytest tests/test_client.py -v
```

### Linting

```bash
# Check code
ruff check transcript_create_client tests
black --check transcript_create_client tests
mypy transcript_create_client

# Auto-fix
ruff check --fix transcript_create_client tests
black transcript_create_client tests
```

## API Reference

See the [main API documentation](https://github.com/subculture-collective/transcript-create#api-reference-selected) for complete endpoint details.

### Client Methods

#### Jobs
- `create_job(url, kind)` - Create transcription job
- `get_job(job_id)` - Get job status
- `wait_for_completion(job_id, timeout, poll_interval)` - Wait for job to complete

#### Videos
- `get_video(video_id)` - Get video information
- `get_transcript(video_id, mode='raw')` - Get Whisper transcript
  - `mode='raw'` - Raw segments (default)
  - `mode='cleaned'` - Cleaned segments with stats
  - `mode='formatted'` - Formatted text with speaker labels
- `get_youtube_transcript(video_id)` - Get YouTube captions

#### Search
- `search(query, source, video_id, limit, offset)` - Search transcripts

#### Exports
- `export_srt(video_id, source)` - Export as SRT
- `export_vtt(video_id, source)` - Export as VTT
- `export_pdf(video_id)` - Export as PDF

## Contributing

Contributions are welcome! Please see the [main contributing guide](https://github.com/subculture-collective/transcript-create/blob/main/CONTRIBUTING.md).

## License

Apache License 2.0 - see [LICENSE](https://github.com/subculture-collective/transcript-create/blob/main/LICENSE)

## Support

- 📖 [Documentation](https://github.com/subculture-collective/transcript-create)
- 🐛 [Issue Tracker](https://github.com/subculture-collective/transcript-create/issues)
- 💬 [Discussions](https://github.com/subculture-collective/transcript-create/discussions)

## Related Projects

- [JavaScript/TypeScript SDK](../javascript) - Client for Node.js and browsers
- [Go SDK](../go) - Client for Go applications
