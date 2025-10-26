# Backup Operations Runbook

## Overview

This runbook provides detailed operational procedures for managing backups in the transcript-create system. It covers routine operations, troubleshooting, and maintenance tasks.

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Backup Scripts Usage](#backup-scripts-usage)
3. [Monitoring](#monitoring)
4. [Troubleshooting](#troubleshooting)
5. [Maintenance Tasks](#maintenance-tasks)
6. [Cloud Storage Operations](#cloud-storage-operations)

---

## Daily Operations

### Automated Backup Schedule

The backup service runs automatically via cron on the following schedule:

| Task | Schedule | Script |
|------|----------|--------|
| Database Backup | Daily 2:00 AM UTC | `backup_db.sh` |
| Media Backup | Daily 3:00 AM UTC | `backup_media.sh` |
| Backup Verification | Weekly Sunday 4:00 AM UTC | `verify_backup.sh` |

### Check Backup Status

**View recent backup logs:**
```bash
# Database backup logs
tail -100 /backups/logs/backup_$(date +%Y%m%d).log

# Media backup logs
tail -100 /backups/media/logs/media_backup_*.log | tail -100

# Cron logs
docker compose logs backup | tail -50
```

**Check latest backup age:**
```bash
# Database backups
ls -lht /backups/daily/ | head -5

# Media backups
ls -ld /backups/media/current
```

**Verify backup sizes:**
```bash
# Database backup size
du -sh /backups/daily/transcripts_daily_*.sql.gz | tail -1

# Total backup storage
du -sh /backups/
```

---

## Backup Scripts Usage

### Database Backup Script

**Location:** `scripts/backup_db.sh`

**Basic usage:**
```bash
cd /path/to/transcript-create   # Change this to your project root directory
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/transcripts"
./scripts/backup_db.sh
```

**With encryption:**
```bash
export BACKUP_ENCRYPT=true
export BACKUP_GPG_RECIPIENT="backup@example.com"
./scripts/backup_db.sh --encrypt
```

**Verify existing backups:**
```bash
./scripts/backup_db.sh --verify-only
```

**Manual backup (outside schedule):**
```bash
# Run inside Docker container
docker compose exec backup bash -c "cd /scripts && ./backup_db.sh"

# Or from host with Docker environment
docker compose run --rm backup bash -c "cd /scripts && ./backup_db.sh"
```

**Environment variables:**
```bash
DATABASE_URL                 # PostgreSQL connection string (required)
BACKUP_DIR                  # Backup directory (default: /backups)
BACKUP_ENCRYPT              # Enable encryption (default: false)
BACKUP_GPG_RECIPIENT        # GPG recipient email
BACKUP_RETENTION_DAILY      # Days to keep daily backups (default: 7)
BACKUP_RETENTION_WEEKLY     # Weeks to keep weekly backups (default: 4)
BACKUP_RETENTION_MONTHLY    # Months to keep monthly backups (default: 12)
BACKUP_S3_BUCKET           # S3 bucket for remote storage
BACKUP_GCS_BUCKET          # GCS bucket for remote storage
BACKUP_AZURE_CONTAINER     # Azure container for remote storage
```

---

### Media Backup Script

**Location:** `scripts/backup_media.sh`

**Basic usage:**
```bash
export MEDIA_SOURCE_DIR=/data
export MEDIA_BACKUP_DIR=/backups/media
./scripts/backup_media.sh
```

**Full backup (no incremental):**
```bash
./scripts/backup_media.sh --full
```

**Verify media backups:**
```bash
./scripts/backup_media.sh --verify-only
```

**Environment variables:**
```bash
MEDIA_SOURCE_DIR          # Source directory (default: /data)
MEDIA_BACKUP_DIR         # Backup directory (default: /backups/media)
MEDIA_RETENTION_DAYS     # Retention in days (default: 30)
BACKUP_S3_BUCKET         # S3 bucket for remote storage
BACKUP_GCS_BUCKET        # GCS bucket for remote storage
BACKUP_AZURE_CONTAINER   # Azure container for remote storage
```

---

### Restore Script

**Location:** `scripts/restore_db.sh`

**List available backups:**
```bash
./scripts/restore_db.sh --list-backups
```

**Restore from specific backup:**
```bash
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/transcripts"
./scripts/restore_db.sh --backup-file /backups/daily/transcripts_daily_20241026_020000.sql.gz
```

**Force restore (skip confirmation):**
```bash
./scripts/restore_db.sh --backup-file /backups/daily/transcripts_daily_20241026_020000.sql.gz --force
```

**Point-in-time recovery guidance:**
```bash
./scripts/restore_db.sh --pitr --target-time '2024-10-26 01:30:00'
```

---

### Verification Script

**Location:** `scripts/verify_backup.sh`

**Basic verification:**
```bash
./scripts/verify_backup.sh
```

**With test restore:**
```bash
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/transcripts"
./scripts/verify_backup.sh --test-restore
```

**Custom backup age threshold:**
```bash
./scripts/verify_backup.sh --max-age-hours 48
```

**Exit codes:**
- `0` - All verifications passed
- `1` - Verification failures detected
- `2` - Backups too old or missing

---

## Monitoring

### Prometheus Metrics

**Export backup metrics for monitoring:**

Create a script to export metrics: `scripts/export_backup_metrics.sh`

```bash
#!/bin/bash
# Export backup metrics to file for node_exporter textfile collector

METRICS_FILE="/var/lib/node_exporter/textfile_collector/backups.prom"

# Database backup metrics
if [[ -f /backups/daily/transcripts_daily_*.sql.gz ]]; then
    latest_backup=$(ls -t /backups/daily/transcripts_daily_*.sql.gz | head -1)
    backup_time=$(stat -c %Y "$latest_backup")
    backup_size=$(stat -c %s "$latest_backup")
    
    cat > "$METRICS_FILE" <<EOF
# HELP backup_last_success_timestamp Unix timestamp of last successful backup
# TYPE backup_last_success_timestamp gauge
backup_last_success_timestamp{type="database"} $backup_time

# HELP backup_size_bytes Size of latest backup in bytes
# TYPE backup_size_bytes gauge
backup_size_bytes{type="database"} $backup_size

# HELP backup_last_status Exit status of last backup (0=success)
# TYPE backup_last_status gauge
backup_last_status{type="database"} 0
EOF
fi
```

### Grafana Dashboard

**Key panels to include:**

1. **Backup Age**
   ```promql
   (time() - backup_last_success_timestamp{type="database"}) / 3600
   ```

2. **Backup Size Trend**
   ```promql
   backup_size_bytes{type="database"}
   ```

3. **Backup Success Rate**
   ```promql
   rate(backup_last_status{type="database"}[24h])
   ```

4. **Storage Usage**
   ```promql
   node_filesystem_avail_bytes{mountpoint="/backups"}
   ```

### Alert Rules

**Example Prometheus alerts:**

```yaml
groups:
  - name: backup_alerts
    rules:
      - alert: BackupTooOld
        expr: time() - backup_last_success_timestamp > 93600  # 26 hours
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Backup is too old"
          description: "Last backup was {{ $value | humanizeDuration }} ago"

      - alert: BackupSizeIncrease
        expr: |
          (backup_size_bytes - backup_size_bytes offset 7d) / backup_size_bytes offset 7d > 0.5
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Backup size increased significantly"
          description: "Backup size increased by {{ $value | humanizePercentage }} in the last week"

      - alert: BackupStorageLow
        expr: |
          node_filesystem_avail_bytes{mountpoint="/backups"} / node_filesystem_size_bytes{mountpoint="/backups"} < 0.1
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Backup storage running low"
          description: "Only {{ $value | humanizePercentage }} storage available"
```

---

## Troubleshooting

### Issue: Backup Job Failed

**Symptoms:**
- No recent backup files
- Error messages in logs
- Backup script exits with non-zero status

**Diagnosis:**
```bash
# Check recent logs
tail -100 /backups/logs/backup_$(date +%Y%m%d).log

# Check backup service status
docker compose ps backup

# Check database connectivity
docker compose exec backup pg_isready -h db -U postgres
```

**Common causes and solutions:**

1. **Database connection failed:**
   ```bash
   # Verify DATABASE_URL is correct
   docker compose exec backup printenv DATABASE_URL
   
   # Test connection
   docker compose exec backup psql -c "SELECT version();"
   ```

2. **Insufficient disk space:**
   ```bash
   # Check available space
   df -h /backups
   
   # Clean up old backups manually if needed
   find /backups/daily -name "*.sql.gz" -mtime +7 -delete
   ```

3. **Permission issues:**
   ```bash
   # Check backup directory permissions
   ls -ld /backups/
   
   # Fix permissions
   chmod 755 /backups
   chown -R postgres:postgres /backups
   ```

4. **pg_dump errors:**
   ```bash
   # Test pg_dump directly
   docker compose exec db pg_dump -U postgres -d transcripts > /tmp/test.sql
   
   # Check PostgreSQL logs
   docker compose logs db | grep -i error
   ```

---

### Issue: Restore Failed

**Symptoms:**
- Restore script exits with error
- Database not restored correctly
- Missing tables or data

**Diagnosis:**
```bash
# Verify backup file integrity
gzip -t /backups/daily/transcripts_daily_*.sql.gz

# Check backup contents
gunzip -c /backups/daily/transcripts_daily_*.sql.gz | head -100

# Verify checksum
sha256sum -c /backups/daily/transcripts_daily_*.sql.gz.sha256
```

**Solutions:**

1. **Corrupted backup file:**
   ```bash
   # Use an older backup
   ./scripts/restore_db.sh --list-backups
   ./scripts/restore_db.sh --backup-file /backups/daily/older_backup.sql.gz
   ```

2. **Database connection issues:**
   ```bash
   # Verify database is running
   docker compose ps db
   
   # Verify connection
   docker compose exec db psql -U postgres -c "SELECT 1;"
   ```

3. **Insufficient disk space:**
   ```bash
   # Check database volume space
   docker system df -v
   
   # Clean up if needed
   docker volume prune
   ```

---

### Issue: Backup Size Anomaly

**Symptoms:**
- Backup size significantly larger or smaller than usual
- Disk space filling up quickly

**Diagnosis:**
```bash
# Compare backup sizes
ls -lh /backups/daily/ | tail -10

# Check database size
docker compose exec db psql -U postgres -c "
  SELECT pg_size_pretty(pg_database_size('transcripts'));
"

# Check table sizes
docker compose exec db psql -U postgres -d transcripts -c "
  SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
  FROM pg_tables
  WHERE schemaname = 'public'
  ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
  LIMIT 10;
"
```

**Actions:**
- Review data growth patterns
- Check for runaway queries creating temporary data
- Consider archiving old data
- Review backup compression settings

---

### Issue: Cloud Upload Failed

**Symptoms:**
- Backups not appearing in cloud storage
- Upload errors in logs

**Diagnosis:**
```bash
# Check cloud CLI availability
docker compose exec backup which aws
docker compose exec backup which gsutil
docker compose exec backup which az

# Test cloud credentials
docker compose exec backup aws s3 ls
docker compose exec backup gsutil ls
docker compose exec backup az storage account list
```

**Solutions:**

1. **Missing credentials:**
   ```bash
   # Configure AWS credentials
   docker compose exec backup aws configure
   
   # Or set environment variables
   export AWS_ACCESS_KEY_ID=...
   export AWS_SECRET_ACCESS_KEY=...
   ```

2. **Network issues:**
   ```bash
   # Test connectivity
   docker compose exec backup curl -I https://s3.amazonaws.com
   
   # Check proxy settings if behind firewall
   export HTTP_PROXY=...
   export HTTPS_PROXY=...
   ```

3. **Bucket permissions:**
   ```bash
   # Verify bucket access
   aws s3api head-bucket --bucket your-backup-bucket
   
   # Check IAM permissions for the user/role
   ```

---

## Maintenance Tasks

### Weekly Tasks

1. **Review backup logs:**
   ```bash
   # Check for errors or warnings
   grep -i "error\|warning\|failed" /backups/logs/backup_*.log | tail -50
   ```

2. **Verify backup integrity:**
   ```bash
   ./scripts/verify_backup.sh
   ```

3. **Check storage usage:**
   ```bash
   du -sh /backups/*
   df -h /backups
   ```

### Monthly Tasks

1. **Test restore in staging:**
   ```bash
   # Copy latest backup to staging
   scp /backups/daily/latest.sql.gz staging:/tmp/
   
   # Restore on staging
   ssh staging "cd /app && ./scripts/restore_db.sh --backup-file /tmp/latest.sql.gz --force"
   
   # Verify staging functionality
   ```

2. **Review retention policy:**
   ```bash
   # Count backups by type
   echo "Daily: $(ls /backups/daily/*.sql.gz | wc -l)"
   echo "Weekly: $(ls /backups/weekly/*.sql.gz | wc -l)"
   echo "Monthly: $(ls /backups/monthly/*.sql.gz | wc -l)"
   ```

3. **Audit cloud storage costs:**
   ```bash
   # AWS S3
   aws s3 ls s3://your-bucket/backups/ --recursive --summarize --human-readable
   
   # GCS
   gsutil du -sh gs://your-bucket/backups/
   ```

### Quarterly Tasks

1. **Disaster recovery drill** (see [Disaster Recovery Plan](disaster-recovery.md))

2. **Review and update documentation**

3. **Security audit:**
   - Review backup access logs
   - Rotate encryption keys
   - Update cloud credentials
   - Review IAM policies

4. **Capacity planning:**
   - Analyze backup growth trends
   - Project storage needs for next quarter
   - Adjust retention policies if needed

---

## Cloud Storage Operations

### AWS S3

**Upload backup manually:**
```bash
aws s3 cp /backups/daily/transcripts_daily_20241026.sql.gz \
  s3://your-bucket/backups/postgres/ \
  --storage-class GLACIER
```

**List backups:**
```bash
aws s3 ls s3://your-bucket/backups/postgres/ --recursive --human-readable
```

**Download backup:**
```bash
aws s3 cp s3://your-bucket/backups/postgres/transcripts_daily_20241026.sql.gz \
  /tmp/restore.sql.gz
```

**Configure lifecycle policy:**
```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket your-bucket \
  --lifecycle-configuration file://s3-lifecycle.json
```

### Google Cloud Storage

**Upload backup:**
```bash
gsutil cp /backups/daily/transcripts_daily_20241026.sql.gz \
  gs://your-bucket/backups/postgres/
```

**List backups:**
```bash
gsutil ls -lh gs://your-bucket/backups/postgres/
```

**Download backup:**
```bash
gsutil cp gs://your-bucket/backups/postgres/transcripts_daily_20241026.sql.gz \
  /tmp/restore.sql.gz
```

**Set storage class:**
```bash
gsutil rewrite -s NEARLINE \
  gs://your-bucket/backups/postgres/transcripts_daily_20241026.sql.gz
```

### Azure Blob Storage

**Upload backup:**
```bash
az storage blob upload \
  --account-name youraccount \
  --container-name backups \
  --name postgres/transcripts_daily_20241026.sql.gz \
  --file /backups/daily/transcripts_daily_20241026.sql.gz \
  --tier Cool
```

**List backups:**
```bash
az storage blob list \
  --account-name youraccount \
  --container-name backups \
  --prefix postgres/ \
  --output table
```

**Download backup:**
```bash
az storage blob download \
  --account-name youraccount \
  --container-name backups \
  --name postgres/transcripts_daily_20241026.sql.gz \
  --file /tmp/restore.sql.gz
```

---

## Appendix

### Quick Reference Commands

```bash
# Check last backup
ls -lht /backups/daily/ | head -1

# Manual database backup
docker compose exec backup bash -c "cd /scripts && ./backup_db.sh"

# Manual media backup
docker compose exec backup bash -c "cd /scripts && ./backup_media.sh"

# Verify backups
docker compose exec backup bash -c "cd /scripts && ./verify_backup.sh"

# List available backups
docker compose exec backup bash -c "cd /scripts && ./restore_db.sh --list-backups"

# Check backup service logs
docker compose logs -f backup

# Check storage space
df -h /backups
du -sh /backups/*
```

### Backup File Naming Convention

```
transcripts_{type}_{timestamp}.sql.gz[.gpg]

Where:
  type      = daily | weekly | monthly
  timestamp = YYYYMMDD_HHMMSS
  .gpg      = optional encryption suffix

Examples:
  transcripts_daily_20241026_020000.sql.gz
  transcripts_weekly_20241020_020000.sql.gz.gpg
  transcripts_monthly_20241001_020000.sql.gz
```

---

**Last Updated:** 2024-10-26  
**Next Review:** 2025-01-26
