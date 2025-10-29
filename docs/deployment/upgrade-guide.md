# Upgrade Guide

Guide for upgrading transcript-create to newer versions with zero-downtime strategies and rollback procedures.

## Table of Contents

1. [Pre-Upgrade Checklist](#pre-upgrade-checklist)
2. [Upgrade Strategies](#upgrade-strategies)
3. [Docker Compose Upgrades](#docker-compose-upgrades)
4. [Kubernetes Upgrades](#kubernetes-upgrades)
5. [Database Migrations](#database-migrations)
6. [Rollback Procedures](#rollback-procedures)
7. [Version-Specific Notes](#version-specific-notes)

## Pre-Upgrade Checklist

Before upgrading, complete these steps:

- [ ] Review [CHANGELOG](../../CHANGELOG.md) for breaking changes
- [ ] Check database migration compatibility
- [ ] Create full backup (database + media files)
- [ ] Test upgrade in staging environment
- [ ] Schedule maintenance window (if downtime required)
- [ ] Notify users of planned upgrade
- [ ] Verify rollback plan
- [ ] Document current version and configuration
- [ ] Check disk space (migrations may require temporary space)

### Create Backup

```bash
# Docker Compose
docker compose exec backup /scripts/backup_db.sh
docker compose exec backup /scripts/backup_media.sh

# Kubernetes
kubectl exec -n transcript-create deployment/transcript-api -- \
  python /app/scripts/backup_db.py

# Verify backup
ls -lh /backups/db/
```

### Check Current Version

```bash
# Docker Compose
docker exec transcript-api python -c "import app; print(app.__version__)"

# Kubernetes
kubectl exec -n transcript-create deployment/transcript-api -- \
  python -c "import app; print(app.__version__)"

# Or check image tag
docker images | grep transcript-create
kubectl get deployment transcript-api -n transcript-create -o jsonpath='{.spec.template.spec.containers[0].image}'
```

## Upgrade Strategies

### Strategy Comparison

| Strategy | Downtime | Complexity | Best For | Risk |
|----------|----------|------------|----------|------|
| Blue-Green | None | Medium | Production | Low |
| Rolling Update | None | Low | K8s deployments | Low |
| Recreate | Yes (5-15 min) | Low | Simple setups | Medium |
| Canary | None | High | Large deployments | Very Low |

### Zero-Downtime Requirements

For zero-downtime upgrades, ensure:
- Database migrations are backward compatible
- Multiple API replicas running (minimum 3)
- Health checks configured
- Pod Disruption Budgets in place (K8s)
- Load balancer with health checking

## Docker Compose Upgrades

### Standard Upgrade (Brief Downtime)

```bash
# 1. Stop services
docker compose down

# 2. Backup current data
./scripts/backup_db.sh
./scripts/backup_media.sh

# 3. Pull latest code
git fetch origin
git checkout v1.2.0  # Replace with target version

# 4. Rebuild images
docker compose build

# 5. Run database migrations
docker compose run --rm migrations

# 6. Start services
docker compose up -d

# 7. Verify
docker compose ps
curl http://localhost:8000/health
docker compose logs -f api worker
```

### Rolling Upgrade (Zero Downtime)

Requires multiple API instances:

```bash
# 1. Scale up API instances
docker compose up -d --scale api=6 --no-recreate

# 2. Pull new code and rebuild
git checkout v1.2.0
docker compose build

# 3. Run migrations (if any)
docker compose run --rm migrations

# 4. Update API instances one by one
docker compose up -d --no-deps --scale api=6 api
sleep 30  # Wait for new instances to be healthy

# 5. Scale back to normal
docker compose up -d --scale api=3

# 6. Update worker
docker compose up -d --no-deps worker

# 7. Verify
curl http://localhost:8000/health
```

### Using Watchtower (Automatic)

If watchtower is enabled in docker-compose.prod.yml:

```bash
# Watchtower will automatically update containers with label
# com.centurylinklabs.watchtower.enable=true

# Push new image to registry
docker tag transcript-create:latest your-registry/transcript-create:v1.2.0
docker push your-registry/transcript-create:v1.2.0

# Watchtower checks every 24 hours by default
# Or trigger manual update:
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --run-once \
  --cleanup \
  transcript-api transcript-worker
```

## Kubernetes Upgrades

### Helm Upgrade (Recommended)

```bash
# 1. Review changes
helm diff upgrade transcript-create ./charts/transcript-create \
  -f production-values.yaml \
  --namespace transcript-create

# 2. Run upgrade
helm upgrade transcript-create ./charts/transcript-create \
  -f production-values.yaml \
  --namespace transcript-create \
  --set image.tag=1.2.0 \
  --wait \
  --timeout=10m

# 3. Monitor rollout
kubectl rollout status deployment/transcript-api -n transcript-create
kubectl rollout status deployment/transcript-worker -n transcript-create

# 4. Verify
kubectl get pods -n transcript-create
kubectl logs -f deployment/transcript-api -n transcript-create --tail=50
curl https://api.example.com/health
```

### kubectl Rolling Update

```bash
# 1. Update image tag in deployment files
sed -i 's/transcript-create:v1.1.0/transcript-create:v1.2.0/' k8s/api-deployment.yaml
sed -i 's/transcript-create:v1.1.0/transcript-create:v1.2.0/' k8s/worker-deployment.yaml

# 2. Apply migrations (if any)
kubectl apply -f k8s/migrations-job.yaml -n transcript-create
kubectl wait --for=condition=complete job/transcript-migrations -n transcript-create --timeout=300s

# 3. Update deployments
kubectl apply -f k8s/api-deployment.yaml -n transcript-create
kubectl apply -f k8s/worker-deployment.yaml -n transcript-create

# 4. Monitor rollout
kubectl rollout status deployment/transcript-api -n transcript-create -w

# 5. Verify new pods
kubectl get pods -n transcript-create -l app=transcript-api -o wide
```

### Blue-Green Deployment

```bash
# 1. Create "green" deployment with new version
cat > green-deployment.yaml <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: transcript-api-green
  namespace: transcript-create
spec:
  replicas: 3
  selector:
    matchLabels:
      app: transcript-api
      version: green
  template:
    metadata:
      labels:
        app: transcript-api
        version: green
    spec:
      containers:
      - name: api
        image: transcript-create:v1.2.0
        # ... rest of spec from api-deployment.yaml
EOF

kubectl apply -f green-deployment.yaml

# 2. Wait for green deployment to be ready
kubectl rollout status deployment/transcript-api-green -n transcript-create

# 3. Test green deployment
kubectl port-forward deployment/transcript-api-green 8001:8000 -n transcript-create &
curl http://localhost:8001/health

# 4. Switch service to green
kubectl patch service transcript-api -n transcript-create \
  -p '{"spec":{"selector":{"version":"green"}}}'

# 5. Monitor for issues
# If OK, delete blue deployment:
kubectl delete deployment transcript-api -n transcript-create

# If issues, revert:
kubectl patch service transcript-api -n transcript-create \
  -p '{"spec":{"selector":{"version":"blue"}}}'
```

### Canary Deployment

```bash
# 1. Deploy canary with 10% traffic
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: transcript-api-canary
  namespace: transcript-create
spec:
  replicas: 1  # 10% of production (3 replicas stable + 1 canary)
  selector:
    matchLabels:
      app: transcript-api
      track: canary
  template:
    metadata:
      labels:
        app: transcript-api
        track: canary
    spec:
      containers:
      - name: api
        image: transcript-create:v1.2.0
        # ... same spec as production
EOF

# 2. Monitor canary metrics
kubectl logs -f deployment/transcript-api-canary -n transcript-create
# Check error rates, latency, etc.

# 3. Gradually increase canary traffic
kubectl scale deployment transcript-api-canary -n transcript-create --replicas=2

# 4. If successful, promote canary to production
kubectl set image deployment/transcript-api api=transcript-create:v1.2.0 -n transcript-create
kubectl delete deployment transcript-api-canary -n transcript-create

# If issues, delete canary
kubectl delete deployment transcript-api-canary -n transcript-create
```

## Database Migrations

### Check Migration Status

```bash
# Docker Compose
docker compose exec api alembic current
docker compose exec api alembic history

# Kubernetes
kubectl exec -n transcript-create deployment/transcript-api -- alembic current
kubectl exec -n transcript-create deployment/transcript-api -- alembic history
```

### Run Migrations

```bash
# Docker Compose
docker compose run --rm migrations

# Kubernetes
kubectl apply -f k8s/migrations-job.yaml -n transcript-create
kubectl wait --for=condition=complete job/transcript-migrations -n transcript-create --timeout=300s
kubectl logs job/transcript-migrations -n transcript-create

# Manual execution
kubectl exec -it deployment/transcript-api -n transcript-create -- alembic upgrade head
```

### Migration Best Practices

1. **Test migrations** in staging first
2. **Backup before migrations** (automatic in jobs)
3. **Monitor migration progress** - large tables may take time
4. **Use online schema changes** for large tables (via pt-online-schema-change or similar)
5. **Keep migrations backward compatible** during zero-downtime upgrades

### Backward Compatible Migrations

For zero-downtime:

**Step 1: Add new column (nullable)**
```python
# Migration 1: Add column
def upgrade():
    op.add_column('videos', sa.Column('new_field', sa.String(), nullable=True))

# Deploy this migration with old code still running
```

**Step 2: Deploy code using new column**
```python
# Code now writes to both old and new fields
video.old_field = value
video.new_field = value
```

**Step 3: Backfill data**
```python
# Migration 2: Backfill
def upgrade():
    op.execute("UPDATE videos SET new_field = old_field WHERE new_field IS NULL")
```

**Step 4: Make column non-nullable**
```python
# Migration 3: Add constraint
def upgrade():
    op.alter_column('videos', 'new_field', nullable=False)
```

**Step 5: Remove old column**
```python
# Migration 4: Drop old column
def upgrade():
    op.drop_column('videos', 'old_field')
```

## Rollback Procedures

### Docker Compose Rollback

```bash
# 1. Stop current version
docker compose down

# 2. Revert to previous version
git checkout v1.1.0

# 3. Restore database if needed
docker compose up -d db
./scripts/restore_db.sh /backups/db/backup-pre-upgrade.sql.gz

# 4. Rebuild and start
docker compose build
docker compose up -d

# 5. Verify
curl http://localhost:8000/health
```

### Kubernetes Rollback

#### Helm Rollback

```bash
# Check revision history
helm history transcript-create -n transcript-create

# Rollback to previous version
helm rollback transcript-create -n transcript-create

# Rollback to specific revision
helm rollback transcript-create 2 -n transcript-create

# Verify
kubectl get pods -n transcript-create -w
```

#### kubectl Rollback

```bash
# Check rollout history
kubectl rollout history deployment/transcript-api -n transcript-create

# Rollback to previous version
kubectl rollout undo deployment/transcript-api -n transcript-create
kubectl rollout undo deployment/transcript-worker -n transcript-create

# Rollback to specific revision
kubectl rollout undo deployment/transcript-api --to-revision=2 -n transcript-create

# Monitor rollback
kubectl rollout status deployment/transcript-api -n transcript-create
```

### Database Rollback

```bash
# Rollback to specific migration
docker compose exec api alembic downgrade -1  # Down one version
docker compose exec api alembic downgrade abc123  # To specific version

# Or restore from backup
./scripts/restore_db.sh /backups/db/backup-pre-upgrade.sql.gz

# For Kubernetes
kubectl exec -it deployment/transcript-api -n transcript-create -- \
  alembic downgrade -1
```

### Emergency Rollback

If systems are down:

```bash
# 1. Immediate rollback (no health checks)
kubectl set image deployment/transcript-api \
  api=transcript-create:v1.1.0 \
  -n transcript-create

kubectl set image deployment/transcript-worker \
  worker=transcript-create:v1.1.0 \
  -n transcript-create

# 2. Delete bad pods immediately
kubectl delete pod -n transcript-create -l app=transcript-api
kubectl delete pod -n transcript-create -l app=transcript-worker

# 3. Scale up if needed
kubectl scale deployment transcript-api -n transcript-create --replicas=5

# 4. Restore database if corrupted
kubectl exec -it deployment/transcript-api -n transcript-create -- \
  bash -c "psql \$DATABASE_URL < /backups/db/latest.sql"
```

## Version-Specific Notes

### Upgrading to v1.2.0 (Example)

**Breaking Changes:**
- Environment variable `WHISPER_BACKEND` default changed to `faster-whisper`
- Database: Added `segments.confidence` column

**Migration Steps:**
```bash
# 1. Update environment variables
echo "WHISPER_BACKEND=faster-whisper" >> .env

# 2. Run migrations (adds confidence column)
docker compose run --rm migrations

# 3. Rebuild with new dependencies
docker compose build

# 4. Deploy
docker compose up -d
```

### Upgrading to v2.0.0 (Major Version)

**Breaking Changes:**
- API endpoint changes (see API migration guide)
- Database schema restructure
- Configuration format changes

**Migration Steps:**
```bash
# 1. Run migration tool
docker compose run --rm api python scripts/migrate_v1_to_v2.py

# 2. Update configuration
cp .env .env.v1.backup
./scripts/convert_env_v2.sh .env.v1.backup > .env

# 3. Full database backup
docker compose exec backup /scripts/backup_db.sh

# 4. Test in staging
# ... verify everything works

# 5. Production upgrade
docker compose down
git checkout v2.0.0
docker compose build
docker compose up -d
```

## Monitoring During Upgrade

### Key Metrics to Watch

```bash
# API health
watch -n 5 'curl -s http://localhost:8000/health | jq'

# Pod status (K8s)
watch -n 5 'kubectl get pods -n transcript-create'

# Error logs
docker compose logs -f api | grep -i error
kubectl logs -f deployment/transcript-api -n transcript-create | grep -i error

# Database connections
docker exec transcript-db psql -U postgres -c \
  "SELECT count(*) as active_connections FROM pg_stat_activity WHERE state = 'active';"

# Response times
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/api/jobs
```

**curl-format.txt:**
```
time_namelookup:  %{time_namelookup}\n
time_connect:  %{time_connect}\n
time_starttransfer:  %{time_starttransfer}\n
time_total:  %{time_total}\n
```

### Automated Health Checks

```bash
#!/bin/bash
# post-upgrade-check.sh

echo "Running post-upgrade health checks..."

# API health
if curl -sf http://localhost:8000/health > /dev/null; then
  echo "✓ API health check passed"
else
  echo "✗ API health check FAILED"
  exit 1
fi

# Database connectivity
if docker exec transcript-api python -c "from app.db import engine; engine.connect()" 2>/dev/null; then
  echo "✓ Database connection OK"
else
  echo "✗ Database connection FAILED"
  exit 1
fi

# GPU availability (if applicable)
if docker exec transcript-worker nvidia-smi > /dev/null 2>&1 || \
   docker exec transcript-worker rocm-smi > /dev/null 2>&1; then
  echo "✓ GPU detected"
else
  echo "⚠ Warning: GPU not detected"
fi

# Submit test job
JOB_ID=$(curl -sf -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}' \
  | jq -r '.id')

if [ -n "$JOB_ID" ] && [ "$JOB_ID" != "null" ]; then
  echo "✓ Test job submitted: $JOB_ID"
else
  echo "✗ Test job submission FAILED"
  exit 1
fi

echo "All health checks passed!"
```

## Post-Upgrade Tasks

After successful upgrade:

- [ ] Verify all services are running
- [ ] Check logs for errors
- [ ] Submit test job and verify processing
- [ ] Verify search functionality
- [ ] Test user authentication
- [ ] Check monitoring dashboards
- [ ] Verify backups are working
- [ ] Update documentation with new version
- [ ] Notify users of successful upgrade
- [ ] Monitor for 24 hours for issues

## Troubleshooting Upgrades

See [Troubleshooting Guide](./troubleshooting.md) for common issues.

### Common Upgrade Issues

**Migration fails:**
- Check database connectivity
- Verify user permissions
- Check for conflicting constraints
- Review migration logs

**Pods won't start (K8s):**
- Check image pull errors
- Verify secrets are accessible
- Review resource limits
- Check liveness/readiness probes

**Performance degradation:**
- Check new resource requirements
- Verify database indexes
- Review configuration changes
- Check for breaking changes

## Support

For upgrade assistance:
- GitHub Issues: [github.com/subculture-collective/transcript-create/issues](https://github.com/subculture-collective/transcript-create/issues)
- Documentation: [docs/](../../docs/)
- Changelog: [CHANGELOG.md](../../CHANGELOG.md)
