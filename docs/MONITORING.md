# Monitoring with Prometheus & Grafana

This document describes the monitoring infrastructure for the Transcript Create application.

## Overview

The monitoring stack consists of:

- **Prometheus**: Time-series database for metrics collection
- **Grafana**: Visualization and dashboarding platform
- **Application Metrics**: Custom metrics exposed by API and Worker services

## Quick Start

### Starting the Monitoring Stack

```bash
# Start all services including Prometheus and Grafana
docker compose up -d

# Check that monitoring services are running
docker compose ps prometheus grafana
```

### Accessing the Dashboards

- **Grafana**: <http://localhost:3000>
  - Username: `admin`
  - Password: `admin` (change on first login)
- **Prometheus**: <http://localhost:9090>

### Pre-configured Dashboards

Three dashboards are automatically provisioned:

1. **Overview** (`transcript-overview`)
   - Service health status
   - Request rates
   - Job and video statistics
   - Queue depth

2. **API Performance** (`transcript-api`)
   - Request rate by endpoint
   - Response time percentiles (p50, p95, p99)
   - Error rates
   - Success rate
   - Concurrent requests
   - Search query rate

3. **Transcription Pipeline** (`transcript-pipeline`)
   - Transcription duration
   - Pipeline stage durations (download, transcode, diarization)
   - Video queue status
   - Processing rates
   - Chunks per video
   - Model load times

## Metrics Reference

### API Metrics

#### HTTP Request Metrics

- `http_requests_total` (counter): Total HTTP requests by method, endpoint, and status
- `http_request_duration_seconds` (histogram): Request latency distribution
- `http_requests_in_flight` (gauge): Current concurrent requests

#### Business Metrics

- `jobs_created_total` (counter): Jobs created by type (single/channel)
- `jobs_completed_total` (counter): Successfully completed jobs
- `jobs_failed_total` (counter): Failed jobs
- `videos_transcribed_total` (counter): Successfully transcribed videos
- `search_queries_total` (counter): Search queries by backend (postgres/opensearch)
- `exports_total` (counter): Exports by format (srt/vtt/json/pdf)

#### Database Metrics

- `db_connections_active` (gauge): Active database connections
- `db_query_duration_seconds` (histogram): Query duration distribution
- `db_errors_total` (counter): Database errors by type

### Worker Metrics

#### Processing Metrics

- `transcription_duration_seconds` (histogram): Total transcription time by model
- `download_duration_seconds` (histogram): Audio download time
- `transcode_duration_seconds` (histogram): Audio transcoding time
- `diarization_duration_seconds` (histogram): Speaker diarization time

#### Queue Metrics

- `videos_pending` (gauge): Videos waiting to be processed
- `videos_in_progress` (gauge): Videos currently being processed by state
- `videos_processed_total` (counter): Completed/failed video count

#### Whisper Model Metrics

- `whisper_model_load_seconds` (histogram): Model loading time by model and backend
- `whisper_chunk_transcription_seconds` (histogram): Per-chunk transcription time
- `chunk_count` (histogram): Number of audio chunks per video

#### GPU Metrics (Optional)

- `gpu_memory_used_bytes` (gauge): GPU memory in use by device
- `gpu_memory_total_bytes` (gauge): Total GPU memory by device

#### Ingestion Observability Metrics

These metrics track yt-dlp operations for audio download, metadata fetch, and caption retrieval:

- `ytdlp_operation_duration_seconds` (histogram): Duration of yt-dlp operations by operation type and client strategy
  - Labels: `operation` (download, metadata, captions), `client` (web_safari, ios, android, tv, direct, default)
  - Buckets: 1s, 2s, 5s, 10s, 20s, 30s, 60s, 120s, 180s, 300s, 600s
  
- `ytdlp_operation_attempts_total` (counter): Total operation attempts by result
  - Labels: `operation`, `client`, `result` (success, failure)
  
- `ytdlp_operation_errors_total` (counter): Failed operations by error classification
  - Labels: `operation`, `client`, `error_class` (network, throttle, auth, token, not_found, timeout, unknown)
  
- `ytdlp_token_usage_total` (counter): Operations tracked by PO token presence
  - Labels: `operation`, `has_token` (true, false)

- `youtube_circuit_breaker_state` (gauge): Circuit breaker state
  - Labels: `name` (youtube_download, youtube_metadata)
  - Values: 0=closed, 1=half_open, 2=open

- `youtube_circuit_breaker_transitions_total` (counter): State transitions
  - Labels: `name`, `from_state`, `to_state`

##### Useful Queries

**Success rate by client strategy:**
```promql
rate(ytdlp_operation_attempts_total{result="success"}[5m]) 
/ 
rate(ytdlp_operation_attempts_total[5m])
```

**95th percentile download duration by client:**
```promql
histogram_quantile(0.95, 
  rate(ytdlp_operation_duration_seconds_bucket{operation="download"}[5m])
)
```

**Error rate by classification:**
```promql
rate(ytdlp_operation_errors_total[5m])
```

**Token usage percentage:**
```promql
rate(ytdlp_token_usage_total{has_token="true"}[5m])
/
rate(ytdlp_token_usage_total[5m])
```

## Alerting

### Pre-configured Alerts

Alerts are defined in `/config/prometheus/alerts.yml`:

#### API Alerts

- **HighErrorRate**: API error rate >5% for 5 minutes
- **SlowResponseTime**: p95 latency >1s for 5 minutes
- **APIServiceDown**: API service unavailable for 2 minutes

#### Worker Alerts

- **NoJobsCompleted**: No jobs completed in 1 hour
- **WorkerServiceDown**: Worker service unavailable for 2 minutes
- **HighJobFailureRate**: Job failure rate >20% for 10 minutes
- **JobsStuckInQueue**: >50 videos pending for 30 minutes

#### Database Alerts

- **HighDatabaseErrors**: Database error rate >1/sec for 5 minutes

#### Ingestion Alerts

Recommended alerting thresholds for YouTube ingestion operations:

- **HighYtdlpErrorRate**: yt-dlp operation error rate >10% for 10 minutes
  ```promql
  (
    rate(ytdlp_operation_attempts_total{result="failure"}[10m])
    /
    rate(ytdlp_operation_attempts_total[10m])
  ) > 0.1
  ```

- **SlowYtdlpOperations**: p95 operation duration >120s for 15 minutes
  ```promql
  histogram_quantile(0.95,
    rate(ytdlp_operation_duration_seconds_bucket[15m])
  ) > 120
  ```

- **CircuitBreakerOpen**: Circuit breaker has been open for 5 minutes
  ```promql
  youtube_circuit_breaker_state == 2
  ```

- **HighThrottlingRate**: YouTube throttling errors >5/min for 10 minutes
  ```promql
  rate(ytdlp_operation_errors_total{error_class="throttle"}[10m]) > 0.083
  ```

- **TokenFailures**: PO token errors increasing
  ```promql
  rate(ytdlp_operation_errors_total{error_class="token"}[5m]) > 0
  ```

### Setting Up Alertmanager (Optional)

To receive alert notifications:

1. Add Alertmanager to `docker-compose.yml`:

```yaml
alertmanager:
  image: prom/alertmanager:v0.27.0
  command:
    - '--config.file=/etc/alertmanager/alertmanager.yml'
  volumes:
    - ./config/alertmanager:/etc/alertmanager
  ports:
    - "9093:9093"
```

2. Create `/config/alertmanager/alertmanager.yml`:

```yaml
global:
  slack_api_url: 'YOUR_SLACK_WEBHOOK_URL'

route:
  receiver: 'slack-notifications'
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 3h

receivers:
  - name: 'slack-notifications'
    slack_configs:
      - channel: '#alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
```

3. Uncomment the Alertmanager target in `config/prometheus/prometheus.yml`

## Adding Custom Metrics

### In the API

1. Define metric in `app/metrics.py`:

```python
from prometheus_client import Counter

my_metric = Counter(
    "my_metric_total",
    "Description of my metric",
    ["label1", "label2"],
)
```

2. Use metric in your code:

```python
from app.metrics import my_metric

my_metric.labels(label1="value1", label2="value2").inc()
```

### In the Worker

1. Define metric in `worker/metrics.py`:

```python
from prometheus_client import Histogram

my_worker_metric = Histogram(
    "my_worker_metric_seconds",
    "Description of my metric",
    buckets=(1, 5, 10, 30, 60, 120),
)
```

2. Use metric in your code:

```python
from worker.metrics import my_worker_metric
import time

start = time.time()
# ... do work ...
duration = time.time() - start
my_worker_metric.observe(duration)
```

### Best Practices

- **Metric Names**: Use snake_case and descriptive names
- **Labels**: Keep cardinality low (<100 unique combinations)
- **Units**: Include units in metric names (e.g., `_seconds`, `_bytes`, `_total`)
- **Metric Types**:
  - **Counter**: Monotonically increasing values (requests, errors)
  - **Gauge**: Values that can go up/down (queue size, memory)
  - **Histogram**: Distribution of values (duration, size)
  - **Summary**: Similar to histogram but with quantiles

## Troubleshooting

### Metrics Not Appearing

1. **Check service health**:

```bash
# API metrics endpoint
curl http://localhost:8000/metrics

# Worker metrics endpoint
curl http://localhost:8001/metrics
```

2. **Check Prometheus targets**:
   - Visit <http://localhost:9090/targets>
   - Ensure all targets are "UP"

3. **Check container logs**:

```bash
docker compose logs api worker prometheus grafana
```

### High Memory Usage

Prometheus stores metrics in memory and on disk. To reduce memory:

1. Decrease retention period in `config/prometheus/prometheus.yml`:

```yaml
storage:
  tsdb:
    retention.time: 15d  # Default is 30d
    retention.size: 5GB  # Default is 10GB
```

2. Reduce scrape frequency:

```yaml
global:
  scrape_interval: 30s  # Default is 15s
```

### Dashboard Not Loading

1. **Check Grafana logs**:

```bash
docker compose logs grafana
```

2. **Verify datasource**:
   - Go to Configuration → Data Sources
   - Test the Prometheus connection

3. **Re-import dashboard**:
   - Go to Dashboards → Import
   - Upload JSON file from `config/grafana/dashboards/`

### Performance Impact

Metrics collection overhead is typically <1% CPU and <100MB RAM.

To verify:

```bash
# Check resource usage
docker stats api worker prometheus grafana
```

If overhead is high:

- Reduce scrape frequency
- Decrease histogram bucket count
- Remove unused metrics

### YouTube Ingestion Issues

#### Common Error Classes and Remediation

The ingestion metrics classify errors to help diagnose issues:

**1. `throttle` errors (429, "too many requests")**
- **Cause**: YouTube rate limiting
- **Symptoms**: High `ytdlp_operation_errors_total{error_class="throttle"}`
- **Remediation**:
  - Circuit breaker will automatically back off
  - Increase `YTDLP_BACKOFF_MAX_DELAY` to slow retry rate
  - Enable PO tokens if not already active (`PO_TOKEN_USE_FOR_AUDIO=true`)
  - Reduce concurrent worker instances

**2. `token` errors (invalid/expired PO tokens)**
- **Cause**: PO tokens expired or rejected by YouTube
- **Symptoms**: High `ytdlp_operation_errors_total{error_class="token"}`
- **Remediation**:
  - Check PO token provider availability
  - Verify `PO_TOKEN_PROVIDER_URL` is accessible
  - Check token expiry with `po_token_failures_total` metric
  - Review logs for token invalidation events

**3. `auth` errors (403, "sign in required", "bot detected")**
- **Cause**: YouTube requiring authentication or detecting automated access
- **Symptoms**: High `ytdlp_operation_errors_total{error_class="auth"}`
- **Remediation**:
  - Enable PO tokens (required for most flows now)
  - Configure cookies file via `YTDLP_COOKIES_PATH`
  - Try different client strategies (ios, android as fallbacks)
  - Add delays: increase `YTDLP_BACKOFF_BASE_DELAY`

**4. `not_found` errors (404, unavailable, private)**
- **Cause**: Video is deleted, private, or region-locked
- **Symptoms**: High `ytdlp_operation_errors_total{error_class="not_found"}`
- **Remediation**:
  - These are expected and not retried automatically
  - Mark jobs as failed in application logic
  - No infrastructure changes needed

**5. `network` errors (connection issues, timeouts)**
- **Cause**: Network connectivity problems
- **Symptoms**: High `ytdlp_operation_errors_total{error_class="network"}`
- **Remediation**:
  - Check network connectivity to YouTube
  - Verify DNS resolution
  - Increase `YTDLP_REQUEST_TIMEOUT` if timeouts are frequent
  - Check firewall rules

**6. `timeout` errors (operation exceeded timeout)**
- **Cause**: Large files or slow connection
- **Symptoms**: High `ytdlp_operation_duration_seconds` and timeout errors
- **Remediation**:
  - Increase `YTDLP_REQUEST_TIMEOUT` (default 120s)
  - Check bandwidth availability
  - Consider chunking or streaming approaches

#### Monitoring Client Strategy Performance

Compare success rates across different client strategies:

```bash
# Query Prometheus for client performance
curl -G 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=rate(ytdlp_operation_attempts_total{result="success"}[5m]) by (client)'
```

If specific clients are failing frequently:
- Disable underperforming clients: `YTDLP_CLIENTS_DISABLED=android,ios`
- Reorder client priority: `YTDLP_CLIENT_ORDER=web_safari,tv,ios,android`

#### Structured Log Analysis

All ingestion operations log structured fields. Query logs with:

```bash
# Find slow downloads (>60s)
docker compose logs worker | jq 'select(.duration_seconds > 60 and .operation == "download")'

# Find operations without tokens
docker compose logs worker | jq 'select(.has_token == false and .operation != "captions")'

# Group errors by classification
docker compose logs worker | jq 'select(.error_class) | .error_class' | sort | uniq -c
```

## Backup and Restore

### Prometheus Data

```bash
# Backup
docker compose stop prometheus
tar -czf prometheus-backup.tar.gz -C $(docker volume inspect --format '{{ .Mountpoint }}' transcript-create_prometheus-data) .
docker compose start prometheus

# Restore
docker compose stop prometheus
tar -xzf prometheus-backup.tar.gz -C $(docker volume inspect --format '{{ .Mountpoint }}' transcript-create_prometheus-data)
docker compose start prometheus
```

### Grafana Dashboards

Dashboards are version-controlled in `config/grafana/dashboards/` and automatically provisioned.

To export a modified dashboard:

1. Go to Dashboard Settings → JSON Model
2. Copy JSON
3. Save to `config/grafana/dashboards/`

## Integration with External Systems

### Grafana Cloud

To send metrics to Grafana Cloud:

1. Add remote write to `config/prometheus/prometheus.yml`:

```yaml
remote_write:
  - url: https://prometheus-us-central1.grafana.net/api/prom/push
    basic_auth:
      username: YOUR_INSTANCE_ID
      password: YOUR_API_KEY
```

### Datadog

To send metrics to Datadog:

1. Add Datadog exporter to `docker-compose.yml`
2. Configure Prometheus to scrape Datadog exporter
3. Datadog will pull metrics automatically

## Security Considerations

### Production Recommendations

1. **Change default credentials**:
   - Grafana admin password
   - Add authentication to Prometheus

2. **Network isolation**:

```yaml
# In docker-compose.yml
networks:
  monitoring:
    internal: true

# Add network to monitoring services
prometheus:
  networks:
    - monitoring
```

3. **TLS/HTTPS**:
   - Use reverse proxy (nginx, traefik) for HTTPS
   - Configure certificate for Grafana

4. **Access control**:
   - Limit Grafana users and permissions
   - Use Grafana RBAC for team access

## Further Reading

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [PromQL Cheat Sheet](https://promlabs.com/promql-cheat-sheet/)
