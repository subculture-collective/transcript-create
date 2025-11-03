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

#### No tokens available

```
WARNING: Failed to retrieve token from any provider
```

**Solution**: Configure at least one token source (manual or provider)

#### Tokens in cooldown

```
DEBUG: Token in cooldown period
```

**Solution**: Wait for cooldown to expire or investigate why tokens are failing

#### Provider timeout

```
WARNING: HTTP provider timeout
```

**Solution**: Increase `PO_TOKEN_PROVIDER_TIMEOUT` or check provider availability

#### Low cache hit rate

**Solution**: 
- Increase `PO_TOKEN_CACHE_TTL`
- Check if context varies too much (creates separate cache entries)
- Verify tokens aren't being invalidated frequently

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
