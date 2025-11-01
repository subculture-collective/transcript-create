/**
 * Retry logic with exponential backoff
 */

import { NetworkError, RateLimitError, ServerError, TimeoutError } from './errors';

export interface RetryConfig {
  /** Maximum number of retry attempts */
  maxRetries: number;
  /** Initial delay between retries in milliseconds */
  initialDelay: number;
  /** Maximum delay between retries in milliseconds */
  maxDelay: number;
  /** Exponential backoff base */
  exponentialBase: number;
  /** Add random jitter to delays */
  jitter: boolean;
  /** HTTP status codes that should trigger retry */
  retryableStatusCodes: Set<number>;
}

export const DEFAULT_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  initialDelay: 1000,
  maxDelay: 60000,
  exponentialBase: 2,
  jitter: true,
  retryableStatusCodes: new Set([408, 429, 500, 502, 503, 504]),
};

/**
 * Calculate delay for the given attempt
 */
function calculateDelay(attempt: number, config: RetryConfig): number {
  let delay = Math.min(
    config.initialDelay * Math.pow(config.exponentialBase, attempt),
    config.maxDelay
  );

  if (config.jitter) {
    // Add "equal jitter" (aka half jitter): random value between 50% and 100% of delay.
    // See: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
    delay = delay * (0.5 + Math.random() * 0.5);
  }

  return delay;
}

/**
 * Check if error should trigger retry
 */
function shouldRetry(attempt: number, error: any, config: RetryConfig): boolean {
  if (attempt >= config.maxRetries) {
    return false;
  }

  // Always retry network errors and timeouts
  if (error instanceof NetworkError || error instanceof TimeoutError) {
    return true;
  }

  // Retry rate limit errors
  if (error instanceof RateLimitError) {
    return true;
  }

  // Retry server errors (5xx)
  if (error instanceof ServerError) {
    return true;
  }

  // Check HTTP status codes if available
  if (error.statusCode && config.retryableStatusCodes.has(error.statusCode)) {
    return true;
  }

  return false;
}

/**
 * Sleep for specified milliseconds
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Execute function with retry logic
 */
export async function withRetry<T>(
  fn: () => Promise<T>,
  config: RetryConfig = DEFAULT_RETRY_CONFIG
): Promise<T> {
  let lastError: any;

  for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      if (!shouldRetry(attempt, error, config)) {
        throw error;
      }

      if (attempt < config.maxRetries) {
        let delay = calculateDelay(attempt, config);

        // For rate limit errors, use Retry-After header if available
        if (error instanceof RateLimitError && error.retryAfter) {
          delay = Math.max(delay, error.retryAfter * 1000);
        }

        await sleep(delay);
      }
    }
  }

  throw lastError;
}
