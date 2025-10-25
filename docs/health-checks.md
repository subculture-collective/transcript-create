# Health Check Endpoints

This document describes the health check endpoints implemented for the Transcript Create API, designed for monitoring, load balancing, and Kubernetes deployment.

## Overview

The API provides four health check endpoints with different purposes:

| Endpoint | Purpose | Response Time | Checks Dependencies |
|----------|---------|---------------|---------------------|
| `/health` | Basic health check | < 100ms | No |
| `/live` | Kubernetes liveness probe | < 100ms | No |
| `/ready` | Kubernetes readiness probe | < 5s | Yes (critical only) |
| `/health/detailed` | Comprehensive status | < 5s | Yes (all) |

## Endpoints

### 1. Basic Health Check

**Endpoint:** `GET /health`

**Purpose:** Simple endpoint for load balancers and uptime monitoring.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-25T23:00:00.000000Z"
}
```

**Status Codes:**
- `200 OK`: Service is running

**Usage:**
- Load balancer health checks
- Uptime monitoring services
- Quick connectivity tests

**Characteristics:**
- No authentication required
- Minimal overhead (no DB queries)
- Always returns 200 if service is running

---

### 2. Liveness Probe

**Endpoint:** `GET /live`

**Purpose:** Kubernetes liveness probe to check if the process is alive.

**Response:**
```json
{
  "status": "alive",
  "timestamp": "2025-10-25T23:00:00.000000Z"
}
```

**Status Codes:**
- `200 OK`: Process is alive and responding

**Usage:**
- Kubernetes liveness probe
- Container orchestration health checks

**Kubernetes Configuration:**
```yaml
livenessProbe:
  httpGet:
    path: /live
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

**Characteristics:**
- No authentication required
- No dependency checks
- Minimal overhead
- Should never fail unless process is dead

---

### 3. Readiness Probe

**Endpoint:** `GET /ready`

**Purpose:** Check if service can accept traffic by verifying critical dependencies.

**Response (Ready):**
```json
{
  "status": "ready",
  "timestamp": "2025-10-25T23:00:00.000000Z",
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 5.2,
      "pool_size": 10,
      "pool_checked_in": 8
    }
  }
}
```

**Response (Not Ready):**
```json
{
  "status": "not_ready",
  "timestamp": "2025-10-25T23:00:00.000000Z",
  "checks": {
    "database": {
      "status": "unhealthy",
      "latency_ms": 2.1,
      "error": "Connection refused"
    }
  }
}
```

**Status Codes:**
- `200 OK`: Service is ready to accept traffic
- `503 Service Unavailable`: Dependencies are unavailable

**Usage:**
- Kubernetes readiness probe
- Load balancer backend pool decisions

**Kubernetes Configuration:**
```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

**Checks Performed:**
- Database connectivity (always)
- OpenSearch (if configured as critical)
- Storage (if configured as critical)

**Configuration:**
Set critical components via environment variable:
```bash
HEALTH_CHECK_CRITICAL_COMPONENTS="database,opensearch,storage"
```

---

### 4. Detailed Health Check

**Endpoint:** `GET /health/detailed`

**Purpose:** Comprehensive health check of all system components.

**Response (Healthy):**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-25T23:00:00.000000Z",
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 5.2,
      "pool_size": 10,
      "pool_checked_in": 8
    },
    "opensearch": {
      "status": "healthy",
      "latency_ms": 12.5,
      "cluster_status": "green",
      "number_of_nodes": 3
    },
    "storage": {
      "status": "healthy",
      "free_gb": 120.5,
      "total_gb": 500.0,
      "used_gb": 379.5,
      "can_write": true
    },
    "worker": {
      "status": "healthy",
      "jobs_pending": 3,
      "jobs_stuck": 0,
      "last_heartbeat": "2025-10-25T22:59:30.000000Z",
      "seconds_since_heartbeat": 30.5,
      "worker_id": "worker-hostname-12345"
    }
  }
}
```

**Response (Degraded):**
```json
{
  "status": "degraded",
  "timestamp": "2025-10-25T23:00:00.000000Z",
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 5.2
    },
    "opensearch": {
      "status": "degraded",
      "latency_ms": 45.3,
      "cluster_status": "yellow"
    },
    "storage": {
      "status": "healthy",
      "free_gb": 15.2,
      "total_gb": 500.0
    },
    "worker": {
      "status": "degraded",
      "jobs_pending": 150,
      "jobs_stuck": 2,
      "last_heartbeat": "2025-10-25T22:53:30.000000Z",
      "seconds_since_heartbeat": 330.5,
      "error": "Worker heartbeat is stale (330s > 300s)"
    }
  }
}
```

**Response (Unhealthy):**
```json
{
  "status": "unhealthy",
  "timestamp": "2025-10-25T23:00:00.000000Z",
  "checks": {
    "database": {
      "status": "unhealthy",
      "latency_ms": 2.1,
      "error": "Connection refused"
    },
    "opensearch": {
      "status": "disabled"
    },
    "storage": {
      "status": "healthy",
      "free_gb": 120.5
    },
    "worker": {
      "status": "unhealthy",
      "error": "Cannot connect to database"
    }
  }
}
```

**Status Codes:**
- `200 OK`: All components healthy or degraded
- `503 Service Unavailable`: One or more critical components are unhealthy

**Overall Status Logic:**
- `healthy`: All components are healthy
- `degraded`: Some components degraded but none unhealthy
- `unhealthy`: One or more critical components are unhealthy

**Usage:**
- Monitoring dashboards
- Alerting systems
- Troubleshooting
- Status pages

---

## Component Health Checks

### Database

**What it checks:**
- Connection to PostgreSQL database
- Read permissions (`SELECT COUNT(*) FROM jobs`)
- Query latency
- Connection pool status

**Healthy criteria:**
- Can connect and query successfully
- Query completes within timeout

**Response fields:**
- `status`: "healthy" or "unhealthy"
- `latency_ms`: Query latency in milliseconds
- `pool_size`: Total connection pool size
- `pool_checked_in`: Available connections
- `error`: Error message (if unhealthy)

---

### OpenSearch

**What it checks:**
- Cluster health API
- Response time

**Healthy criteria:**
- Cluster status is "green" or "yellow"
- API responds within timeout

**Response fields:**
- `status`: "healthy", "degraded", "unhealthy", or "disabled"
- `latency_ms`: API call latency
- `cluster_status`: "green", "yellow", or "red"
- `number_of_nodes`: Number of nodes in cluster
- `error`: Error message (if unhealthy)

**Note:** Only checked if `SEARCH_BACKEND=opensearch`

---

### Storage

**What it checks:**
- Disk space on `/data` volume
- Write permissions

**Healthy criteria:**
- Free space ≥ `HEALTH_CHECK_DISK_MIN_FREE_GB` (default: 10 GB)
- Can write test file to workdir

**Response fields:**
- `status`: "healthy" or "unhealthy"
- `free_gb`: Free disk space in GB
- `total_gb`: Total disk space in GB
- `used_gb`: Used disk space in GB
- `can_write`: Boolean indicating write permission
- `error`: Error message (if unhealthy)

---

### Worker

**What it checks:**
- Worker heartbeat freshness
- Pending job count
- Stuck job count (jobs in progress states too long)

**Healthy criteria:**
- Heartbeat within last 5 minutes (configurable)
- Worker is actively processing jobs

**Response fields:**
- `status`: "healthy", "degraded", or "unhealthy"
- `jobs_pending`: Number of pending jobs
- `jobs_stuck`: Number of stuck jobs
- `last_heartbeat`: ISO timestamp of last heartbeat
- `seconds_since_heartbeat`: Seconds since last heartbeat
- `worker_id`: Unique worker identifier
- `error`: Error message (if degraded/unhealthy)

**Worker Heartbeat:**
- Workers update `worker_heartbeat` table every 60 seconds
- Stale threshold: 300 seconds (5 minutes) by default
- Worker ID format: `{hostname}-{pid}`

---

## Configuration

### Environment Variables

```bash
# Health check timeout for all checks (seconds)
HEALTH_CHECK_TIMEOUT=5.0

# Worker heartbeat stale threshold (seconds)
HEALTH_CHECK_WORKER_STALE_SECONDS=300

# Minimum free disk space (GB)
HEALTH_CHECK_DISK_MIN_FREE_GB=10.0

# Critical components (comma-separated)
# Only these components cause 503 responses
HEALTH_CHECK_CRITICAL_COMPONENTS="database"

# Work directory for storage checks
WORKDIR="/data"
```

### Default Values

| Setting | Default | Description |
|---------|---------|-------------|
| `HEALTH_CHECK_TIMEOUT` | 5.0 | Maximum time for health checks (seconds) |
| `HEALTH_CHECK_WORKER_STALE_SECONDS` | 300 | Worker heartbeat stale threshold (seconds) |
| `HEALTH_CHECK_DISK_MIN_FREE_GB` | 10.0 | Minimum required free disk space (GB) |
| `HEALTH_CHECK_CRITICAL_COMPONENTS` | "database" | Critical components that cause 503 |
| `WORKDIR` | "/data" | Data directory for storage checks |

---

## Prometheus Metrics

The health check endpoints expose metrics for monitoring:

### `health_check_status`
**Type:** Gauge  
**Labels:** `component`  
**Values:** 1 = healthy, 0 = unhealthy  

```
health_check_status{component="database"} 1
health_check_status{component="opensearch"} 0
health_check_status{component="storage"} 1
health_check_status{component="worker"} 1
```

### `health_check_duration_seconds`
**Type:** Histogram  
**Labels:** `component`  
**Description:** Duration of health checks in seconds

```
health_check_duration_seconds_bucket{component="database",le="0.01"} 45
health_check_duration_seconds_bucket{component="database",le="0.1"} 50
health_check_duration_seconds_sum{component="database"} 2.5
health_check_duration_seconds_count{component="database"} 50
```

### `health_check_total`
**Type:** Counter  
**Labels:** `component`, `status`  
**Description:** Total number of health checks performed

```
health_check_total{component="database",status="healthy"} 1234
health_check_total{component="database",status="unhealthy"} 5
health_check_total{component="worker",status="degraded"} 12
```

---

## Troubleshooting

### Database Unhealthy

**Symptoms:**
- `/ready` returns 503
- Database check shows "Connection refused"

**Possible causes:**
1. PostgreSQL is not running
2. Incorrect DATABASE_URL
3. Network connectivity issues
4. Connection pool exhausted

**Resolution:**
```bash
# Check PostgreSQL status
docker compose ps db

# Check logs
docker compose logs db

# Verify connection
psql $DATABASE_URL -c "SELECT 1"

# Check connection pool
# Look at pool_size and pool_checked_in in health response
```

---

### Worker Degraded

**Symptoms:**
- Worker check shows "Worker heartbeat is stale"
- `seconds_since_heartbeat` > 300

**Possible causes:**
1. Worker process crashed or stopped
2. Worker is stuck processing a job
3. Database connection issues preventing heartbeat updates

**Resolution:**
```bash
# Check worker status
docker compose ps worker

# Check worker logs
docker compose logs worker

# Restart worker
docker compose restart worker

# Check for stuck jobs
psql $DATABASE_URL -c "SELECT * FROM videos WHERE state IN ('downloading', 'transcoding', 'transcribing') AND updated_at < now() - interval '5 minutes'"
```

---

### Storage Unhealthy

**Symptoms:**
- Storage check shows "Low disk space" or "Cannot write to workdir"

**Possible causes:**
1. Disk full or nearly full
2. `/data` volume not mounted
3. Permission issues

**Resolution:**
```bash
# Check disk space
df -h /data

# Check permissions
ls -la /data

# Clean up old files
docker compose exec api bash
cd /data
du -sh *
# Remove old processed videos if CLEANUP_AFTER_PROCESS=false
```

---

### OpenSearch Unhealthy

**Symptoms:**
- OpenSearch check shows cluster_status "red"
- API timeout errors

**Possible causes:**
1. OpenSearch not running
2. Cluster unhealthy
3. Network issues

**Resolution:**
```bash
# Check OpenSearch status
curl -u admin:admin http://localhost:9200/_cluster/health

# Check logs
docker compose logs opensearch

# Restart OpenSearch
docker compose restart opensearch
```

---

## Best Practices

### 1. Monitoring Setup

- Configure Prometheus to scrape `/metrics` endpoint
- Set up alerts for `health_check_status{component="database"} == 0`
- Alert on sustained unhealthy status (not transient failures)

Example Prometheus alert:
```yaml
- alert: DatabaseUnhealthy
  expr: health_check_status{component="database"} == 0
  for: 5m
  annotations:
    summary: "Database health check failing"
```

### 2. Load Balancer Configuration

- Use `/health` for basic health checks
- Set check interval: 10-30 seconds
- Set timeout: 5 seconds
- Set unhealthy threshold: 2-3 consecutive failures

### 3. Kubernetes Configuration

- Use `/live` for liveness probe (restarts dead pods)
- Use `/ready` for readiness probe (removes from service)
- Set appropriate timeouts and thresholds
- Allow enough time for startup (initialDelaySeconds)

### 4. Development vs Production

**Development:**
```bash
# Relax health check requirements
HEALTH_CHECK_CRITICAL_COMPONENTS="database"
HEALTH_CHECK_WORKER_STALE_SECONDS=600
```

**Production:**
```bash
# Strict health checks
HEALTH_CHECK_CRITICAL_COMPONENTS="database,opensearch,storage,worker"
HEALTH_CHECK_WORKER_STALE_SECONDS=300
HEALTH_CHECK_DISK_MIN_FREE_GB=50
```

---

## Testing

### Manual Testing

```bash
# Basic health
curl http://localhost:8000/health

# Liveness
curl http://localhost:8000/live

# Readiness
curl http://localhost:8000/ready

# Detailed health
curl http://localhost:8000/health/detailed | jq
```

### Automated Testing

```bash
# Run health check tests
pytest tests/test_routes_health.py -v

# Run specific test
pytest tests/test_routes_health.py::TestHealthEndpoints::test_health_check_basic -v
```

### Load Testing

```bash
# Test health endpoint performance
ab -n 1000 -c 10 http://localhost:8000/health

# Test detailed health under load
ab -n 100 -c 5 http://localhost:8000/health/detailed
```

---

## Success Criteria

✅ Health checks respond in < 5 seconds  
✅ Accurate status reporting for all components  
✅ Integrated with Prometheus monitoring  
✅ Works with Kubernetes liveness/readiness probes  
✅ Configurable critical components  
✅ Worker heartbeat mechanism active  
✅ Comprehensive test coverage (25 tests)  

---

## API Reference

See the interactive API documentation at `/docs` for complete request/response schemas and examples.

---

## Related Documentation

- [Prometheus Metrics](./IMPLEMENTATION_SUMMARY_MONITORING.md)
- [Kubernetes Deployment Guide](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Production Deployment](./docs/deployment.md)
