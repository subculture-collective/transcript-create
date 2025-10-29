# Troubleshooting Deployment Issues

Common deployment issues and their solutions for transcript-create.

## Table of Contents

1. [General Issues](#general-issues)
2. [Database Problems](#database-problems)
3. [GPU Issues](#gpu-issues)
4. [Storage Problems](#storage-problems)
5. [Network and Connectivity](#network-and-connectivity)
6. [Performance Issues](#performance-issues)
7. [Security and Authentication](#security-and-authentication)
8. [Kubernetes-Specific](#kubernetes-specific)
9. [Cloud Provider Issues](#cloud-provider-issues)

## General Issues

### Application Won't Start

**Symptoms:** Container exits immediately or enters CrashLoopBackOff

**Diagnosis:**
```bash
# Check logs
docker logs transcript-api
# or
kubectl logs -f deployment/transcript-api -n transcript-create

# Check environment variables
docker inspect transcript-api | grep -A 20 Env
kubectl describe pod <pod-name> -n transcript-create
```

**Common Causes:**
1. Missing required environment variables
2. Invalid DATABASE_URL format
3. Database not accessible
4. Missing secrets

**Solutions:**
```bash
# Verify required environment variables are set
grep -E "(DATABASE_URL|SESSION_SECRET|ENVIRONMENT)" .env

# Test database connection
docker exec -it transcript-api python -c "from app.db import engine; engine.connect(); print('OK')"

# Regenerate SESSION_SECRET if invalid
openssl rand -hex 32
```

### Migrations Fail

**Symptoms:** "relation does not exist" errors, schema version mismatch

**Diagnosis:**
```bash
# Check current migration version
docker exec transcript-api alembic current

# Check migration history
docker exec transcript-api alembic history
```

**Solutions:**
```bash
# Run pending migrations
docker exec transcript-api alembic upgrade head

# If stuck, check database directly
docker exec -it transcript-db psql -U postgres -d transcripts
# \dt  -- list tables
# SELECT * FROM alembic_version;

# Nuclear option: reset migrations (⚠️ destroys data)
docker exec transcript-api alembic downgrade base
docker exec transcript-api alembic upgrade head
```

## Database Problems

### Connection Refused

**Symptoms:** "Connection refused", "could not connect to server"

**Diagnosis:**
```bash
# Test network connectivity
docker exec transcript-api ping -c 3 db
# or for K8s
kubectl exec -it <api-pod> -n transcript-create -- ping postgres-service

# Check if database is running
docker ps | grep postgres
kubectl get pods -n transcript-create | grep postgres
```

**Solutions:**
```bash
# Verify DATABASE_URL format
# Correct: postgresql+psycopg://user:pass@host:5432/dbname
# Wrong: postgresql://... (missing +psycopg)

# Check database service is healthy
docker compose ps db
kubectl describe pod postgres-0 -n transcript-create

# For K8s, verify service DNS
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup postgres-service
```

### Too Many Connections

**Symptoms:** "FATAL: remaining connection slots are reserved"

**Diagnosis:**
```bash
# Check current connections
docker exec transcript-db psql -U postgres -c \
  "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"

# Check max_connections setting
docker exec transcript-db psql -U postgres -c "SHOW max_connections;"
```

**Solutions:**
```bash
# Increase max_connections (requires restart)
# Edit docker-compose.yml or PostgreSQL config:
# command: -c max_connections=200

# Or use connection pooling (recommended)
# Add PgBouncer as a sidecar

# Temporary: kill idle connections
docker exec transcript-db psql -U postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND state_change < NOW() - INTERVAL '10 minutes';"
```

### Slow Queries

**Symptoms:** High database CPU, slow API responses

**Diagnosis:**
```bash
# Enable slow query logging
docker exec transcript-db psql -U postgres -c \
  "ALTER SYSTEM SET log_min_duration_statement = 1000;"  # Log queries > 1s

# Check slow queries
docker exec transcript-db psql -U postgres -c \
  "SELECT query, calls, total_time, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# Check missing indexes
docker exec transcript-db psql -U postgres -d transcripts -f - <<'SQL'
SELECT schemaname, tablename, attname, n_distinct, correlation
FROM pg_stats
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY abs(correlation) DESC;
SQL
```

**Solutions:**
```bash
# Run VACUUM ANALYZE
docker exec transcript-db psql -U postgres -d transcripts -c "VACUUM ANALYZE;"

# Check for missing indexes (app should create these)
# jobs(status), videos(youtube_id), segments(transcript_id)

# Increase shared_buffers and effective_cache_size
# In PostgreSQL config
```

## GPU Issues

### GPU Not Detected

**Symptoms:** Worker logs show "GPU not available", falling back to CPU

**Diagnosis:**
```bash
# Check GPU visibility on host
rocm-smi  # AMD
nvidia-smi  # NVIDIA

# Check GPU in container
docker exec transcript-worker rocm-smi
docker exec transcript-worker nvidia-smi

# For K8s
kubectl exec -it <worker-pod> -n transcript-create -- rocm-smi
kubectl describe node <gpu-node> | grep -A 5 "Allocatable"
```

**Solutions:**

**Docker:**
```bash
# Ensure devices are mounted (AMD ROCm)
# In docker-compose.yml:
services:
  worker:
    devices:
      - /dev/kfd:/dev/kfd
      - /dev/dri:/dev/dri
    group_add:
      - video

# For NVIDIA, ensure nvidia runtime is used
docker run --gpus all --rm nvidia/cuda:12.0-base nvidia-smi
```

**Kubernetes:**
```bash
# Check GPU device plugin
kubectl get pods -n kube-system | grep -E "(nvidia|amd)"

# For NVIDIA, install device plugin
kubectl create -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.0/nvidia-device-plugin.yml

# For AMD, install device plugin
kubectl apply -f https://raw.githubusercontent.com/RadeonOpenCompute/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml

# Verify GPU resources
kubectl describe node <gpu-node> | grep -E "(nvidia.com/gpu|amd.com/gpu)"
```

### Out of GPU Memory

**Symptoms:** "CUDA out of memory", "ROCm out of memory", worker crashes

**Diagnosis:**
```bash
# Check GPU memory usage
rocm-smi | grep -A 3 "Memory Usage"
nvidia-smi --query-gpu=memory.used,memory.total --format=csv

# Check WHISPER_MODEL size
# large-v3: ~6GB VRAM, medium: ~3GB, small: ~1GB
```

**Solutions:**
```bash
# Use smaller model in .env
WHISPER_MODEL=medium  # or small

# Reduce chunk size
CHUNK_SECONDS=600  # from 900

# Use CPU fallback
FORCE_GPU=false

# Ensure only one worker per GPU
# In K8s deployment:
resources:
  limits:
    nvidia.com/gpu: 1  # or amd.com/gpu: 1
```

### GPU Driver Version Mismatch

**Symptoms:** "unsupported GPU architecture", "driver version mismatch"

**Solutions:**
```bash
# Check host driver version
rocm-smi --showdriverversion
nvidia-smi | grep "Driver Version"

# Match Docker image ROCm version to host
# In docker-compose.yml build args:
build:
  args:
    ROCM_WHEEL_INDEX: https://download.pytorch.org/whl/rocm6.1  # Match your ROCm version

# For NVIDIA, ensure compatible CUDA version
# T4 GPU: CUDA 11.x or 12.x
# V100: CUDA 11.x recommended
```

## Storage Problems

### Disk Full

**Symptoms:** "No space left on device", write errors

**Diagnosis:**
```bash
# Check disk usage
df -h
docker system df  # Docker-specific

# For K8s
kubectl exec -it <pod> -n transcript-create -- df -h
kubectl describe pvc -n transcript-create
```

**Solutions:**
```bash
# Clean up Docker
docker system prune -a --volumes

# Clean up old media files
find /data -type f -mtime +30 -delete

# Increase PVC size (K8s)
kubectl patch pvc transcript-data -n transcript-create \
  -p '{"spec":{"resources":{"requests":{"storage":"1Ti"}}}}'

# Enable cleanup settings
CLEANUP_AFTER_PROCESS=true
CLEANUP_DELETE_RAW=true
CLEANUP_DELETE_CHUNKS=true
```

### Permission Denied

**Symptoms:** "Permission denied" when writing to /data

**Diagnosis:**
```bash
# Check ownership
docker exec transcript-worker ls -la /data

# For K8s
kubectl exec <worker-pod> -n transcript-create -- ls -la /data
```

**Solutions:**
```bash
# Fix ownership on host
sudo chown -R 1000:1000 /path/to/data

# For K8s with NFS/EFS, set proper permissions
# In PVC or StorageClass, add:
mountOptions:
  - uid=1000
  - gid=1000
  - dir_mode=0777
  - file_mode=0777
```

## Network and Connectivity

### API Not Accessible

**Symptoms:** "Connection refused", 502 Bad Gateway, timeout

**Diagnosis:**
```bash
# Check if API is running
curl http://localhost:8000/health

# Check API logs
docker logs transcript-api --tail 50

# For K8s
kubectl get svc -n transcript-create
kubectl get ingress -n transcript-create
kubectl describe ingress transcript-ingress -n transcript-create
```

**Solutions:**
```bash
# Verify port mapping (Docker)
docker ps | grep transcript-api
# Should show: 0.0.0.0:8000->8000/tcp

# For K8s, check service
kubectl port-forward svc/transcript-api 8000:8000 -n transcript-create
curl http://localhost:8000/health

# Check ingress controller
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx

# Verify DNS
nslookup api.example.com
```

### SSL Certificate Issues

**Symptoms:** "certificate not trusted", "ERR_CERT_AUTHORITY_INVALID"

**Diagnosis:**
```bash
# Check certificate
echo | openssl s_client -servername api.example.com -connect api.example.com:443 2>/dev/null | openssl x509 -noout -dates

# For K8s with cert-manager
kubectl get certificate -n transcript-create
kubectl describe certificate transcript-tls -n transcript-create
```

**Solutions:**
```bash
# For Caddy, check logs
docker logs caddy

# For cert-manager, check certificate order
kubectl get certificaterequest -n transcript-create
kubectl describe certificaterequest <request-name> -n transcript-create

# Manual renewal (Let's Encrypt)
certbot renew --force-renewal

# Verify DNS is correct (required for ACME challenge)
dig api.example.com +short
```

### CORS Errors

**Symptoms:** "blocked by CORS policy" in browser console

**Diagnosis:**
```bash
# Check CORS headers
curl -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
  -X OPTIONS \
  -v https://api.example.com/api/jobs
```

**Solutions:**
```bash
# Update FRONTEND_ORIGIN in .env
FRONTEND_ORIGIN=https://app.example.com

# Add additional origins if needed
CORS_ALLOW_ORIGINS=https://app.example.com,https://admin.example.com

# Restart API
docker restart transcript-api
kubectl rollout restart deployment/transcript-api -n transcript-create
```

## Performance Issues

### Slow Transcription

**Symptoms:** Videos take much longer than expected to transcribe

**Diagnosis:**
```bash
# Check if GPU is being used
docker exec transcript-worker python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"

# Check GPU utilization
watch -n 1 nvidia-smi
watch -n 1 rocm-smi

# Check logs for fallback messages
docker logs transcript-worker | grep -i "falling back\|cpu"
```

**Solutions:**
```bash
# Ensure GPU is enabled
FORCE_GPU=true
WHISPER_BACKEND=faster-whisper  # Faster than 'whisper'

# Use appropriate quality preset
WHISPER_QUALITY_PRESET=fast  # or balanced

# Reduce chunk size for faster iteration
CHUNK_SECONDS=600

# Disable VAD filter if causing slowdowns
WHISPER_VAD_FILTER=false
```

### High Memory Usage

**Symptoms:** OOM kills, slow performance, swap usage

**Diagnosis:**
```bash
# Check memory usage
docker stats

# For K8s
kubectl top pods -n transcript-create
kubectl top nodes
```

**Solutions:**
```bash
# Set resource limits (K8s)
resources:
  limits:
    memory: 16Gi
  requests:
    memory: 8Gi

# Reduce worker parallelism
MAX_PARALLEL_JOBS=1

# Use smaller Whisper model
WHISPER_MODEL=medium  # or small

# Increase chunk size (fewer concurrent chunks)
CHUNK_SECONDS=1200
```

## Security and Authentication

### OAuth Login Fails

**Symptoms:** "OAuth error", "invalid redirect_uri", "access denied"

**Diagnosis:**
```bash
# Check OAuth configuration
echo $OAUTH_GOOGLE_CLIENT_ID
echo $OAUTH_GOOGLE_REDIRECT_URI

# Check logs
docker logs transcript-api | grep -i oauth
```

**Solutions:**
```bash
# Verify redirect URI matches OAuth provider settings
# Google: https://console.cloud.google.com/apis/credentials
# Twitch: https://dev.twitch.tv/console/apps

# Correct format
OAUTH_GOOGLE_REDIRECT_URI=https://api.example.com/auth/callback/google

# Ensure HTTPS for production
# OAuth providers often require HTTPS for redirects

# Check state validation
OAUTH_STATE_VALIDATION=true
```

### Session Issues

**Symptoms:** "Session expired", "invalid session", frequent logouts

**Diagnosis:**
```bash
# Check SESSION_SECRET is set and consistent
echo $SESSION_SECRET | wc -c  # Should be 64 characters (32 bytes hex)

# Check Redis connectivity
docker exec transcript-api python -c "
from redis import Redis
r = Redis.from_url('$REDIS_URL')
r.ping()
print('Redis OK')
"
```

**Solutions:**
```bash
# Generate new SESSION_SECRET
SESSION_SECRET=$(openssl rand -hex 32)

# Increase session expiration
SESSION_EXPIRE_HOURS=24
SESSION_REFRESH_THRESHOLD_HOURS=12

# Ensure Redis is running
docker ps | grep redis
kubectl get pods -n transcript-create | grep redis

# Check Redis memory
docker exec redis redis-cli INFO memory
```

## Kubernetes-Specific

### Pods in CrashLoopBackOff

**Diagnosis:**
```bash
kubectl describe pod <pod-name> -n transcript-create
kubectl logs <pod-name> -n transcript-create --previous
```

**Solutions:**
```bash
# Check liveness/readiness probes
kubectl get pod <pod-name> -n transcript-create -o yaml | grep -A 10 livenessProbe

# Increase startup time
# In deployment:
startupProbe:
  initialDelaySeconds: 60
  periodSeconds: 10
  failureThreshold: 10
```

### PVC Won't Bind

**Symptoms:** PVC stuck in "Pending" state

**Diagnosis:**
```bash
kubectl describe pvc transcript-data -n transcript-create
kubectl get storageclass
```

**Solutions:**
```bash
# Check if StorageClass exists
kubectl get sc

# Create StorageClass if missing
# Or update PVC to use existing StorageClass

# For ReadWriteMany, ensure storage supports it
# AWS: Use EFS CSI driver
# GCP: Use Filestore
# Azure: Use Azure Files
```

### Ingress Not Working

**Diagnosis:**
```bash
kubectl describe ingress transcript-ingress -n transcript-create
kubectl get svc -n ingress-nginx
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx
```

**Solutions:**
```bash
# Check ingress controller is installed
kubectl get pods -n ingress-nginx

# Verify ingress class
kubectl get ingressclass

# Check service backend
kubectl get svc transcript-api -n transcript-create
kubectl get endpoints transcript-api -n transcript-create
```

## Cloud Provider Issues

### AWS ECS Task Failures

**Diagnosis:**
```bash
aws ecs describe-tasks --cluster transcript-prod --tasks <task-id>
aws logs tail /ecs/transcript-api --follow
```

**Solutions:**
```bash
# Check IAM permissions
# Task execution role needs ECR, Secrets Manager access

# Increase memory/CPU
# In task definition

# Check security groups
# Allow traffic from ALB to ECS tasks
```

### GCP Cloud SQL Connection

**Diagnosis:**
```bash
kubectl logs <pod-name> -n transcript-create -c cloudsql-proxy
gcloud sql instances describe transcript-db
```

**Solutions:**
```bash
# Verify Cloud SQL Proxy is running
# Check Workload Identity bindings
# Ensure private IP is configured
```

## Getting Help

If issues persist:

1. **Check logs thoroughly**: Most issues are revealed in logs
2. **Verify configuration**: Double-check environment variables
3. **Test components individually**: Database, Redis, GPU, etc.
4. **Search GitHub Issues**: [github.com/subculture-collective/transcript-create/issues](https://github.com/subculture-collective/transcript-create/issues)
5. **Ask for help**: Create a new issue with:
   - Deployment method (Docker Compose, K8s, cloud provider)
   - Full error messages and logs
   - Configuration (with secrets redacted)
   - Steps to reproduce

## Diagnostic Script

```bash
#!/bin/bash
# Save as diagnose.sh and run to collect diagnostic info

echo "=== System Info ==="
uname -a
docker --version
kubectl version --client 2>/dev/null || echo "kubectl not installed"

echo -e "\n=== Docker Services ==="
docker ps

echo -e "\n=== Docker Logs (last 50 lines) ==="
docker logs transcript-api --tail 50 2>&1
docker logs transcript-worker --tail 50 2>&1

echo -e "\n=== GPU Status ==="
nvidia-smi 2>/dev/null || rocm-smi 2>/dev/null || echo "No GPU detected"

echo -e "\n=== Disk Usage ==="
df -h

echo -e "\n=== Network ==="
curl -s http://localhost:8000/health || echo "API not accessible"

echo -e "\n=== Database Connection ==="
docker exec transcript-api python -c "from app.db import engine; engine.connect(); print('DB OK')" 2>&1

echo -e "\n=== Kubernetes Pods (if applicable) ==="
kubectl get pods -n transcript-create 2>/dev/null

echo -e "\n=== Kubernetes Events (if applicable) ==="
kubectl get events -n transcript-create --sort-by='.lastTimestamp' 2>/dev/null | tail -20
```

## Related Documentation

- [Production Checklist](./production-checklist.md)
- [Upgrade Guide](./upgrade-guide.md)
- [Kubernetes Guide](./kubernetes.md)
- [Docker Compose Guide](./docker-compose.md)
