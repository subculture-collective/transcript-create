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

- **Grafana**: http://localhost:3000
  - Username: `admin`
  - Password: `admin` (change on first login)
- **Prometheus**: http://localhost:9090

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
   - Visit http://localhost:9090/targets
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
