# PO Token Manager

## Overview

The PO Token Manager is a component that manages YouTube PO (proof-of-origin) tokens required for Player, GVS (GetVideoStream), and Subs (Subtitles) API calls. It provides a flexible abstraction for obtaining, caching, and providing tokens through multiple provider strategies.

## Architecture

### Components

1. **POTokenManager**: Main coordinator that manages providers and caching
2. **POTokenProvider**: Protocol/interface for token providers
3. **POTokenCache**: Cache with TTL and cooldown logic
4. **Token Providers**:
   - `ManualTokenProvider`: Manual token injection from settings/environment
   - `HTTPTokenProvider`: External HTTP service for token generation

### Token Types

The system supports three YouTube token types:

- **PLAYER**: Player API token for video playback
- **GVS**: GetVideoStream API token for stream access
- **SUBS**: Subtitles API token for caption access

## Configuration

### Environment Variables

Add these settings to your `.env` file:

```bash
# Manual token injection (highest priority)
PO_TOKEN_PLAYER=your_player_token_here
PO_TOKEN_GVS=your_gvs_token_here
PO_TOKEN_SUBS=your_subs_token_here

# External provider configuration
PO_TOKEN_PROVIDER_ENABLED=false
PO_TOKEN_PROVIDER_URL=http://localhost:8080
PO_TOKEN_PROVIDER_TIMEOUT=5.0

# Cache and cooldown settings
PO_TOKEN_CACHE_TTL=3600          # 1 hour
PO_TOKEN_COOLDOWN_SECONDS=60     # 1 minute
```

### Settings Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `PO_TOKEN_PLAYER` | `""` | Manual player token |
| `PO_TOKEN_GVS` | `""` | Manual GVS token |
| `PO_TOKEN_SUBS` | `""` | Manual subs token |
| `PO_TOKEN_PROVIDER_ENABLED` | `False` | Enable external provider |
| `PO_TOKEN_PROVIDER_URL` | `""` | Provider service URL |
| `PO_TOKEN_PROVIDER_TIMEOUT` | `5.0` | Provider request timeout (seconds) |
| `PO_TOKEN_CACHE_TTL` | `3600` | Token cache TTL (seconds) |
| `PO_TOKEN_COOLDOWN_SECONDS` | `60` | Cooldown after failure (seconds) |

## Usage

### Basic Usage

The token manager is automatically initialized in the worker loop:

```python
from worker.po_token_manager import get_token_manager, TokenType

# Get the global token manager instance
token_manager = get_token_manager()

# Request a token
player_token = token_manager.get_token(TokenType.PLAYER)
if player_token:
    # Use token in yt-dlp or other YouTube API calls
    pass
```

### With Context

Tokens can be requested with context for more specific caching:

```python
context = {
    "region": "us",
    "session_id": "abc123",
    "client": "web_safari"
}

token = token_manager.get_token(TokenType.PLAYER, context=context)
```

### Mark Token as Invalid

When a token fails (e.g., 403 Forbidden), mark it as invalid to trigger cooldown:

```python
token_manager.mark_token_invalid(
    TokenType.PLAYER,
    reason="forbidden_error"
)
```

### Get Statistics

Monitor token manager performance:

```python
stats = token_manager.get_stats()
print(f"Cache hit rate: {stats['cache']['hit_rate']:.2%}")
print(f"Success rate: {stats['retrievals']['success_rate']:.2%}")
```

## Provider Implementation

### Manual Provider

The simplest provider reads tokens from settings:

```python
from worker.po_token_providers import ManualTokenProvider

provider = ManualTokenProvider(
    player_token="manual_token_123",
    gvs_token="gvs_token_456",
)
```

### HTTP Provider

External service for dynamic token generation:

```python
from worker.po_token_providers import HTTPTokenProvider

provider = HTTPTokenProvider(
    base_url="http://localhost:8080",
    timeout=5.0,
)
```

#### HTTP Provider API Contract

Your external service should implement:

**Endpoint**: `GET /token`

**Query Parameters**:
- `type`: Token type (`player`, `gvs`, or `subs`)
- `context` (optional): JSON-encoded context object

**Response Format**:
```json
{
  "token": "generated_token_value"
}
```

**Error Response**:
```json
{
  "error": "error_message"
}
```

### Custom Provider

Implement the `POTokenProvider` protocol:

```python
from typing import Optional
from worker.po_token_manager import POTokenProvider, TokenType

class CustomProvider:
    """Custom token provider example."""
    
    def get_token(self, token_type: TokenType, context: Optional[dict] = None) -> Optional[str]:
        # Your token generation logic here
        return "custom_token"
    
    def is_available(self) -> bool:
        # Check if provider is ready
        return True

# Register with manager
token_manager = get_token_manager()
token_manager.add_provider(CustomProvider())
```

## Caching Behavior

### TTL (Time-To-Live)

Tokens are cached for `PO_TOKEN_CACHE_TTL` seconds (default: 1 hour). After expiration:
- Cache returns `None`
- Manager tries providers again
- Fresh token is cached

### Cooldown

When a token is marked invalid:
- Token enters cooldown period (`PO_TOKEN_COOLDOWN_SECONDS`, default: 60s)
- Cache won't return the token during cooldown
- Prevents hammering providers with bad tokens
- After cooldown, providers are retried

### Cache Keys

Cache keys include:
- Token type (player, gvs, subs)
- Context values (if provided)

Example keys:
```
player
player:region=us:session_id=abc123
gvs:client=web_safari
```

## Integration with yt-dlp

The token manager is integrated into the worker's audio download process:

```python
# In worker/audio.py
def _yt_dlp_cmd(base_out: Path, url: str, strategy: Optional[ClientStrategy] = None) -> List[str]:
    cmd = ["yt-dlp", "-v", "-f", "bestaudio", ...]
    
    # Add PO tokens if available
    po_tokens = _get_po_tokens()
    if po_tokens:
        # Format: --extractor-args "youtube:po_token=player:TOKEN1;po_token=gvs:TOKEN2"
        token_args = []
        for token_type, token_value in po_tokens.items():
            token_args.append(f"po_token={token_type}:{token_value}")
        
        extractor_arg = "youtube:" + ";".join(token_args)
        cmd.extend(["--extractor-args", extractor_arg])
    
    return cmd
```

## Metrics

The following Prometheus metrics are exported:

### Token Retrieval Metrics

- `po_token_retrievals_total{token_type, result}`: Total token retrievals
  - `result`: `success`, `failed`, `cached`
  
- `po_token_provider_attempts_total{provider, token_type}`: Provider attempts

- `po_token_cache_hits_total{token_type}`: Cache hits

- `po_token_cache_misses_total{token_type}`: Cache misses

- `po_token_retrieval_latency_seconds{provider, token_type}`: Retrieval latency histogram

- `po_token_failures_total{token_type, reason}`: Token failures/invalidations

### Accessing Metrics

```python
from worker.metrics import (
    po_token_retrievals_total,
    po_token_cache_hits_total,
)

# Increment counters
po_token_retrievals_total.labels(
    token_type="player",
    result="success"
).inc()

# Get manager stats programmatically
stats = token_manager.get_stats()
```

## Operational Considerations

### Token Scopes

YouTube PO tokens have different scopes:

1. **Player tokens**: Required for video playback API calls
2. **GVS tokens**: Required for GetVideoStream API (downloading)
3. **Subs tokens**: Required for subtitle/caption API calls

Most yt-dlp operations need **player** and **GVS** tokens. Subtitle operations need **subs** tokens.

### Token Lifecycle

1. **Acquisition**: Manager tries providers in order until one succeeds
2. **Caching**: Valid token cached with TTL
3. **Usage**: Token used in yt-dlp extractor args
4. **Expiration**: After TTL expires, token is refreshed
5. **Failure**: On 403/token errors, token is marked invalid and enters cooldown

### Error Handling

Token failures are detected via:
- HTTP 403 status codes
- "token" keyword in error messages
- "forbidden" keyword in error messages (only when "token" is also mentioned)

When detected:
- Only PLAYER and GVS token types are marked invalid on download failures
- Cooldown prevents immediate retry
- Providers are consulted after cooldown

### Best Practices

1. **Manual tokens for testing**: Use manual tokens during development
2. **Provider for production**: Implement HTTP provider for dynamic token generation
3. **Monitor metrics**: Track cache hit rates and failure reasons
4. **Tune TTL**: Adjust based on token validity period
5. **Tune cooldown**: Balance between retry frequency and provider load

### Troubleshooting

This section provides comprehensive troubleshooting for PO token issues.

#### Common Failure Modes

##### 1. HTTP 403 Forbidden Errors

**Symptoms:**
```
ERROR: HTTP Error 403: Forbidden
ERROR: Video unavailable
```

**Root causes:**
- Invalid or expired PO tokens
- Missing required tokens (PLAYER/GVS)
- YouTube rate limiting or IP blocking
- Token type mismatch (wrong token for operation)

**Diagnosis:**

Check logs for token-related errors:
```bash
docker compose logs worker | grep -E "token|403|forbidden"
```

Check metrics:
```bash
# Token usage
curl -s http://localhost:8001/metrics | grep ytdlp_token_usage_total

# Token failures
curl -s http://localhost:8001/metrics | grep po_token_failures_total
```

**Solutions:**

1. **Configure tokens** (if not set):
   ```bash
   PO_TOKEN_PLAYER=your_player_token
   PO_TOKEN_GVS=your_gvs_token
   ```

2. **Verify tokens are being used**:
   ```bash
   docker compose logs worker | grep "PO tokens added"
   ```

3. **Check token expiration**: Tokens typically expire after 1-24 hours
   - Re-generate tokens from provider
   - Or update manual tokens in `.env`

4. **Enable provider** for automatic refresh:
   ```bash
   PO_TOKEN_PROVIDER_ENABLED=true
   PO_TOKEN_PROVIDER_URL=http://your-token-service:8080
   ```

5. **Check cooldown status**:
   ```bash
   docker compose logs worker | grep "cooldown"
   ```

##### 2. Circuit Breaker Open

**Symptoms:**
```
WARNING: Circuit breaker is open, rejecting request
WARNING: Circuit breaker opened after 5 consecutive failures
```

**Root causes:**
- Multiple consecutive token failures (≥5 by default)
- YouTube API outage or rate limiting
- Network connectivity issues
- Invalid token configuration

**Diagnosis:**

Check circuit breaker state:
```bash
# Logs
docker compose logs worker | grep "circuit breaker"

# Metrics
curl -s http://localhost:8001/metrics | grep ytdlp_circuit_breaker
```

**Circuit breaker states:**
- `0` = Closed (normal)
- `1` = Open (blocking requests)
- `2` = Half-open (testing recovery)

**Solutions:**

1. **Wait for cooldown**: Circuit breaker will test recovery after cooldown period
   - Default: 60 seconds
   - Check: `YTDLP_CIRCUIT_BREAKER_COOLDOWN` in `.env`

2. **Verify YouTube is accessible**:
   ```bash
   docker compose exec worker curl -I https://www.youtube.com/
   ```

3. **Check token validity**: Invalid tokens cause repeated failures
   - Regenerate tokens
   - Test tokens manually with yt-dlp

4. **Adjust threshold** if too sensitive:
   ```bash
   YTDLP_CIRCUIT_BREAKER_THRESHOLD=10  # Increase from default 5
   ```

5. **Manual reset** (restart worker):
   ```bash
   docker compose restart worker
   ```

##### 3. No Tokens Available

**Symptoms:**
```
WARNING: Failed to retrieve token from any provider
DEBUG: No token available for type: player
```

**Root causes:**
- No providers configured
- All providers failed
- Provider service unreachable

**Diagnosis:**

Check token manager initialization:
```bash
docker compose logs worker | grep -E "token provider|token manager"
```

Check provider configuration:
```bash
grep PO_TOKEN .env
```

**Solutions:**

1. **Configure manual tokens** (simplest):
   ```bash
   PO_TOKEN_PLAYER=your_token_here
   PO_TOKEN_GVS=your_gvs_token_here
   ```

2. **Enable and test provider**:
   ```bash
   PO_TOKEN_PROVIDER_ENABLED=true
   PO_TOKEN_PROVIDER_URL=http://token-service:8080
   
   # Test provider endpoint
   curl http://token-service:8080/token?type=player
   ```

3. **Check provider logs** for errors:
   ```bash
   docker compose logs token-service  # If using external service
   ```

4. **Verify provider timeout** isn't too short:
   ```bash
   PO_TOKEN_PROVIDER_TIMEOUT=10.0  # Increase if needed
   ```

##### 4. Tokens in Cooldown

**Symptoms:**
```
DEBUG: Token in cooldown period
INFO: Token marked as invalid, entering cooldown
```

**Root causes:**
- Token was recently marked invalid due to 403 error
- Token used during cooldown period (≤60s by default)
- Provider returned invalid token

**Diagnosis:**

Check cooldown events:
```bash
docker compose logs worker | grep "cooldown"
```

Check last invalidation reason:
```bash
docker compose logs worker | grep "marked as invalid"
```

**Solutions:**

1. **Wait for cooldown to expire**: Default is 60 seconds
   ```bash
   PO_TOKEN_COOLDOWN_SECONDS=60
   ```

2. **Investigate why tokens fail**:
   - Check token expiration
   - Verify token format is correct
   - Test tokens manually:
     ```bash
     yt-dlp --extractor-args "youtube:po_token=player:YOUR_TOKEN" \
            --get-url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
     ```

3. **Increase cooldown** if tokens are getting rate limited:
   ```bash
   PO_TOKEN_COOLDOWN_SECONDS=300  # 5 minutes
   ```

4. **Decrease cooldown** if tokens are valid but marked incorrectly:
   ```bash
   PO_TOKEN_COOLDOWN_SECONDS=30  # 30 seconds
   ```

##### 5. Provider Timeout

**Symptoms:**
```
WARNING: HTTP provider timeout after 5.0 seconds
ERROR: Failed to retrieve token from HTTP provider
```

**Root causes:**
- Provider service is slow or overloaded
- Network latency between worker and provider
- Provider is down or unreachable

**Diagnosis:**

Test provider manually:
```bash
time curl -s http://your-provider:8080/token?type=player
```

Check provider logs:
```bash
docker compose logs token-provider  # If using docker compose
```

**Solutions:**

1. **Increase timeout**:
   ```bash
   PO_TOKEN_PROVIDER_TIMEOUT=15.0  # Increase from default 5.0
   ```

2. **Check network connectivity**:
   ```bash
   docker compose exec worker ping -c 3 token-provider
   docker compose exec worker curl -v http://token-provider:8080/health
   ```

3. **Add manual tokens as fallback**:
   ```bash
   PO_TOKEN_PLAYER=fallback_token
   PO_TOKEN_PROVIDER_ENABLED=true
   ```

4. **Scale provider** if it's overloaded
   ```bash
   docker compose up -d --scale token-provider=3
   ```

##### 6. Low Cache Hit Rate

**Symptoms:**
- Metrics show low `po_token_cache_hits_total` vs `po_token_cache_misses_total`
- Frequent provider calls
- High latency for token retrieval

**Diagnosis:**

Check cache metrics:
```bash
curl -s http://localhost:8001/metrics | grep po_token_cache
```

Calculate hit rate:
```bash
# Should be >80% for good performance
hits=$(curl -s http://localhost:8001/metrics | grep po_token_cache_hits_total | awk '{print $2}')
misses=$(curl -s http://localhost:8001/metrics | grep po_token_cache_misses_total | awk '{print $2}')
if [ $((hits + misses)) -eq 0 ]; then
  echo "Hit rate: No data yet"
else
  echo "Hit rate: $(echo "scale=2; $hits / ($hits + $misses) * 100" | bc)%"
fi
```

**Root causes:**
- TTL too short
- Tokens invalidated frequently (due to failures)
- Context varies too much (creates separate cache entries)
- Cache not enabled or configured

**Solutions:**

1. **Increase TTL**:
   ```bash
   PO_TOKEN_CACHE_TTL=7200  # 2 hours (from default 1 hour)
   ```

2. **Reduce context variation**: Use fewer context fields
   ```python
   # Instead of:
   context = {"region": "us", "session": uuid4(), "client": "web"}
   
   # Use:
   context = {"client": "web"}  # Fewer keys = better cache hit rate
   ```

3. **Reduce token invalidation**: Fix underlying token issues
   - Use valid tokens that don't expire quickly
   - Configure provider for automatic refresh

4. **Monitor invalidation reasons**:
   ```bash
   docker compose logs worker | grep "mark.*invalid"
   ```

#### Client Fallback Behavior

When PO tokens fail, the worker uses client fallback to try alternative YouTube clients.

**Fallback sequence:**
1. Try **web_safari** with PO tokens
2. If 403/token error, mark PLAYER/GVS tokens invalid
3. Cooldown prevents immediate token retry
4. Fall back to **ios** client (next in order)
5. Fall back to **android** client
6. Fall back to **tv** client (most reliable)

**Observing fallback in logs:**
```bash
docker compose logs worker | grep -E "Trying client|fallback|client failed"
```

**Example log sequence:**
```
INFO: Trying client: web_safari with PO tokens
ERROR: HTTP 403 Forbidden with web_safari
INFO: Marking PLAYER and GVS tokens as invalid
DEBUG: Token entering cooldown for 60 seconds
INFO: Client web_safari failed, trying next...
INFO: Trying client: ios without PO tokens
INFO: Client ios succeeded
```

**Configuration:**
```bash
# Client order (tried in sequence)
YTDLP_CLIENT_ORDER=web_safari,ios,android,tv

# Retries per client
YTDLP_TRIES_PER_CLIENT=2

# Sleep between retries
YTDLP_RETRY_SLEEP=1.0
```

**Metrics:**
```bash
# Track which clients succeed/fail
curl -s http://localhost:8001/metrics | grep ytdlp_operation_attempts_total
```

#### Interpreting Logs

**Key log patterns to watch:**

1. **Token retrieval:**
   ```
   DEBUG: Retrieving PO token for type: player
   DEBUG: Token retrieved from ManualTokenProvider
   DEBUG: Token cache hit for player
   ```

2. **Token usage:**
   ```
   INFO: PO tokens added to yt-dlp command
   DEBUG: Using PLAYER token: abc***
   DEBUG: Using GVS token: def***
   ```

3. **Token failures:**
   ```
   ERROR: HTTP 403 Forbidden
   WARNING: Detected PO token failure
   INFO: Marking token as invalid: player (reason: forbidden_error)
   DEBUG: Token entering cooldown for 60 seconds
   ```

4. **Circuit breaker:**
   ```
   WARNING: Circuit breaker opened after 5 consecutive failures
   INFO: Circuit breaker entering half-open state
   INFO: Circuit breaker closed after 2 successes
   ```

5. **Provider errors:**
   ```
   WARNING: HTTP provider request failed: Connection timeout
   ERROR: Failed to retrieve token from HTTP provider
   DEBUG: Falling back to next provider
   ```

**Log levels guide:**
- `DEBUG`: Normal operations, cache hits, token retrievals
- `INFO`: State changes, provider switches, token additions
- `WARNING`: Failures, timeouts, circuit breaker events
- `ERROR`: Critical failures, provider errors, download failures

#### Interpreting Metrics

**Essential metrics to monitor:**

1. **Token usage:**
   ```
   ytdlp_token_usage_total{has_token="true"}  # Operations with tokens
   ytdlp_token_usage_total{has_token="false"} # Operations without tokens
   ```
   - Goal: Most operations should have `has_token="true"`
   - Alert if ratio drops below 80%

2. **Token retrieval success rate:**
   ```
   po_token_retrievals_total{result="success"}
   po_token_retrievals_total{result="failed"}
   po_token_retrievals_total{result="cached"}
   ```
   - Goal: Success + cached > 95%
   - Alert if failed > 5%

3. **Cache performance:**
   ```
   po_token_cache_hits_total
   po_token_cache_misses_total
   ```
   - Goal: Hit rate > 80%
   - Calculate: `hits / (hits + misses)`

4. **Token failures:**
   ```
   po_token_failures_total{token_type="player", reason="forbidden_error"}
   po_token_failures_total{token_type="gvs", reason="timeout"}
   ```
   - Track failure reasons to identify patterns
   - High `forbidden_error` = token validity issue
   - High `timeout` = provider performance issue

5. **Circuit breaker:**
   ```
   ytdlp_circuit_breaker_state  # 0=closed, 1=open, 2=half-open
   ytdlp_circuit_breaker_opens_total
   ytdlp_circuit_breaker_closes_total
   ```
   - Alert if state = 1 (open) for >5 minutes
   - Track open/close ratio (should trend toward more closes)

6. **Provider performance:**
   ```
   po_token_retrieval_latency_seconds{provider="manual"}
   po_token_retrieval_latency_seconds{provider="http"}
   ```
   - Goal: p95 < 1s for HTTP provider
   - Alert if p95 > 5s

**Grafana query examples:**

```promql
# Token success rate (last 1h)
sum(rate(po_token_retrievals_total{result="success"}[1h])) /
sum(rate(po_token_retrievals_total[1h]))

# Cache hit rate (check both metrics exist before calculating)
sum(po_token_cache_hits_total) /
(sum(po_token_cache_hits_total) + sum(po_token_cache_misses_total))

# Circuit breaker open duration
sum(increase(ytdlp_circuit_breaker_opens_total[1h])) by (component)

# Token failure rate by reason
sum(rate(po_token_failures_total[5m])) by (reason)
```

#### Feature Flag Configuration

Use feature flags to enable/disable token usage for specific operations:

```bash
# Use PO tokens for audio downloads (Player/GVS)
PO_TOKEN_USE_FOR_AUDIO=true

# Use PO tokens for caption fetching (Subs)
PO_TOKEN_USE_FOR_CAPTIONS=true
```

**Use cases:**
- Gradual rollout: Enable for captions first, then audio
- A/B testing: Compare success rates with/without tokens
- Emergency disable: Turn off if tokens cause issues
- Selective usage: Use tokens only for operations that need them

**Metrics by feature flag:**
```bash
# Audio downloads with/without tokens
curl -s http://localhost:8001/metrics | \
  grep 'ytdlp_token_usage_total{operation="audio"}'

# Caption fetches with/without tokens
curl -s http://localhost:8001/metrics | \
  grep 'ytdlp_token_usage_total{operation="captions"}'
```

#### Cooldown Period Behavior

Understanding cooldown mechanics:

1. **Trigger**: Token marked invalid due to 403 or token-related error
2. **Duration**: `PO_TOKEN_COOLDOWN_SECONDS` (default: 60s)
3. **Behavior**:
   - Token won't be returned from cache during cooldown
   - Provider will be consulted after cooldown expires
   - Other token types not affected (PLAYER cooldown doesn't affect GVS)

**Cooldown tuning:**

- **Short cooldown (30s)**: Fast recovery, higher provider load
  ```bash
  PO_TOKEN_COOLDOWN_SECONDS=30
  ```
  Use when: Tokens are valid but occasionally marked incorrectly

- **Medium cooldown (60s)**: Balanced (default)
  ```bash
  PO_TOKEN_COOLDOWN_SECONDS=60
  ```
  Use when: Standard operation

- **Long cooldown (300s)**: Slow recovery, lower provider load
  ```bash
  PO_TOKEN_COOLDOWN_SECONDS=300
  ```
  Use when: Provider is expensive or rate-limited

**Monitor cooldown events:**
```bash
# Count cooldown events per hour
docker compose logs worker --since 1h | grep "entering cooldown" | wc -l

# Average cooldown duration
docker compose logs worker | \
  grep -E "entering cooldown|exiting cooldown" | \
  # Parse timestamps and calculate durations
  awk '{print $1, $2, $NF}'
```

#### Quick Troubleshooting Flowchart

```
Video download fails with 403
    │
    ├─> Check: Are PO tokens configured?
    │   ├─> NO  → Configure PO_TOKEN_PLAYER and PO_TOKEN_GVS
    │   └─> YES → Continue
    │
    ├─> Check: Are tokens being used?
    │   │   (Look for "PO tokens added" in logs)
    │   ├─> NO  → Check PO_TOKEN_USE_FOR_AUDIO=true
    │   └─> YES → Continue
    │
    ├─> Check: Are tokens in cooldown?
    │   │   (Look for "cooldown" in logs)
    │   ├─> YES → Wait for cooldown or investigate why tokens fail
    │   └─> NO  → Continue
    │
    ├─> Check: Is circuit breaker open?
    │   │   (Look for "circuit breaker open")
    │   ├─> YES → Wait for cooldown or fix underlying issue
    │   └─> NO  → Continue
    │
    ├─> Check: Are tokens expired?
    │   ├─> YES → Regenerate tokens (manual or provider)
    │   └─> NO  → Continue
    │
    └─> Check: Does client fallback work?
        ├─> YES → Success with fallback client
        └─> NO  → Check cookies, circuit breaker threshold,
                  network connectivity, YouTube status

## Example Configurations

### Development (Manual Tokens)

```bash
PO_TOKEN_PLAYER=dev_player_token_abc123
PO_TOKEN_GVS=dev_gvs_token_def456
PO_TOKEN_SUBS=dev_subs_token_ghi789
PO_TOKEN_PROVIDER_ENABLED=false
```

### Production (HTTP Provider)

```bash
PO_TOKEN_PLAYER=
PO_TOKEN_GVS=
PO_TOKEN_SUBS=
PO_TOKEN_PROVIDER_ENABLED=true
PO_TOKEN_PROVIDER_URL=http://token-service:8080
PO_TOKEN_PROVIDER_TIMEOUT=10.0
PO_TOKEN_CACHE_TTL=7200
PO_TOKEN_COOLDOWN_SECONDS=120
```

### Hybrid (Manual + Provider Fallback)

```bash
PO_TOKEN_PLAYER=fallback_player_token
PO_TOKEN_GVS=
PO_TOKEN_SUBS=
PO_TOKEN_PROVIDER_ENABLED=true
PO_TOKEN_PROVIDER_URL=http://token-service:8080
```

Manual tokens are tried first, provider is used as fallback.

## Testing

Run the test suite:

```bash
# Run token manager tests
pytest tests/worker/test_po_token_manager.py -v

# Run provider tests
pytest tests/worker/test_po_token_providers.py -v

# Run all token-related tests
pytest tests/worker/test_po_token*.py -v
```

## Future Enhancements

Potential improvements:

1. **JavaScript runtime provider**: Execute JS code to generate tokens
2. **Token rotation**: Proactive token refresh before expiration
3. **Regional tokens**: Different tokens per geographic region
4. **Token validation**: Pre-check token validity before use
5. **Distributed cache**: Redis-backed cache for multi-worker deployments
6. **Rate limiting**: Limit provider call frequency
7. **Token pooling**: Maintain multiple valid tokens per type

## References

- [YouTube PO Token Documentation](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token)
- [yt-dlp Extractor Arguments](https://github.com/yt-dlp/yt-dlp#extractor-arguments)
- Worker implementation: `worker/po_token_manager.py`
- Providers: `worker/po_token_providers.py`
- Integration: `worker/audio.py`
