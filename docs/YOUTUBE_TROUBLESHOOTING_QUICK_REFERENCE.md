# YouTube Troubleshooting Quick Reference

Quick troubleshooting guide for common YouTube ingestion issues. For detailed guides, see:
- **[YouTube Ingestion Setup](youtube-ingestion-setup.md)** - Complete setup guide
- **[PO Token Manager](po-token-manager.md)** - Token configuration and troubleshooting

## Quick Diagnosis

### Error: "JavaScript runtime not available"

**Cause:** yt-dlp requires a JS runtime (Deno/Node/Bun/QuickJS) to solve YouTube challenges.

**Fix:**
```bash
# Install Deno (recommended)
curl -fsSL https://deno.land/install.sh | sh

# Verify installation
deno --version

# Test yt-dlp
yt-dlp --version

# Restart worker
docker compose restart worker
```

**See:** [JS Runtime Setup Guide](youtube-ingestion-setup.md#javascript-runtime-required)

---

### Error: "HTTP 403 Forbidden"

**Cause:** Missing cookies or PO tokens. YouTube requires authentication for many videos.

**Fix (Priority order):**

1. **Add cookies** (most common fix):
   ```bash
   # Export cookies from browser using extension:
   # Chrome/Edge: "Get cookies.txt LOCALLY"
   # Firefox: "cookies.txt"
   
   # Add to .env:
   YTDLP_COOKIES_PATH=/path/to/youtube_cookies.txt
   
   # Verify format (should show .youtube.com entries)
   head -5 /path/to/youtube_cookies.txt
   
   # Restart worker
   docker compose restart worker
   ```

2. **Configure PO tokens**:
   ```bash
   # Add to .env:
   PO_TOKEN_PLAYER=your_player_token
   PO_TOKEN_GVS=your_gvs_token
   ```

3. **Enable client fallback** (default, but verify):
   ```bash
   YTDLP_CLIENT_ORDER=web_safari,ios,android,tv
   ```

**See:**
- [Cookie Setup](youtube-ingestion-setup.md#cookies-configuration)
- [PO Token Setup](po-token-manager.md)
- [403 Troubleshooting](youtube-ingestion-setup.md#403-forbidden-errors)

---

### Error: "Circuit breaker is open"

**Cause:** Too many consecutive failures (≥5 by default) triggered protection mode.

**Check status:**
```bash
# Check logs
docker compose logs worker | grep "circuit breaker"

# Check metrics
curl -s http://localhost:8001/metrics | grep ytdlp_circuit_breaker_state
# 0 = closed (normal)
# 1 = open (blocking)
# 2 = half-open (testing)
```

**Fix:**

1. **Wait for automatic recovery** (60s by default)
2. **Fix underlying issue** (check cookies, tokens, YouTube status)
3. **Manual reset** (restart worker):
   ```bash
   docker compose restart worker
   ```

4. **Adjust threshold** if too sensitive:
   ```bash
   YTDLP_CIRCUIT_BREAKER_THRESHOLD=10  # Increase from default 5
   ```

**See:** [Circuit Breaker Guide](youtube-ingestion-setup.md#circuit-breaker-configuration)

---

### Error: "Token in cooldown period"

**Cause:** Token was recently marked invalid due to 403 error.

**Check:**
```bash
# Check cooldown status
docker compose logs worker | grep "cooldown"

# Check why tokens failed
docker compose logs worker | grep "marked as invalid"
```

**Fix:**

1. **Wait for cooldown** (60s by default)
2. **Check token validity**:
   ```bash
   # Test token manually
   yt-dlp --extractor-args "youtube:po_token=player:YOUR_TOKEN" \
          --get-url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
   ```
3. **Regenerate tokens** if expired
4. **Adjust cooldown** if needed:
   ```bash
   PO_TOKEN_COOLDOWN_SECONDS=30  # Reduce from default 60
   ```

**See:** [Token Cooldown Troubleshooting](po-token-manager.md#4-tokens-in-cooldown)

---

### Error: "Video unavailable" / "Sign in to confirm age"

**Cause:** Age-restricted or region-locked content requires authentication.

**Fix:**
```bash
# Export cookies while logged into YouTube
# See browser-specific instructions above

# Add to .env:
YTDLP_COOKIES_PATH=/path/to/youtube_cookies.txt

# Optional: Try geo-bypass
YTDLP_EXTRA_ARGS=--geo-bypass

# Restart worker
docker compose restart worker
```

**See:** [Cookie Export Guide](youtube-ingestion-setup.md#exporting-cookies-from-your-browser)

---

### Error: Download timeout

**Cause:** Large file, slow network, or default timeout too short.

**Fix:**
```bash
# Increase timeout in .env:
YTDLP_REQUEST_TIMEOUT=300.0  # 5 minutes (from default 120s)

# Check network connectivity
docker compose exec worker ping -c 3 youtube.com

# Try different client
YTDLP_CLIENT_ORDER=tv,android,ios,web_safari  # TV first (most reliable)

# Restart worker
docker compose restart worker
```

**See:** [Timeout Troubleshooting](youtube-ingestion-setup.md#video-download-timeout)

---

## Quick Health Checks

### 1. Verify JavaScript Runtime
```bash
# Check runtime is installed
which deno  # or node, bun, quickjs

# Check version
deno --version

# Test yt-dlp integration
yt-dlp --version

# Check worker logs for validation
docker compose logs worker | grep -i "javascript\|runtime"
```

### 2. Verify Cookies
```bash
# Check file exists and has correct permissions
ls -la /path/to/youtube_cookies.txt

# Verify format (should show .youtube.com)
head -n 5 /path/to/youtube_cookies.txt

# Test with yt-dlp
yt-dlp --cookies /path/to/youtube_cookies.txt \
       --get-title "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

### 3. Verify PO Tokens
```bash
# Check logs for token usage
docker compose logs worker | grep "PO tokens added"

# Check token metrics
curl -s http://localhost:8001/metrics | grep ytdlp_token_usage_total

# Check token failures
curl -s http://localhost:8001/metrics | grep po_token_failures_total
```

### 4. Verify Configuration
```bash
# Check key settings
grep -E "^JS_RUNTIME|^YTDLP|^PO_TOKEN" .env | grep -v "^#"

# Verify settings are loaded
docker compose exec worker printenv | grep YTDLP
```

### 5. Test Full Pipeline
```bash
# Submit test job
curl -X POST http://localhost:8000/jobs \
     -H 'Content-Type: application/json' \
     -d '{
       "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
       "kind": "single"
     }'

# Monitor logs
docker compose logs -f worker | grep -E "yt-dlp|download|client|circuit"
```

---

## Configuration Quick Copy-Paste

### Minimal Working Configuration

```bash
# .env - Minimal setup for local testing

# JavaScript Runtime (REQUIRED)
JS_RUNTIME_CMD=deno
JS_RUNTIME_ARGS=run -A
YTDLP_REQUIRE_JS_RUNTIME=true

# Client Fallback
YTDLP_CLIENT_ORDER=web_safari,ios,android,tv
YTDLP_TRIES_PER_CLIENT=2

# Circuit Breaker
YTDLP_CIRCUIT_BREAKER_ENABLED=true
YTDLP_CIRCUIT_BREAKER_THRESHOLD=5
YTDLP_CIRCUIT_BREAKER_COOLDOWN=60.0
```

### Production Configuration

```bash
# .env - Production setup with all features

# JavaScript Runtime (REQUIRED)
JS_RUNTIME_CMD=deno
JS_RUNTIME_ARGS=run -A
YTDLP_REQUIRE_JS_RUNTIME=true

# Cookies (HIGHLY RECOMMENDED)
YTDLP_COOKIES_PATH=/app/config/youtube_cookies.txt

# Client Fallback
YTDLP_CLIENT_ORDER=web_safari,ios,android,tv
YTDLP_TRIES_PER_CLIENT=2
YTDLP_RETRY_SLEEP=1.0
YTDLP_EXTRA_ARGS=--prefer-free-formats

# Retry and Backoff
YTDLP_MAX_RETRY_ATTEMPTS=3
YTDLP_BACKOFF_BASE_DELAY=1.0
YTDLP_BACKOFF_MAX_DELAY=60.0
YTDLP_BACKOFF_JITTER=true
YTDLP_REQUEST_TIMEOUT=120.0

# Circuit Breaker
YTDLP_CIRCUIT_BREAKER_ENABLED=true
YTDLP_CIRCUIT_BREAKER_THRESHOLD=5
YTDLP_CIRCUIT_BREAKER_COOLDOWN=60.0
YTDLP_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2

# PO Tokens (OPTIONAL BUT RECOMMENDED)
PO_TOKEN_PLAYER=your_player_token
PO_TOKEN_GVS=your_gvs_token
PO_TOKEN_CACHE_TTL=3600
PO_TOKEN_COOLDOWN_SECONDS=60
PO_TOKEN_USE_FOR_AUDIO=true
PO_TOKEN_USE_FOR_CAPTIONS=true
```

---

## Common Metrics to Monitor

### Success Rate
```bash
# Overall success rate (should be >95%)
curl -s http://localhost:8001/metrics | grep ytdlp_operation_attempts_total
```

### Token Usage
```bash
# Operations with tokens (should be high)
curl -s http://localhost:8001/metrics | grep 'ytdlp_token_usage_total{has_token="true"}'

# Token failures by reason
curl -s http://localhost:8001/metrics | grep po_token_failures_total
```

### Circuit Breaker
```bash
# Current state (0=closed/normal, 1=open/blocking, 2=half-open/testing)
curl -s http://localhost:8001/metrics | grep ytdlp_circuit_breaker_state

# Open events (should be rare)
curl -s http://localhost:8001/metrics | grep ytdlp_circuit_breaker_opens_total
```

### Client Fallback Success
```bash
# Success rate by client
curl -s http://localhost:8001/metrics | grep 'ytdlp_operation_attempts_total{result="success"}'
```

---

## Common Log Patterns

### Success
```
INFO: JavaScript runtime validation successful
INFO: PO tokens added to yt-dlp command
INFO: Running yt-dlp download command
INFO: yt-dlp download succeeded
```

### Token Failure
```
ERROR: HTTP 403 Forbidden
WARNING: Detected PO token failure
INFO: Marking token as invalid: player
DEBUG: Token entering cooldown for 60 seconds
```

### Circuit Breaker
```
WARNING: Circuit breaker opened after 5 consecutive failures
INFO: Circuit breaker entering half-open state
INFO: Circuit breaker closed after 2 successes
```

### Client Fallback
```
INFO: Trying client: web_safari
ERROR: Client web_safari failed
INFO: Trying client: ios
INFO: Client ios succeeded
```

---

## Decision Tree

```
Download fails
    │
    ├─> Error mentions "JavaScript runtime"?
    │   YES → Install JS runtime (see top of guide)
    │   NO  → Continue
    │
    ├─> HTTP 403 Forbidden?
    │   YES → Add cookies, configure PO tokens (see 403 section)
    │   NO  → Continue
    │
    ├─> "Circuit breaker open"?
    │   YES → Wait for cooldown or fix underlying issue (see circuit breaker section)
    │   NO  → Continue
    │
    ├─> "Token in cooldown"?
    │   YES → Wait or check token validity (see token cooldown section)
    │   NO  → Continue
    │
    ├─> "Video unavailable" or "Sign in"?
    │   YES → Add cookies from logged-in browser (see cookies section)
    │   NO  → Continue
    │
    └─> Timeout?
        YES → Increase timeout or try different client (see timeout section)
        NO  → Check logs and metrics for specific error
```

---

## Getting Help

If this quick reference doesn't solve your issue:

1. **Check detailed guides**:
   - [YouTube Ingestion Setup](youtube-ingestion-setup.md)
   - [PO Token Manager](po-token-manager.md)

2. **Check system health**:
   - [Health Checks](health-checks.md)
   - [Monitoring](MONITORING.md)

3. **Search issues**: https://github.com/subculture-collective/transcript-create/issues

4. **Create new issue**: https://github.com/subculture-collective/transcript-create/issues/new

Include in your issue:
- Error message from logs
- Relevant configuration (redact secrets!)
- Steps to reproduce
- Docker/system versions
