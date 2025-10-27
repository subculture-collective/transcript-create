/**
 * Transcript Create API Client
 */

import ky, { type KyInstance, type Options as KyOptions } from 'ky';
import type {
  ClientOptions,
  Job,
  JobCreateRequest,
  JobKind,
  SearchOptions,
  SearchResponse,
  SearchSource,
  TranscriptResponse,
  VideoInfo,
  WaitOptions,
  YouTubeTranscriptResponse,
} from './types';
import { handleErrorResponse, NetworkError, TimeoutError } from './errors';
import { withRetry, DEFAULT_RETRY_CONFIG, type RetryConfig } from './retry';
import { RateLimiter, AdaptiveRateLimiter } from './rate-limiter';

/**
 * Transcript Create API Client
 */
export class TranscriptClient {
  private client: KyInstance;
  private rateLimiter?: RateLimiter | AdaptiveRateLimiter;
  private retryConfig: RetryConfig;

  constructor(options: ClientOptions = {}) {
    const {
      baseUrl = 'http://localhost:8000',
      apiKey,
      timeout = 30000,
      maxRetries = 3,
      retryDelay = 1000,
      rateLimit,
    } = options;

    // Setup ky client
    const kyOptions: KyOptions = {
      prefixUrl: baseUrl,
      timeout,
      retry: 0, // We handle retries ourselves
    };

    // Add API key if provided
    if (apiKey) {
      kyOptions.headers = {
        Authorization: `Bearer ${apiKey}`,
      };
    }

    this.client = ky.create(kyOptions);

    // Setup rate limiting
    if (rateLimit) {
      this.rateLimiter = new AdaptiveRateLimiter(rateLimit);
    }

    // Setup retry configuration
    this.retryConfig = {
      ...DEFAULT_RETRY_CONFIG,
      maxRetries,
      initialDelay: retryDelay,
    };
  }

  /**
   * Make HTTP request with error handling and retry logic
   */
  private async request<T>(path: string, options?: KyOptions): Promise<T> {
    // Apply rate limiting
    if (this.rateLimiter) {
      await this.rateLimiter.acquire();
    }

    return withRetry(async () => {
      try {
        const response = await this.client(path, options);

        // Handle rate limiting feedback
        if (response.status === 429 && this.rateLimiter instanceof AdaptiveRateLimiter) {
          this.rateLimiter.onRateLimit();
        }

        // Check for errors
        if (!response.ok) {
          let errorData: any;
          try {
            errorData = await response.json();
          } catch {
            // Response might not be JSON
          }
          handleErrorResponse(response, errorData);
        }

        // Success callback for adaptive rate limiting
        if (this.rateLimiter instanceof AdaptiveRateLimiter) {
          this.rateLimiter.onSuccess();
        }

        return response.json<T>();
      } catch (error: any) {
        // Convert fetch errors to our error types
        if (error.name === 'TimeoutError') {
          throw new TimeoutError(`Request timeout: ${error.message}`);
        } else if (error.name === 'TypeError' && error.message.includes('fetch')) {
          throw new NetworkError(`Network error: ${error.message}`);
        }
        throw error;
      }
    }, this.retryConfig);
  }

  // Jobs API

  /**
   * Create a new transcription job
   */
  async createJob(url: string, kind: JobKind = 'single'): Promise<Job> {
    const body: JobCreateRequest = { url, kind };
    return this.request<Job>('jobs', {
      method: 'POST',
      json: body,
    });
  }

  /**
   * Get job status
   */
  async getJob(jobId: string): Promise<Job> {
    return this.request<Job>(`jobs/${jobId}`);
  }

  /**
   * Wait for job to complete
   */
  async waitForCompletion(jobId: string, options: WaitOptions = {}): Promise<Job> {
    const { timeout = 3600000, pollInterval = 5000 } = options;
    const startTime = Date.now();

    while (true) {
      const job = await this.getJob(jobId);

      if (job.state === 'completed' || job.state === 'failed') {
        return job;
      }

      // Check timeout
      const elapsed = Date.now() - startTime;
      if (elapsed >= timeout) {
        throw new TimeoutError(`Job ${jobId} did not complete within ${timeout}ms`);
      }

      // Wait before next poll
      await new Promise((resolve) => setTimeout(resolve, pollInterval));
    }
  }

  // Videos API

  /**
   * Get video information
   */
  async getVideo(videoId: string): Promise<VideoInfo> {
    return this.request<VideoInfo>(`videos/${videoId}`);
  }

  /**
   * Get video transcript
   */
  async getTranscript(videoId: string): Promise<TranscriptResponse> {
    return this.request<TranscriptResponse>(`videos/${videoId}/transcript`);
  }

  /**
   * Get YouTube captions
   */
  async getYouTubeTranscript(videoId: string): Promise<YouTubeTranscriptResponse> {
    return this.request<YouTubeTranscriptResponse>(`videos/${videoId}/youtube-transcript.json`);
  }

  // Search API

  /**
   * Search transcripts
   */
  async search(options: SearchOptions): Promise<SearchResponse> {
    const { query, source = 'native', video_id, limit = 50, offset = 0 } = options;

    const searchParams: Record<string, string> = {
      q: query,
      source,
      limit: String(limit),
      offset: String(offset),
    };

    if (video_id) {
      searchParams.video_id = video_id;
    }

    return this.request<SearchResponse>('search', {
      searchParams,
    });
  }

  // Export API

  /**
   * Export transcript as SRT
   */
  async exportSRT(videoId: string, source: SearchSource = 'native'): Promise<Blob> {
    const path = source === 'native'
      ? `videos/${videoId}/transcript.srt`
      : `videos/${videoId}/youtube-transcript.srt`;

    const response = await this.client(path);
    if (!response.ok) {
      let errorData: any;
      try {
        errorData = await response.json();
      } catch {
        // Response might not be JSON
      }
      handleErrorResponse(response, errorData);
    }
    return response.blob();
  }

  /**
   * Export transcript as VTT
   */
  async exportVTT(videoId: string, source: SearchSource = 'native'): Promise<Blob> {
    const path = source === 'native'
      ? `videos/${videoId}/transcript.vtt`
      : `videos/${videoId}/youtube-transcript.vtt`;

    const response = await this.client(path);
    if (!response.ok) {
      let errorData: any;
      try {
        errorData = await response.json();
      } catch {
        // Response might not be JSON
      }
      handleErrorResponse(response, errorData);
    }
    return response.blob();
  }

  /**
   * Export transcript as PDF
   */
  async exportPDF(videoId: string): Promise<Blob> {
    const response = await this.client(`videos/${videoId}/transcript.pdf`);
    if (!response.ok) {
      let errorData: any;
      try {
        errorData = await response.json();
      } catch {
        // Response might not be JSON
      }
      handleErrorResponse(response, errorData);
    }
    return response.blob();
  }
}
