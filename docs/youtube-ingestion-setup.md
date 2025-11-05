# YouTube Ingestion Setup Guide

## Overview

This guide provides step-by-step instructions for setting up reliable YouTube video ingestion in Transcript Create. YouTube requires specific configurations including JavaScript runtimes, cookies, and PO tokens to successfully download videos.

## Prerequisites

### JavaScript Runtime (Required)

yt-dlp requires a JavaScript runtime to solve YouTube challenges and extract video information. Without this, video downloads will fail.

#### Recommended: Deno

Deno is the recommended runtime due to its security model and ease of installation.

**Linux/macOS:**
```bash
curl -fsSL https://deno.land/install.sh | sh
```

**Windows (PowerShell):**
```powershell
irm https://deno.land/install.ps1 | iex
```

**Homebrew (macOS/Linux):**
```bash
brew install deno
```

**Verify installation:**
```bash
deno --version
```

#### Alternative Runtimes

**Node.js:**
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install nodejs

# macOS
brew install node

# Windows
# Download from https://nodejs.org/

# Verify
node --version
```

**Bun:**
```bash
# Linux/macOS
curl -fsSL https://bun.sh/install | bash

# Windows
powershell -c "irm bun.sh/install.ps1|iex"

# Verify
bun --version
```

**QuickJS:**
```bash
# Ubuntu/Debian
sudo apt install quickjs

# macOS
brew install quickjs

# Verify
quickjs --version
```

### Configuration

Add the following to your `.env` file:

```bash
# JavaScript Runtime Configuration
JS_RUNTIME_CMD=deno               # Runtime command (deno, node, bun, quickjs)
JS_RUNTIME_ARGS=run -A            # Runtime arguments (Deno needs "run -A")
YTDLP_REQUIRE_JS_RUNTIME=true    # Enforce runtime validation at startup
```

**Runtime-specific arguments:**
- **Deno**: `run -A` (grants all permissions)
- **Node**: Leave empty or omit
- **Bun**: Leave empty or omit
- **QuickJS**: Leave empty or omit

### Health Checks

**Verify JavaScript runtime is accessible:**
```bash
# Test the runtime directly
which deno           # or node, bun, quickjs
deno --version       # or node --version, etc.

# Test yt-dlp integration
yt-dlp --version
```

**Test with a simple YouTube video:**
```bash
yt-dlp -f bestaudio --get-url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

If this command succeeds, your JavaScript runtime is properly configured.

**Check application logs:**
```bash
# Docker
docker compose logs -f api worker | grep -i "javascript\|runtime"

# Local
tail -f logs/api.log logs/worker.log | grep -i "javascript\|runtime"
```

Look for these success indicators:
```
INFO: Validating JavaScript runtime for yt-dlp...
INFO: JavaScript runtime validation successful
```

## Cookies Configuration

Cookies help bypass YouTube restrictions and access age-restricted or member-only content.

### Exporting Cookies from Your Browser

#### Chrome/Edge

1. Install the **"Get cookies.txt LOCALLY"** extension:
   - Chrome: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   - Edge: Available in Edge Add-ons

2. Navigate to `youtube.com` and ensure you're logged in

3. Click the extension icon and select **"Export"**

4. Save as `youtube_cookies.txt` in Netscape format

5. Place the file in a secure location accessible to the worker

#### Firefox

1. Install the **"cookies.txt"** extension:
   - [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

2. Visit `youtube.com` while logged in

3. Click the extension icon and export cookies

4. Save as `youtube_cookies.txt`

#### Safari

1. Install the **"Get cookies.txt"** extension or use a third-party tool

2. Alternatively, use a command-line tool:
   ```bash
   # Using cookiemonster (install via Homebrew)
   brew install cookiemonster
   cookiemonster youtube.com > youtube_cookies.txt
   ```

### Cookie File Format

Cookies must be in Netscape format. Here's an example:

```
# Netscape HTTP Cookie File
.youtube.com	TRUE	/	TRUE	0	CONSENT	YES+1
.youtube.com	TRUE	/	FALSE	1735689600	VISITOR_INFO1_LIVE	abc123def456
.youtube.com	TRUE	/	FALSE	1735689600	YSC	xyz789
```

**Important fields:**
- Domain (e.g., `.youtube.com`)
- Flag (TRUE/FALSE for domain matching)
- Path (e.g., `/`)
- Secure flag (TRUE/FALSE)
- Expiration timestamp
- Cookie name
- Cookie value

### Configuration

Add to your `.env` file:

```bash
# Path to cookies file (Netscape format)
YTDLP_COOKIES_PATH=/path/to/youtube_cookies.txt
```

**Security considerations:**
- Store cookies outside the repository (add to `.gitignore`)
- Use restrictive file permissions: `chmod 600 youtube_cookies.txt`
- Rotate cookies periodically (export fresh cookies every 30-60 days)
- Use separate accounts for automation vs personal use

### Verify Cookies

Test cookies with yt-dlp:

```bash
yt-dlp --cookies /path/to/youtube_cookies.txt \
       --get-url "https://www.youtube.com/watch?v=VIDEO_ID"
```

## Client Fallback Strategy

YouTube serves different content based on the client type. Configure fallback strategies to maximize success rates.

### Available Clients

1. **web_safari** - Safari web client (best quality, HLS streaming)
2. **ios** - iOS mobile client (good for bypassing restrictions)
3. **android** - Android mobile client (alternative mobile option)
4. **tv** - TV embedded client (most reliable fallback)

### Configuration

```bash
# Client order for fallback (comma-separated)
YTDLP_CLIENT_ORDER=web_safari,ios,android,tv

# Disable specific clients (comma-separated)
YTDLP_CLIENTS_DISABLED=

# Retry attempts per client
YTDLP_TRIES_PER_CLIENT=2

# Sleep between retries (seconds)
YTDLP_RETRY_SLEEP=1.0
```

### Safe Extractor Arguments

Common safe extractor args to add to `.env`:

```bash
# Additional extractor arguments (space-separated)
YTDLP_EXTRA_ARGS=--no-check-certificate --prefer-free-formats
```

**Available options:**
- `--no-check-certificate` - Skip SSL certificate validation (use cautiously)
- `--prefer-free-formats` - Prefer free video formats over premium
- `--geo-bypass` - Bypass geographic restrictions
- `--user-agent "Mozilla/5.0..."` - Custom user agent string

### How Fallback Works

When a download fails:
1. Worker tries `web_safari` client (first in order)
2. If it fails, tries `ios` client
3. If it fails, tries `android` client
4. If it fails, tries `tv` client (final fallback)
5. Each client is retried `YTDLP_TRIES_PER_CLIENT` times

**Metrics tracked:**
- `ytdlp_operation_attempts_total` - Total attempts per client
- `ytdlp_operation_duration_seconds` - Duration per operation
- `ytdlp_operation_errors_total` - Errors by classification

## Circuit Breaker Configuration

Circuit breakers prevent hot loops during YouTube outages or rate limiting.

### Settings

```bash
# Enable circuit breaker protection
YTDLP_CIRCUIT_BREAKER_ENABLED=true

# Consecutive failures before opening circuit
YTDLP_CIRCUIT_BREAKER_THRESHOLD=5

# Cooldown period before testing recovery (seconds)
YTDLP_CIRCUIT_BREAKER_COOLDOWN=60.0

# Successes in half-open state to close circuit
YTDLP_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2
```

### Circuit States

1. **Closed** (normal operation)
   - Requests flow through normally
   - Failures are counted
   - Opens when threshold is reached

2. **Open** (circuit breaker active)
   - Requests fail immediately without trying
   - No load on YouTube
   - Enters half-open after cooldown

3. **Half-Open** (testing recovery)
   - Limited requests allowed through
   - If successful, circuit closes
   - If failed, circuit reopens

### Monitoring Circuit Breaker

**Check status via logs:**
```bash
# Look for circuit breaker events
docker compose logs worker | grep -i "circuit"
```

**Example log messages:**
```
WARNING: Circuit breaker opened after 5 consecutive failures
INFO: Circuit breaker entering half-open state
INFO: Circuit breaker closed after successful recovery
```

**Prometheus metrics:**
- `ytdlp_circuit_breaker_state{state}` - Current state (0=closed, 1=open, 2=half-open)
- `ytdlp_circuit_breaker_opens_total` - Total times circuit opened
- `ytdlp_circuit_breaker_closes_total` - Total times circuit closed

## Retry and Backoff Configuration

Configure retry behavior for transient failures.

### Settings

```bash
# Maximum retry attempts for transient failures
YTDLP_MAX_RETRY_ATTEMPTS=3

# Initial backoff delay (seconds)
YTDLP_BACKOFF_BASE_DELAY=1.0

# Maximum backoff delay cap (seconds)
YTDLP_BACKOFF_MAX_DELAY=60.0

# Add random jitter to backoff delays (recommended)
YTDLP_BACKOFF_JITTER=true

# Timeout per request attempt (seconds)
YTDLP_REQUEST_TIMEOUT=120.0
```

### Backoff Strategy

Exponential backoff with jitter:
1. **First retry**: 1s + jitter
2. **Second retry**: 2s + jitter
3. **Third retry**: 4s + jitter
4. **Cap**: Never exceeds `YTDLP_BACKOFF_MAX_DELAY`

**Jitter** prevents thundering herd problems by randomizing retry timing.

## Complete Configuration Example

Here's a production-ready `.env` configuration:

```bash
# =========================================
# JavaScript Runtime (Required)
# =========================================
JS_RUNTIME_CMD=deno
JS_RUNTIME_ARGS=run -A
YTDLP_REQUIRE_JS_RUNTIME=true

# =========================================
# Cookies (Highly Recommended)
# =========================================
YTDLP_COOKIES_PATH=/app/config/youtube_cookies.txt

# =========================================
# Client Fallback Strategy
# =========================================
YTDLP_CLIENT_ORDER=web_safari,ios,android,tv
YTDLP_CLIENTS_DISABLED=
YTDLP_TRIES_PER_CLIENT=2
YTDLP_RETRY_SLEEP=1.0
YTDLP_EXTRA_ARGS=--prefer-free-formats

# =========================================
# Retry and Backoff
# =========================================
YTDLP_MAX_RETRY_ATTEMPTS=3
YTDLP_BACKOFF_BASE_DELAY=1.0
YTDLP_BACKOFF_MAX_DELAY=60.0
YTDLP_BACKOFF_JITTER=true
YTDLP_REQUEST_TIMEOUT=120.0

# =========================================
# Circuit Breaker
# =========================================
YTDLP_CIRCUIT_BREAKER_ENABLED=true
YTDLP_CIRCUIT_BREAKER_THRESHOLD=5
YTDLP_CIRCUIT_BREAKER_COOLDOWN=60.0
YTDLP_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2

# =========================================
# PO Tokens (Optional, see po-token-manager.md)
# =========================================
PO_TOKEN_PLAYER=
PO_TOKEN_GVS=
PO_TOKEN_SUBS=
PO_TOKEN_PROVIDER_ENABLED=false
```

## Testing Your Configuration

### 1. Test JavaScript Runtime

```bash
# Direct test
deno --version

# Test with yt-dlp
yt-dlp --version
```

### 2. Test Cookies

```bash
# Test cookie file format
head -5 /path/to/youtube_cookies.txt

# Test with yt-dlp
yt-dlp --cookies /path/to/youtube_cookies.txt \
       --get-title "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

### 3. Test Client Fallback

```bash
# Test specific client
yt-dlp --extractor-args "youtube:player_client=web_safari" \
       --get-url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Test with cookies + client
yt-dlp --cookies /path/to/youtube_cookies.txt \
       --extractor-args "youtube:player_client=ios" \
       --get-title "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

### 4. Test Full Pipeline

Create a test job:
```bash
curl -X POST http://localhost:8000/jobs \
     -H 'Content-Type: application/json' \
     -d '{
       "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
       "kind": "single"
     }'
```

Monitor logs:
```bash
docker compose logs -f worker | grep -E "yt-dlp|download|client|circuit"
```

## Troubleshooting

### JavaScript Runtime Not Found

**Error:**
```
ERROR: JavaScript runtime 'deno' not found in PATH
```

**Solution:**
1. Install the runtime (see [Prerequisites](#prerequisites))
2. Verify it's in PATH: `which deno`
3. Restart the worker: `docker compose restart worker`
4. Check configuration in `.env`

**Bypass (not recommended):**
```bash
YTDLP_REQUIRE_JS_RUNTIME=false
```

### Cookies Not Working

**Error:**
```
WARNING: Failed to download video: Sign in to confirm your age
```

**Solutions:**
1. **Re-export cookies**: Cookies may have expired
   - Export fresh cookies from your browser
   - Ensure you're logged into YouTube

2. **Check cookie file format**:
   ```bash
   head -5 /path/to/youtube_cookies.txt
   ```
   Should show Netscape format with `.youtube.com` domain

3. **Verify file permissions**:
   ```bash
   chmod 600 /path/to/youtube_cookies.txt
   ls -la /path/to/youtube_cookies.txt
   ```

4. **Test cookies manually**:
   ```bash
   yt-dlp --cookies /path/to/youtube_cookies.txt \
          --get-title "https://www.youtube.com/watch?v=VIDEO_ID"
   ```

### Client Fallback Not Triggering

**Error:**
```
ERROR: Video unavailable
```

**Check configuration:**
```bash
grep YTDLP_CLIENT .env
```

**Verify client order is set:**
```bash
YTDLP_CLIENT_ORDER=web_safari,ios,android,tv
```

**Check logs for fallback attempts:**
```bash
docker compose logs worker | grep "Trying client"
```

Should show:
```
INFO: Trying client: web_safari
INFO: Client web_safari failed, trying next...
INFO: Trying client: ios
```

### Circuit Breaker Stuck Open

**Error:**
```
WARNING: Circuit breaker is open, rejecting request
```

**Check circuit breaker state:**
```bash
docker compose logs worker | grep "circuit breaker"
```

**Solutions:**
1. **Wait for cooldown**: Circuit will test recovery after cooldown period
2. **Check YouTube status**: Verify YouTube is accessible
3. **Manually reset** (restart worker):
   ```bash
   docker compose restart worker
   ```

### Video Download Timeout

**Error:**
```
ERROR: yt-dlp download timed out after 120 seconds
```

**Solutions:**
1. **Increase timeout**:
   ```bash
   YTDLP_REQUEST_TIMEOUT=300.0  # 5 minutes
   ```

2. **Check network connectivity**:
   ```bash
   docker compose exec worker ping -c 3 youtube.com
   ```

3. **Try different client**:
   ```bash
   YTDLP_CLIENT_ORDER=tv,android,ios,web_safari
   ```

### 403 Forbidden Errors

**Error:**
```
ERROR: HTTP Error 403: Forbidden
```

**Common causes:**
1. **Rate limiting**: Too many requests from your IP
2. **Missing cookies**: YouTube requires authentication
3. **Bad PO tokens**: Tokens may be invalid or expired
4. **Geo-restrictions**: Video not available in your region

**Solutions:**

1. **Add cookies** (most common fix):
   ```bash
   YTDLP_COOKIES_PATH=/path/to/youtube_cookies.txt
   ```

2. **Configure PO tokens** (see [po-token-manager.md](po-token-manager.md)):
   ```bash
   PO_TOKEN_PLAYER=your_token_here
   PO_TOKEN_GVS=your_gvs_token_here
   ```

3. **Enable circuit breaker** (prevents hammering):
   ```bash
   YTDLP_CIRCUIT_BREAKER_ENABLED=true
   YTDLP_CIRCUIT_BREAKER_COOLDOWN=300.0  # 5 minutes
   ```

4. **Use geo-bypass**:
   ```bash
   YTDLP_EXTRA_ARGS=--geo-bypass
   ```

5. **Reduce request rate**:
   ```bash
   YTDLP_BACKOFF_BASE_DELAY=5.0
   YTDLP_BACKOFF_MAX_DELAY=300.0
   ```

## Metrics and Monitoring

### Key Metrics

Monitor these Prometheus metrics for YouTube ingestion health:

#### Operation Metrics
- `ytdlp_operation_duration_seconds` - Download duration histogram
- `ytdlp_operation_attempts_total` - Total attempts per client/type
- `ytdlp_operation_errors_total{classification}` - Errors by type

#### Token Metrics
- `ytdlp_token_usage_total{has_token}` - Operations with/without tokens
- `po_token_retrievals_total{token_type, result}` - Token retrieval status
- `po_token_cache_hits_total` - Cache efficiency

#### Circuit Breaker Metrics
- `ytdlp_circuit_breaker_state` - Current circuit state
- `ytdlp_circuit_breaker_opens_total` - Circuit breaker activations
- `ytdlp_circuit_breaker_closes_total` - Circuit breaker recoveries

### Grafana Dashboards

Access pre-configured dashboards:
- **Overview**: http://localhost:3000/d/overview
- **Transcription Pipeline**: http://localhost:3000/d/transcription

Key panels to monitor:
1. **Download Success Rate**: Should be >95%
2. **Circuit Breaker State**: Should be "closed" (0)
3. **Error Classification**: Identify error patterns
4. **Client Fallback Rate**: How often fallbacks succeed

### Log Analysis

**Extract error patterns:**
```bash
docker compose logs worker | \
    grep "ERROR" | \
    grep "yt-dlp" | \
    cut -d: -f4- | \
    sort | uniq -c | sort -rn
```

**Track success/failure rates:**
```bash
docker compose logs worker | \
    grep -E "yt-dlp download (succeeded|failed)" | \
    awk '{print $NF}' | \
    sort | uniq -c
```

**Monitor circuit breaker events:**
```bash
docker compose logs worker | grep "circuit breaker"
```

## Best Practices

### Development

1. **Use Deno**: Simplest runtime to set up and manage
2. **Test with public videos**: Validate setup before production
3. **Monitor logs**: Watch for runtime and client fallback issues
4. **Start simple**: Begin with defaults, tune as needed

### Production

1. **Configure cookies**: Essential for reliable downloads
2. **Enable all fallback clients**: Maximize success rate
3. **Set up PO tokens**: Required for many videos (see [po-token-manager.md](po-token-manager.md))
4. **Enable circuit breaker**: Prevent cascading failures
5. **Monitor metrics**: Track success rates and error patterns
6. **Rotate cookies**: Export fresh cookies monthly
7. **Use separate accounts**: Don't use personal YouTube account
8. **Set conservative timeouts**: Give videos time to download
9. **Configure backoff**: Respect rate limits

### Security

1. **Protect cookies**: Store with `chmod 600` permissions
2. **Exclude from version control**: Add to `.gitignore`
3. **Use environment variables**: Never hardcode secrets
4. **Rotate credentials**: Refresh cookies and tokens regularly
5. **Monitor for abuse**: Watch for unusual download patterns
6. **Use service accounts**: Dedicated accounts for automation

## Next Steps

- **PO Tokens**: See [po-token-manager.md](po-token-manager.md) for advanced token configuration
- **Health Checks**: See [health-checks.md](health-checks.md) for monitoring setup
- **Monitoring**: See [MONITORING.md](MONITORING.md) for comprehensive metrics
- **Error Handling**: See [ERROR_HANDLING.md](ERROR_HANDLING.md) for error recovery patterns

## Additional Resources

- [yt-dlp Documentation](https://github.com/yt-dlp/yt-dlp#readme)
- [yt-dlp Extractor Arguments](https://github.com/yt-dlp/yt-dlp#extractor-arguments)
- [Deno Installation](https://docs.deno.com/runtime/getting_started/installation/)
- [YouTube PO Tokens](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token)

## Support

For issues or questions:
- GitHub Issues: https://github.com/subculture-collective/transcript-create/issues
- Documentation: https://github.com/subculture-collective/transcript-create/tree/main/docs
