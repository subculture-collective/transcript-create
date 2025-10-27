/**
 * Custom error classes for the Transcript Create client
 */

import type { ErrorResponse } from './types';

/**
 * Base class for all API errors
 */
export class APIError extends Error {
  statusCode?: number;
  errorCode?: string;
  details?: Record<string, any>;

  constructor(
    message: string,
    statusCode?: number,
    errorCode?: string,
    details?: Record<string, any>
  ) {
    super(message);
    this.name = 'APIError';
    this.statusCode = statusCode;
    this.errorCode = errorCode;
    this.details = details;

    // Maintains proper stack trace for where our error was thrown (only available on V8)
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, this.constructor);
    }
  }

  toString(): string {
    const parts = [this.message];
    if (this.statusCode) {
      parts.push(`(status: ${this.statusCode})`);
    }
    if (this.errorCode) {
      parts.push(`(code: ${this.errorCode})`);
    }
    return parts.join(' ');
  }
}

/**
 * Authentication failed
 */
export class AuthenticationError extends APIError {
  constructor(message: string, statusCode?: number, errorCode?: string, details?: Record<string, any>) {
    super(message, statusCode, errorCode, details);
    this.name = 'AuthenticationError';
  }
}

/**
 * Invalid or missing API key
 */
export class InvalidAPIKeyError extends AuthenticationError {
  constructor(message: string, statusCode?: number, errorCode?: string, details?: Record<string, any>) {
    super(message, statusCode, errorCode, details);
    this.name = 'InvalidAPIKeyError';
  }
}

/**
 * Resource not found
 */
export class NotFoundError extends APIError {
  constructor(message: string, statusCode?: number, errorCode?: string, details?: Record<string, any>) {
    super(message, statusCode, errorCode, details);
    this.name = 'NotFoundError';
  }
}

/**
 * Transcript not found
 */
export class TranscriptNotFoundError extends NotFoundError {
  constructor(message: string, statusCode?: number, errorCode?: string, details?: Record<string, any>) {
    super(message, statusCode, errorCode, details);
    this.name = 'TranscriptNotFoundError';
  }
}

/**
 * Request validation failed
 */
export class ValidationError extends APIError {
  constructor(message: string, statusCode?: number, errorCode?: string, details?: Record<string, any>) {
    super(message, statusCode, errorCode, details);
    this.name = 'ValidationError';
  }
}

/**
 * Rate limit exceeded
 */
export class RateLimitError extends APIError {
  retryAfter?: number;

  constructor(
    message: string,
    retryAfter?: number,
    statusCode?: number,
    errorCode?: string,
    details?: Record<string, any>
  ) {
    super(message, statusCode, errorCode, details);
    this.name = 'RateLimitError';
    this.retryAfter = retryAfter;
  }
}

/**
 * API quota exceeded
 */
export class QuotaExceededError extends APIError {
  constructor(message: string, statusCode?: number, errorCode?: string, details?: Record<string, any>) {
    super(message, statusCode, errorCode, details);
    this.name = 'QuotaExceededError';
  }
}

/**
 * Server error (5xx)
 */
export class ServerError extends APIError {
  constructor(message: string, statusCode?: number, errorCode?: string, details?: Record<string, any>) {
    super(message, statusCode, errorCode, details);
    this.name = 'ServerError';
  }
}

/**
 * Network connection error
 */
export class NetworkError extends APIError {
  constructor(message: string) {
    super(message);
    this.name = 'NetworkError';
  }
}

/**
 * Request timeout
 */
export class TimeoutError extends APIError {
  constructor(message: string) {
    super(message);
    this.name = 'TimeoutError';
  }
}

/**
 * Parse error response and throw appropriate error
 */
export function handleErrorResponse(response: Response, errorData?: ErrorResponse): never {
  const statusCode = response.status;
  const errorCode = errorData?.error || 'unknown_error';
  const message = errorData?.message || response.statusText || `HTTP ${statusCode}`;
  const details = errorData?.details;

  if (statusCode === 401) {
    throw new InvalidAPIKeyError(message, statusCode, errorCode, details);
  } else if (statusCode === 404) {
    if (message.toLowerCase().includes('transcript')) {
      throw new TranscriptNotFoundError(message, statusCode, errorCode, details);
    }
    throw new NotFoundError(message, statusCode, errorCode, details);
  } else if (statusCode === 402) {
    throw new QuotaExceededError(message, statusCode, errorCode, details);
  } else if (statusCode === 422) {
    throw new ValidationError(message, statusCode, errorCode, details);
  } else if (statusCode === 429) {
    const retryAfter = response.headers.get('Retry-After');
    const retryAfterSeconds = retryAfter ? parseInt(retryAfter, 10) : undefined;
    throw new RateLimitError(message, retryAfterSeconds, statusCode, errorCode, details);
  } else if (statusCode >= 500) {
    throw new ServerError(message, statusCode, errorCode, details);
  } else {
    throw new APIError(message, statusCode, errorCode, details);
  }
}
