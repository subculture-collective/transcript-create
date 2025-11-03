# Transcript Create TypeScript/JavaScript SDK

[![npm version](https://badge.fury.io/js/%40transcript-create%2Fsdk.svg)](https://badge.fury.io/js/%40transcript-create%2Fsdk)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-blue.svg)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Official TypeScript/JavaScript client library for the [Transcript Create API](https://github.com/subculture-collective/transcript-create). Create searchable, exportable transcripts from YouTube videos with Whisper transcription and optional speaker diarization.

## Features

- ✨ **Full TypeScript support** - Complete type definitions for all API methods
- 🔄 **Automatic retries** - Exponential backoff with configurable retry logic
- 🚦 **Rate limiting** - Client-side rate limiting with adaptive adjustment
- 🌐 **Universal** - Works in Node.js and browsers
- 📦 **Tree-shakeable** - ESM and CJS builds with optimized bundle size
- ⏱️ **Job polling** - Built-in support for waiting on job completion
- 📤 **Multiple export formats** - SRT, VTT, PDF, and JSON

## Installation

```bash
npm install @transcript-create/sdk
```

Or with yarn:

```bash
yarn add @transcript-create/sdk
```

Or with pnpm:

```bash
pnpm add @transcript-create/sdk
```

## Quick Start

```typescript
import { TranscriptClient } from '@transcript-create/sdk';

const client = new TranscriptClient({
  baseUrl: 'http://localhost:8000',
});

// Create a transcription job
const job = await client.createJob(
  'https://youtube.com/watch?v=dQw4w9WgXcQ',
  'single'
);
console.log(`Created job: ${job.id}`);

// Wait for completion
const completedJob = await client.waitForCompletion(job.id, {
  timeout: 3600000, // 1 hour
});
console.log(`Job completed: ${completedJob.state}`);

// Get the transcript
const transcript = await client.getTranscript(job.id);
for (const segment of transcript.segments) {
  console.log(`[${segment.start_ms}ms] ${segment.text}`);
}
```

## Usage Examples

### Creating Jobs

```typescript
// Single video
const job = await client.createJob(
  'https://youtube.com/watch?v=VIDEO_ID',
  'single'
);

// Entire channel
const job = await client.createJob(
  'https://youtube.com/@channel',
  'channel'
);
```

### Checking Job Status

```typescript
// Get current status
const job = await client.getJob(jobId);
console.log(`State: ${job.state}`);

// Wait for completion with polling
const job = await client.waitForCompletion(jobId, {
  timeout: 3600000,  // Maximum wait time in milliseconds
  pollInterval: 5000  // Check every 5 seconds
});
```

### Getting Transcripts

```typescript
// Get raw Whisper transcript (default)
const transcript = await client.getTranscript(videoId);
for (const segment of transcript.segments) {
  const speaker = segment.speaker_label || 'Unknown';
  console.log(`[${speaker}] ${segment.text}`);
}

// Get cleaned transcript with filler removal and punctuation
const cleaned = await client.getTranscript(videoId, 'cleaned');
for (const segment of cleaned.segments) {
  console.log(`Raw: ${segment.text_raw}`);
  console.log(`Cleaned: ${segment.text_cleaned}`);
}
console.log(`Stats: ${JSON.stringify(cleaned.stats)}`);

// Get fully formatted transcript
const formatted = await client.getTranscript(videoId, 'formatted');
console.log(formatted.text);  // Formatted text with speaker labels
console.log(`Format: ${formatted.format}`);  // inline/dialogue/structured

// Get YouTube captions
const ytTranscript = await client.getYouTubeTranscript(videoId);
console.log(ytTranscript.full_text);
```

**Transcript Modes:**

The `getTranscript` method supports three modes:

1. **`'raw'`** (default): Raw Whisper segments without processing
   - Returns: `TranscriptResponse` with array of `Segment` objects
   - Use when you need unmodified transcription output

2. **`'cleaned'`**: Segments with cleanup applied
   - Returns: `CleanedTranscriptResponse` with array of `CleanedSegment` objects
   - Features: Filler removal, punctuation, normalization
   - Each segment includes both `text_raw` and `text_cleaned`
   - Response includes cleanup statistics and configuration

3. **`'formatted'`**: Fully formatted text output
   - Returns: `FormattedTranscriptResponse` with single `text` field
   - Features: Speaker labels, paragraph structure, sentence segmentation
   - Best for human-readable output or document generation

### Searching

```typescript
// Search native transcripts
const results = await client.search({
  query: 'machine learning',
  source: 'native',
  limit: 50
});

for (const hit of results.hits) {
  console.log(`Video: ${hit.video_id}`);
  console.log(`Time: ${hit.start_ms}ms - ${hit.end_ms}ms`);
  console.log(`Snippet: ${hit.snippet}`);
}

// Search YouTube captions
const results = await client.search({
  query: 'python',
  source: 'youtube',
  video_id: specificVideoId // Optional: limit to specific video
});
```

### Exporting

```typescript
// Export as SRT
const srtBlob = await client.exportSRT(videoId);
// In Node.js:
const srtBuffer = Buffer.from(await srtBlob.arrayBuffer());
await fs.writeFile('transcript.srt', srtBuffer);

// In browser:
const url = URL.createObjectURL(srtBlob);
const a = document.createElement('a');
a.href = url;
a.download = 'transcript.srt';
a.click();

// Export as VTT
const vttBlob = await client.exportVTT(videoId);

// Export as PDF
const pdfBlob = await client.exportPDF(videoId);
```

## Configuration

### Client Options

```typescript
const client = new TranscriptClient({
  baseUrl: 'https://api.example.com',
  apiKey: 'your-api-key',  // Optional: if authentication required
  timeout: 30000,  // Request timeout in milliseconds
  maxRetries: 3,  // Maximum retry attempts
  retryDelay: 1000,  // Initial retry delay in milliseconds
  rateLimit: 10,  // Max requests per second
});
```

## Error Handling

The SDK provides specific error classes for different scenarios:

```typescript
import {
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
} from '@transcript-create/sdk';

try {
  const transcript = await client.getTranscript(videoId);
} catch (error) {
  if (error instanceof TranscriptNotFoundError) {
    console.log("Transcript hasn't been generated yet");
  } else if (error instanceof QuotaExceededError) {
    console.log('API quota exceeded - upgrade your plan');
  } else if (error instanceof RateLimitError) {
    console.log(`Rate limited - retry after ${error.retryAfter} seconds`);
  } else if (error instanceof ValidationError) {
    console.log(`Invalid request: ${error.message}`);
    console.log(`Details:`, error.details);
  } else if (error instanceof APIError) {
    console.log(`API error: ${error.message} (status: ${error.statusCode})`);
  } else {
    console.error('Unexpected error:', error);
  }
}
```

## Advanced Usage

### Batch Processing

```typescript
async function processVideos(videoUrls: string[]) {
  const client = new TranscriptClient();
  
  // Create all jobs
  const jobs = await Promise.all(
    videoUrls.map(url => client.createJob(url))
  );
  
  // Wait for all completions
  const completed = await Promise.allSettled(
    jobs.map(job => client.waitForCompletion(job.id))
  );
  
  // Process results
  for (let i = 0; i < completed.length; i++) {
    const result = completed[i];
    const job = jobs[i];
    
    if (result.status === 'fulfilled') {
      console.log(`Job ${job.id} completed`);
    } else {
      console.log(`Job ${job.id} failed:`, result.reason);
    }
  }
}
```

### Custom Retry Configuration

```typescript
import { TranscriptClient, DEFAULT_RETRY_CONFIG } from '@transcript-create/sdk';

const client = new TranscriptClient({
  maxRetries: 5,
  retryDelay: 2000,
});
```

## Browser Usage

The SDK works in modern browsers with ES modules:

```html
<script type="module">
  import { TranscriptClient } from 'https://cdn.skypack.dev/@transcript-create/sdk';
  
  const client = new TranscriptClient({
    baseUrl: 'https://api.example.com'
  });
  
  // Use the client...
</script>
```

## Development

### Setup

```bash
cd clients/javascript
npm install
```

### Building

```bash
# Build for production
npm run build

# Build and watch for changes
npm run dev
```

### Running Tests

```bash
# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Watch mode
npm run test:watch
```

### Linting

```bash
# Check code
npm run lint

# Auto-fix
npm run lint:fix

# Check formatting
npm run format:check

# Format code
npm run format
```

## API Reference

See the [main API documentation](https://github.com/subculture-collective/transcript-create#api-reference-selected) for complete endpoint details.

### Client Methods

#### Jobs
- `createJob(url, kind)` - Create transcription job
- `getJob(jobId)` - Get job status
- `waitForCompletion(jobId, options)` - Wait for job to complete

#### Videos
- `getVideo(videoId)` - Get video information
- `getTranscript(videoId, mode?)` - Get Whisper transcript
  - `mode: 'raw'` - Raw segments (default)
  - `mode: 'cleaned'` - Cleaned segments with stats
  - `mode: 'formatted'` - Formatted text with speaker labels
- `getYouTubeTranscript(videoId)` - Get YouTube captions

#### Search
- `search(options)` - Search transcripts

#### Exports
- `exportSRT(videoId, source)` - Export as SRT
- `exportVTT(videoId, source)` - Export as VTT
- `exportPDF(videoId)` - Export as PDF

## TypeScript

This library is written in TypeScript and includes full type definitions. You get autocomplete and type checking out of the box!

```typescript
import type {
  Job,
  TranscriptResponse,
  CleanedTranscriptResponse,
  FormattedTranscriptResponse,
  SearchResponse
} from '@transcript-create/sdk';

const job: Job = await client.createJob(url, 'single');
const transcript: TranscriptResponse = await client.getTranscript(videoId);
const cleaned: CleanedTranscriptResponse = await client.getTranscript(videoId, 'cleaned');
const formatted: FormattedTranscriptResponse = await client.getTranscript(videoId, 'formatted');
const results: SearchResponse = await client.search({ query: 'test' });
```

## Contributing

Contributions are welcome! Please see the [main contributing guide](https://github.com/subculture-collective/transcript-create/blob/main/CONTRIBUTING.md).

## License

Apache License 2.0 - see [LICENSE](https://github.com/subculture-collective/transcript-create/blob/main/LICENSE)

## Support

- 📖 [Documentation](https://github.com/subculture-collective/transcript-create)
- 🐛 [Issue Tracker](https://github.com/subculture-collective/transcript-create/issues)
- 💬 [Discussions](https://github.com/subculture-collective/transcript-create/discussions)

## Related Projects

- [Python SDK](../python) - Client for Python applications
- [Go SDK](../go) - Client for Go applications
