/**
 * Client-side rate limiting
 */

/**
 * Token bucket rate limiter
 */
export class RateLimiter {
  protected rate: number;
  private burstSize: number;
  private tokens: number;
  private lastUpdate: number;

  constructor(requestsPerSecond: number, burstSize?: number) {
    this.rate = requestsPerSecond;
    this.burstSize = burstSize || Math.floor(requestsPerSecond);
    this.tokens = this.burstSize;
    this.lastUpdate = Date.now();
  }

  /**
   * Acquire a token, waiting if necessary
   */
  async acquire(): Promise<void> {
    while (true) {
      const now = Date.now();
      const elapsed = (now - this.lastUpdate) / 1000;
      this.lastUpdate = now;

      // Add tokens based on elapsed time
      this.tokens = Math.min(this.burstSize, this.tokens + elapsed * this.rate);

      if (this.tokens >= 1) {
        this.tokens -= 1;
        return;
      }

      // Calculate wait time for next token
      const waitTime = ((1 - this.tokens) / this.rate) * 1000;
      await new Promise((resolve) => setTimeout(resolve, waitTime));
    }
  }

  /**
   * Reset rate limiter to full capacity
   */
  reset(): void {
    this.tokens = this.burstSize;
    this.lastUpdate = Date.now();
  }
}

/**
 * Adaptive rate limiter that adjusts based on 429 responses
 */
export class AdaptiveRateLimiter extends RateLimiter {
  private currentRate: number;
  private minRate: number;
  private maxRate: number;
  private increaseFactor: number;
  private decreaseFactor: number;
  private successCount: number;
  private successThreshold: number;

  constructor(
    initialRequestsPerSecond: number,
    options: {
      minRate?: number;
      maxRate?: number;
      increaseFactor?: number;
      decreaseFactor?: number;
    } = {}
  ) {
    super(initialRequestsPerSecond);
    this.currentRate = initialRequestsPerSecond;
    this.minRate = options.minRate || 1;
    this.maxRate = options.maxRate || 100;
    this.increaseFactor = options.increaseFactor || 1.1;
    this.decreaseFactor = options.decreaseFactor || 0.5;
    this.successCount = 0;
    this.successThreshold = 10;
  }

  /**
   * Called after successful request
   */
  onSuccess(): void {
    this.successCount++;

    if (this.successCount >= this.successThreshold) {
      // Gradually increase rate
      const newRate = Math.min(this.currentRate * this.increaseFactor, this.maxRate);
      if (newRate !== this.currentRate) {
        this.currentRate = newRate;
        this.rate = newRate; // Update parent class rate
        this.successCount = 0;
      }
    }
  }

  /**
   * Called when rate limit is hit
   */
  onRateLimit(): void {
    // Decrease rate immediately
    this.currentRate = Math.max(this.currentRate * this.decreaseFactor, this.minRate);
    this.rate = this.currentRate; // Update parent class rate
    this.successCount = 0;
  }
}
