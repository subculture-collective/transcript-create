# Production Deployment Checklist

This checklist ensures your transcript-create deployment is production-ready with proper security, reliability, and monitoring.

## Pre-Deployment

### Infrastructure
- [ ] Kubernetes cluster or Docker host provisioned
- [ ] GPU nodes configured (AMD ROCm or NVIDIA CUDA)
- [ ] GPU drivers installed and verified (`rocm-smi` or `nvidia-smi`)
- [ ] Storage provisioner configured (ReadWriteMany for K8s)
- [ ] Network policies and firewall rules configured
- [ ] DNS records created and propagated
- [ ] Load balancer or ingress controller deployed

### Database
- [ ] PostgreSQL 16+ database provisioned
- [ ] Database migrations applied (`alembic upgrade head`)
- [ ] Database user with appropriate permissions created
- [ ] Connection pooling configured (recommended: pgbouncer)
- [ ] Database backups scheduled (daily minimum)
- [ ] WAL archiving enabled for point-in-time recovery
- [ ] Database monitoring enabled

### Storage
- [ ] Persistent volumes provisioned for `/data` (media files)
- [ ] Cache volume provisioned for `/root/.cache` (model weights)
- [ ] Storage quotas set and monitored
- [ ] Backup storage configured (S3, GCS, Azure Blob)
- [ ] Media backup schedule configured
- [ ] Backup retention policies set

### Secrets Management
- [ ] `SESSION_SECRET` generated with `openssl rand -hex 32`
- [ ] Database credentials stored securely
- [ ] OAuth credentials configured (Google, Twitch)
- [ ] Stripe API keys configured (use test keys for staging)
- [ ] HuggingFace token set (for speaker diarization)
- [ ] Secrets stored in proper secret manager (Vault, K8s Secrets, AWS Secrets Manager)
- [ ] Secrets encrypted at rest
- [ ] Secret rotation policy defined

## Security Configuration

### SSL/TLS
- [ ] SSL certificates obtained (Let's Encrypt or commercial)
- [ ] Certificate auto-renewal configured (cert-manager or certbot)
- [ ] TLS 1.2+ enforced
- [ ] HTTPS redirect configured
- [ ] Certificate expiry monitoring enabled
- [ ] HSTS headers configured

### Authentication
- [ ] OAuth providers configured and tested
- [ ] Admin emails configured in `ADMIN_EMAILS`
- [ ] API key expiration policy set (`API_KEY_EXPIRE_DAYS`)
- [ ] Session expiration configured (`SESSION_EXPIRE_HOURS`)
- [ ] Rate limiting enabled (`ENABLE_RATE_LIMITING=true`)
- [ ] Failed login attempt limits configured

### Network Security
- [ ] Firewall rules applied (allow only necessary ports)
- [ ] Network policies configured (K8s)
- [ ] CORS origins properly configured (`FRONTEND_ORIGIN`, `CORS_ALLOW_ORIGINS`)
- [ ] Security headers enabled (CSP, X-Frame-Options, etc.)
- [ ] API endpoints protected with authentication
- [ ] Webhook endpoints validated with signatures

### Container Security
- [ ] Images scanned for vulnerabilities
- [ ] Non-root users configured (UID 1000)
- [ ] Read-only root filesystem where possible
- [ ] Security contexts applied (no privilege escalation)
- [ ] Resource limits set (prevent DoS)

## Application Configuration

### Environment Variables
- [ ] `DATABASE_URL` pointing to production database
- [ ] `REDIS_URL` configured for caching
- [ ] `OPENSEARCH_URL` configured (if using OpenSearch)
- [ ] `FRONTEND_ORIGIN` set to production domain
- [ ] `ENVIRONMENT=production`
- [ ] `LOG_LEVEL=INFO` or `WARNING` (not DEBUG)
- [ ] `LOG_FORMAT=json` for structured logging
- [ ] GPU settings verified (`FORCE_GPU`, `GPU_DEVICE_PREFERENCE`)
- [ ] Whisper model configured (`WHISPER_MODEL=large-v3`)
- [ ] Cleanup settings configured (`CLEANUP_AFTER_PROCESS=true`)

### Resource Allocation
- [ ] API replicas: minimum 3 for high availability
- [ ] Worker replicas: based on GPU availability
- [ ] CPU requests/limits set appropriately
- [ ] Memory requests/limits set appropriately
- [ ] GPU resources allocated (1 GPU per worker)
- [ ] Horizontal Pod Autoscaler configured
- [ ] Pod Disruption Budget configured (K8s)

### Feature Flags
- [ ] OAuth providers enabled as needed
- [ ] Billing features configured (Stripe)
- [ ] Search backend selected (`SEARCH_BACKEND=postgres` or `opensearch`)
- [ ] Caching enabled (`ENABLE_CACHING=true`)
- [ ] Metrics collection enabled (`ENABLE_METRICS=true`)
- [ ] Translation features configured if needed
- [ ] Custom vocabulary enabled if needed

## Monitoring and Observability

### Metrics
- [ ] Prometheus scraping configured
- [ ] Grafana dashboards deployed
- [ ] Custom metrics endpoints accessible (`/metrics`)
- [ ] GPU metrics monitored (utilization, memory)
- [ ] Database performance metrics tracked
- [ ] Worker queue depth monitored

### Logging
- [ ] Centralized logging configured (ELK, Loki, CloudWatch)
- [ ] Log aggregation working
- [ ] Log retention policies set
- [ ] Structured JSON logging enabled
- [ ] Error logs monitored
- [ ] Application logs accessible

### Alerting
- [ ] Critical alerts configured (service down, database errors)
- [ ] Resource alerts (high CPU, memory, disk usage)
- [ ] GPU alerts (not detected, out of memory)
- [ ] Database connection pool exhaustion alerts
- [ ] Certificate expiry alerts (30 days, 7 days, 1 day)
- [ ] Backup failure alerts
- [ ] Alert routing configured (email, Slack, PagerDuty)

### Health Checks
- [ ] Liveness probes configured
- [ ] Readiness probes configured
- [ ] Health check endpoints responsive (`/health`, `/ready`)
- [ ] Startup probes configured (K8s)
- [ ] External monitoring (UptimeRobot, Pingdom, etc.)

## Backup and Disaster Recovery

### Database Backups
- [ ] Automated daily backups scheduled
- [ ] Backup verification process configured
- [ ] WAL archiving to remote storage
- [ ] Point-in-time recovery tested
- [ ] Backup encryption enabled
- [ ] Backup retention: 7 daily, 4 weekly, 12 monthly
- [ ] Restore procedure documented and tested

### Media Backups
- [ ] Media files backed up to remote storage
- [ ] Backup schedule configured (daily or weekly)
- [ ] Backup verification automated
- [ ] Media retention policy set (30 days default)

### Disaster Recovery
- [ ] Recovery Time Objective (RTO) defined
- [ ] Recovery Point Objective (RPO) defined
- [ ] Disaster recovery plan documented
- [ ] Backup restore tested regularly (quarterly minimum)
- [ ] Off-site backups configured
- [ ] Multi-region setup for critical deployments

## Performance

### Caching
- [ ] Redis cache configured and healthy
- [ ] Cache hit rates monitored
- [ ] Cache TTLs tuned appropriately
- [ ] Cache invalidation strategy tested

### Database Optimization
- [ ] Database indexes verified
- [ ] Query performance monitored
- [ ] Connection pool size tuned
- [ ] Slow query logging enabled
- [ ] VACUUM and ANALYZE scheduled

### Content Delivery
- [ ] CDN configured for static assets (optional)
- [ ] Media compression enabled
- [ ] Response caching configured
- [ ] gzip/brotli compression enabled

## Post-Deployment

### Smoke Tests
- [ ] API health checks passing
- [ ] Frontend accessible
- [ ] User authentication working
- [ ] Job submission working
- [ ] Video transcription processing
- [ ] Search functionality working
- [ ] Export features functional
- [ ] Webhooks delivering (if configured)

### Validation
- [ ] Test job submitted and completed successfully
- [ ] GPU detected and used by worker
- [ ] Transcripts generated accurately
- [ ] Speaker diarization working (if enabled)
- [ ] Search results accurate
- [ ] PDF export working
- [ ] Email notifications sent (if configured)

### Documentation
- [ ] Deployment architecture documented
- [ ] Runbooks created for common operations
- [ ] Troubleshooting guide accessible
- [ ] Contact information for on-call team
- [ ] Escalation procedures defined

### Compliance
- [ ] Data privacy requirements met (GDPR, CCPA, etc.)
- [ ] User data retention policies configured
- [ ] Audit logging enabled
- [ ] Terms of service and privacy policy deployed
- [ ] Cookie consent configured (if required)

## Ongoing Operations

### Maintenance
- [ ] Update schedule defined (security patches, feature releases)
- [ ] Maintenance windows communicated
- [ ] Zero-downtime deployment strategy tested
- [ ] Rollback procedures documented
- [ ] Change management process in place

### Monitoring Schedule
- [ ] Daily: Check dashboards for anomalies
- [ ] Daily: Verify backup completion
- [ ] Weekly: Review error logs
- [ ] Weekly: Check certificate expiry dates
- [ ] Monthly: Review resource utilization
- [ ] Monthly: Update dependencies
- [ ] Quarterly: Test disaster recovery
- [ ] Quarterly: Security audit

### Scaling
- [ ] Auto-scaling policies configured
- [ ] Scale-up triggers defined
- [ ] Scale-down policies tested
- [ ] Capacity planning reviewed quarterly
- [ ] Load testing performed

### Cost Management
- [ ] Resource tagging configured
- [ ] Cost monitoring enabled
- [ ] Budget alerts configured
- [ ] Unused resources identified and removed
- [ ] Reserved instances/committed use considered

## Sign-Off

- [ ] **Infrastructure Team**: Infrastructure provisioned and secured
- [ ] **Security Team**: Security review completed
- [ ] **Database Team**: Database configured and backed up
- [ ] **DevOps Team**: Monitoring and alerting configured
- [ ] **Application Team**: Application deployed and tested
- [ ] **Product Team**: Features verified and functional
- [ ] **Management**: Go-live approval obtained

---

## Post-Launch

After 24 hours:
- [ ] Review metrics and logs
- [ ] Check for errors or warnings
- [ ] Validate monitoring alerts
- [ ] Review backup completion
- [ ] Performance tuning if needed

After 1 week:
- [ ] Capacity review
- [ ] Cost analysis
- [ ] User feedback collected
- [ ] Performance optimization identified

After 1 month:
- [ ] Comprehensive review
- [ ] Documentation updates
- [ ] Lessons learned documented
- [ ] Process improvements identified

---

## Quick Reference Commands

### Health Check
```bash
# API health
curl https://api.example.com/health

# Database connection
kubectl exec -it transcript-api-xxx -- python -c "from app.db import engine; engine.connect()"

# GPU status
kubectl exec -it transcript-worker-xxx -- rocm-smi
# or
kubectl exec -it transcript-worker-xxx -- nvidia-smi
```

### View Logs
```bash
# Kubernetes
kubectl logs -f deployment/transcript-api -n transcript-create
kubectl logs -f deployment/transcript-worker -n transcript-create

# Docker Compose
docker compose logs -f api
docker compose logs -f worker
```

### Database Backup
```bash
# Manual backup
./scripts/backup_db.sh

# Verify backup
./scripts/verify_backup.sh /backups/db/backup_name.sql.gz
```

### Restart Services
```bash
# Kubernetes
kubectl rollout restart deployment/transcript-api -n transcript-create
kubectl rollout restart deployment/transcript-worker -n transcript-create

# Docker Compose
docker compose restart api worker
```

---

## Support

For issues during deployment:
- GitHub Issues: https://github.com/subculture-collective/transcript-create/issues
- Documentation: https://github.com/subculture-collective/transcript-create/tree/main/docs/deployment
- Troubleshooting: [docs/deployment/troubleshooting.md](./troubleshooting.md)
