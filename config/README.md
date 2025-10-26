# Configuration Files

This directory contains configuration files for various services in the Transcript Create application.

## Directory Structure

```
config/
├── grafana/                      # Grafana configuration
│   ├── provisioning/            # Auto-provisioning configs
│   │   ├── datasources/         # Datasource definitions (Prometheus)
│   │   └── dashboards/          # Dashboard auto-load config
│   └── dashboards/              # Dashboard JSON files
│       ├── overview.json        # System overview dashboard
│       ├── api-performance.json # API metrics dashboard
│       └── pipeline.json        # Transcription pipeline dashboard
├── opensearch/                  # OpenSearch configuration
│   └── analysis/               # Search analysis configs
│       └── synonyms.txt        # Search synonyms
└── prometheus/                  # Prometheus configuration
    ├── prometheus.yml          # Main Prometheus config with scrape targets
    └── alerts.yml              # Alert rules definitions
```

## Monitoring Stack

See [docs/MONITORING.md](../docs/MONITORING.md) for comprehensive monitoring documentation.

### Quick Start

The monitoring stack is automatically started with `docker compose up -d`:

- **Grafana**: <http://localhost:3000> (admin/admin)
- **Prometheus**: <http://localhost:9090>

### Configuration Files

#### Prometheus (`prometheus/`)

- `prometheus.yml`: Main configuration including:
  - Scrape targets (API on :8000/metrics, Worker on :8001/metrics)
  - Data retention (30 days, 10GB max)
  - Alert rules reference

- `alerts.yml`: Alert definitions for:
  - High error rates (>5%)
  - Slow response times (p95 >1s)
  - Service downtime
  - Job failures
  - Queue backlogs

#### Grafana (`grafana/`)

##### Provisioning

Automatic setup of datasources and dashboards on Grafana startup:

- `provisioning/datasources/prometheus.yml`: Configures Prometheus as default datasource
- `provisioning/dashboards/dashboards.yml`: Auto-loads dashboards from `dashboards/`

##### Dashboards

Three pre-configured dashboards:

1. **overview.json**: High-level system health
   - Service status (API, Worker)
   - Request rates
   - Job statistics (created, completed)
   - Video queue depth

2. **api-performance.json**: API metrics deep-dive
   - Request rate by endpoint
   - Response time percentiles (p50, p95, p99)
   - Error rates and success rate
   - Concurrent requests
   - Search query rates

3. **pipeline.json**: Transcription pipeline monitoring
   - Processing durations by stage
   - Queue status (pending, in-progress)
   - Video processing rates
   - Chunk counts and durations
   - Model load times
   - GPU metrics (if available)

## Modifying Configuration

### Adding Scrape Targets

Edit `prometheus/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'my-service'
    static_configs:
      - targets: ['my-service:port']
```

### Adding Alerts

Edit `prometheus/alerts.yml`:

```yaml
- alert: MyAlert
  expr: my_metric > threshold
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Alert description"
```

### Customizing Dashboards

1. Modify dashboard in Grafana UI
2. Export JSON: Dashboard Settings → JSON Model
3. Save to `grafana/dashboards/`
4. Dashboard auto-updates on next Grafana restart

### Environment-Specific Configs

For production deployments:

1. Change Grafana admin password (or use env vars)
2. Enable Prometheus authentication
3. Add TLS/HTTPS reverse proxy
4. Configure Alertmanager for notifications

See [docs/MONITORING.md](../docs/MONITORING.md) for details.
