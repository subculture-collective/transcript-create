/**
 * Type definitions for Transcript Create API
 */

/**
 * Job types
 */
export type JobKind = 'single' | 'channel';
export type JobState = 'pending' | 'expanded' | 'completed' | 'failed';

/**
 * Search sources
 */
export type SearchSource = 'native' | 'youtube';

/**
 * Export formats
 */
export type ExportFormat = 'srt' | 'vtt' | 'pdf' | 'json';

/**
 * Request to create a new job
 */
export interface JobCreateRequest {
  /** YouTube video or channel URL */
  url: string;
  /** Job type */
  kind?: JobKind;
}

/**
 * Job information
 */
export interface Job {
  /** Job ID */
  id: string;
  /** Job type */
  kind: JobKind;
  /** Current state */
  state: JobState;
  /** Error message if failed */
  error: string | null;
  /** Creation timestamp */
  created_at: string;
  /** Last update timestamp */
  updated_at: string;
}

/**
 * Video information
 */
export interface VideoInfo {
  /** Video ID */
  id: string;
  /** YouTube video ID */
  youtube_id: string;
  /** Video title */
  title: string | null;
  /** Duration in seconds */
  duration_seconds: number | null;
}

/**
 * Transcript segment
 */
export interface Segment {
  /** Start time in milliseconds */
  start_ms: number;
  /** End time in milliseconds */
  end_ms: number;
  /** Transcript text */
  text: string;
  /** Speaker label from diarization */
  speaker_label?: string | null;
}

/**
 * Complete transcript response
 */
export interface TranscriptResponse {
  /** Video ID */
  video_id: string;
  /** Transcript segments */
  segments: Segment[];
}

/**
 * YouTube caption segment
 */
export interface YouTubeSegment {
  /** Start time in milliseconds */
  start_ms: number;
  /** End time in milliseconds */
  end_ms: number;
  /** Caption text */
  text: string;
}

/**
 * YouTube captions response
 */
export interface YouTubeTranscriptResponse {
  /** Video ID */
  video_id: string;
  /** Language code */
  language: string | null;
  /** Caption type */
  kind: string | null;
  /** Full text concatenated */
  full_text: string | null;
  /** Caption segments */
  segments: YouTubeSegment[];
}

/**
 * Search hit result
 */
export interface SearchHit {
  /** Segment ID */
  id: number;
  /** Video ID */
  video_id: string;
  /** Start time in milliseconds */
  start_ms: number;
  /** End time in milliseconds */
  end_ms: number;
  /** Text snippet with highlights */
  snippet: string;
}

/**
 * Search response
 */
export interface SearchResponse {
  /** Total number of results (OpenSearch only) */
  total?: number | null;
  /** Search results */
  hits: SearchHit[];
  /** Query execution time in milliseconds */
  query_time_ms?: number | null;
}

/**
 * Search request options
 */
export interface SearchOptions {
  /** Search query */
  query: string;
  /** Search source */
  source?: SearchSource;
  /** Video ID to limit search */
  video_id?: string;
  /** Maximum results */
  limit?: number;
  /** Result offset for pagination */
  offset?: number;
}

/**
 * API error response
 */
export interface ErrorResponse {
  /** Error code */
  error: string;
  /** Human-readable message */
  message: string;
  /** Additional error details */
  details?: Record<string, any>;
}

/**
 * Client configuration options
 */
export interface ClientOptions {
  /** Base URL of the API */
  baseUrl?: string;
  /** API key for authentication */
  apiKey?: string;
  /** Request timeout in milliseconds */
  timeout?: number;
  /** Maximum number of retries */
  maxRetries?: number;
  /** Initial retry delay in milliseconds */
  retryDelay?: number;
  /** Rate limit (requests per second) */
  rateLimit?: number;
}

/**
 * Wait for completion options
 */
export interface WaitOptions {
  /** Maximum wait time in milliseconds */
  timeout?: number;
  /** Polling interval in milliseconds */
  pollInterval?: number;
}
