/**
 * Tests for error classes
 */

import { describe, it, expect } from 'vitest';
import {
  APIError,
  AuthenticationError,
  InvalidAPIKeyError,
  NotFoundError,
  TranscriptNotFoundError,
  ValidationError,
  RateLimitError,
  QuotaExceededError,
  ServerError,
  NetworkError,
  TimeoutError,
} from '../src/errors';

describe('Error Classes', () => {
  describe('APIError', () => {
    it('should create basic error', () => {
      const error = new APIError('Test error');
      expect(error.message).toBe('Test error');
      expect(error.name).toBe('APIError');
      expect(error.statusCode).toBeUndefined();
      expect(error.errorCode).toBeUndefined();
    });

    it('should create error with details', () => {
      const error = new APIError('Test error', 400, 'test_error', { field: 'value' });
      expect(error.message).toBe('Test error');
      expect(error.statusCode).toBe(400);
      expect(error.errorCode).toBe('test_error');
      expect(error.details).toEqual({ field: 'value' });
    });

    it('should format toString correctly', () => {
      const error = new APIError('Test error', 400, 'test_error');
      const str = error.toString();
      expect(str).toContain('Test error');
      expect(str).toContain('400');
      expect(str).toContain('test_error');
    });
  });

  describe('Specific Error Types', () => {
    it('should create AuthenticationError', () => {
      const error = new AuthenticationError('Auth failed', 401);
      expect(error).toBeInstanceOf(APIError);
      expect(error.name).toBe('AuthenticationError');
      expect(error.statusCode).toBe(401);
    });

    it('should create InvalidAPIKeyError', () => {
      const error = new InvalidAPIKeyError('Invalid key');
      expect(error).toBeInstanceOf(AuthenticationError);
      expect(error).toBeInstanceOf(APIError);
      expect(error.name).toBe('InvalidAPIKeyError');
    });

    it('should create NotFoundError', () => {
      const error = new NotFoundError('Resource not found', 404);
      expect(error).toBeInstanceOf(APIError);
      expect(error.name).toBe('NotFoundError');
      expect(error.statusCode).toBe(404);
    });

    it('should create TranscriptNotFoundError', () => {
      const error = new TranscriptNotFoundError('Transcript not found');
      expect(error).toBeInstanceOf(NotFoundError);
      expect(error).toBeInstanceOf(APIError);
      expect(error.name).toBe('TranscriptNotFoundError');
    });

    it('should create ValidationError', () => {
      const error = new ValidationError(
        'Validation failed',
        422,
        'validation_error',
        { errors: [{ field: 'url', message: 'Invalid' }] }
      );
      expect(error).toBeInstanceOf(APIError);
      expect(error.name).toBe('ValidationError');
      expect(error.statusCode).toBe(422);
      expect(error.details).toBeDefined();
    });

    it('should create RateLimitError', () => {
      const error = new RateLimitError('Rate limit exceeded', 60, 429);
      expect(error).toBeInstanceOf(APIError);
      expect(error.name).toBe('RateLimitError');
      expect(error.retryAfter).toBe(60);
      expect(error.statusCode).toBe(429);
    });

    it('should create QuotaExceededError', () => {
      const error = new QuotaExceededError('Quota exceeded', 402);
      expect(error).toBeInstanceOf(APIError);
      expect(error.name).toBe('QuotaExceededError');
      expect(error.statusCode).toBe(402);
    });

    it('should create ServerError', () => {
      const error = new ServerError('Internal server error', 500);
      expect(error).toBeInstanceOf(APIError);
      expect(error.name).toBe('ServerError');
      expect(error.statusCode).toBe(500);
    });

    it('should create NetworkError', () => {
      const error = new NetworkError('Network failure');
      expect(error).toBeInstanceOf(APIError);
      expect(error.name).toBe('NetworkError');
    });

    it('should create TimeoutError', () => {
      const error = new TimeoutError('Request timeout');
      expect(error).toBeInstanceOf(APIError);
      expect(error.name).toBe('TimeoutError');
    });
  });
});
