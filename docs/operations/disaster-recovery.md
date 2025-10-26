# Disaster Recovery Plan

## Overview

This document outlines the disaster recovery procedures for the transcript-create system, including backup strategies, recovery procedures, and runbooks for common failure scenarios.

**Recovery Objectives:**
- **RTO (Recovery Time Objective):** < 1 hour
- **RPO (Recovery Point Objective):** < 5 minutes (with WAL archiving)

## Table of Contents

1. [Backup Strategy](#backup-strategy)
2. [Recovery Procedures](#recovery-procedures)
3. [Disaster Scenarios](#disaster-scenarios)
4. [Testing and Drills](#testing-and-drills)
5. [Monitoring and Alerts](#monitoring-and-alerts)
6. [Contact Information](#contact-information)

---

## Backup Strategy

### Database Backups

#### Daily Full Backups
- **Schedule:** 2 AM UTC daily
- **Method:** `pg_dump` with gzip compression
- **Location:** `/backups/daily/`, `/backups/weekly/`, `/backups/monthly/`
- **Retention:**
  - Daily: 7 days
  - Weekly: 4 weeks (28 days)
  - Monthly: 12 months (360 days)
- **Encryption:** Optional GPG encryption (enable in production)
- **Remote Storage:** Optional sync to S3/GCS/Azure

#### WAL Archiving (Point-in-Time Recovery)
- **Method:** Continuous WAL archiving
- **Location:** `/backups/wal_archive/`
- **Retention:** 7 days
- **Enables:** Point-in-time recovery to any timestamp within retention window

### Media Backups

- **Content:** `/data` volume (video files, audio, transcripts)
- **Schedule:** 3 AM UTC daily
- **Method:** rsync with incremental backups
- **Retention:** 30 days
- **Remote Storage:** Optional sync to cloud storage with cold/glacier tier

### Verification

- **Schedule:** Weekly (Sunday 4 AM UTC)
- **Checks:**
  - Checksum verification
  - Gzip integrity
  - Backup age validation
  - Test restore (optional)

---

## Recovery Procedures

### Full Database Restore

Use this procedure to restore the database from a full backup.

#### Prerequisites
- Access to backup files
- PostgreSQL client tools installed
- Database credentials

#### Steps

1. **List available backups:**
   ```bash
   cd /path/to/transcript-create
   ./scripts/restore_db.sh --list-backups
   ```

2. **Stop application services:**
   ```bash
   docker compose stop api worker
   ```

3. **Restore from backup:**
   ```bash
   export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/transcripts"
   ./scripts/restore_db.sh --backup-file /backups/daily/transcripts_daily_YYYYMMDD_HHMMSS.sql.gz
   ```

4. **Verify data integrity:**
   ```bash
   # Connect to database and verify critical tables
   docker compose exec db psql -U postgres -d transcripts -c "SELECT COUNT(*) FROM jobs;"
   docker compose exec db psql -U postgres -d transcripts -c "SELECT COUNT(*) FROM videos;"
   docker compose exec db psql -U postgres -d transcripts -c "SELECT COUNT(*) FROM transcripts;"
   ```

5. **Restart services:**
   ```bash
   docker compose start api worker
   ```

6. **Test application:**
   - Verify API health: `curl http://localhost:8000/health`
   - Test search functionality
   - Check recent jobs/videos

**Estimated Time:** 15-30 minutes (depending on database size)

---

### Point-in-Time Recovery (PITR)

Use this procedure to recover to a specific point in time using WAL archives.

#### Prerequisites
- Base backup taken before target recovery time
- WAL archive files from backup time to target time
- PostgreSQL stopped and data directory accessible

#### Steps

1. **Stop PostgreSQL:**
   ```bash
   docker compose stop db
   ```

2. **Clear existing data directory:**
   ```bash
   docker compose run --rm db rm -rf /var/lib/postgresql/data/*
   ```

3. **Restore base backup:**
   ```bash
   # Extract base backup to data directory
   docker compose run --rm backup bash -c "
     gunzip -c /backups/daily/transcripts_daily_YYYYMMDD_HHMMSS.sql.gz | \
     psql -U postgres -d template1
   "
   ```

4. **Configure recovery:**
   ```bash
   docker compose run --rm db bash -c "
     cat > /var/lib/postgresql/data/recovery.signal << EOF
   # PostgreSQL will enter recovery mode
   EOF
     
     cat >> /var/lib/postgresql/data/postgresql.auto.conf << EOF
   restore_command = 'cp /backups/wal_archive/%f %p'
   recovery_target_time = '2024-10-26 01:30:00'
   recovery_target_action = 'promote'
   EOF
   "
   ```

5. **Start PostgreSQL to begin recovery:**
   ```bash
   docker compose start db
   ```

6. **Monitor recovery:**
   ```bash
   docker compose logs -f db
   # Watch for "database system is ready to accept connections"
   ```

7. **Verify recovered data:**
   ```bash
   docker compose exec db psql -U postgres -d transcripts -c "
     SELECT NOW(), COUNT(*) FROM videos WHERE created_at < '2024-10-26 01:30:00';
   "
   ```

8. **Restart application:**
   ```bash
   docker compose start api worker
   ```

**Estimated Time:** 30-60 minutes (depending on WAL volume)

---

### Media File Restore

Use this procedure to restore media files from backup.

#### Steps

1. **Stop worker to prevent new processing:**
   ```bash
   docker compose stop worker
   ```

2. **List available media backups:**
   ```bash
   ls -lh /backups/media/
   ```

3. **Restore media files:**
   ```bash
   # Restore from specific backup
   rsync -av --progress /backups/media/YYYYMMDD_HHMMSS/ /data/

   # Or restore from latest
   rsync -av --progress /backups/media/current/ /data/
   ```

4. **Verify restored files:**
   ```bash
   # Check file counts and sizes
   find /data -type f | wc -l
   du -sh /data
   ```

5. **Restart worker:**
   ```bash
   docker compose start worker
   ```

**Estimated Time:** Variable (depends on data size, typically 10-30 minutes)

---

## Disaster Scenarios

### Scenario 1: Database Corruption

**Symptoms:**
- PostgreSQL crashes or won't start
- Data corruption errors in logs
- Inconsistent query results

**Recovery Actions:**

1. **Assess severity:**
   ```bash
   docker compose logs db | grep -i "corruption\|panic\|fatal"
   ```

2. **Attempt PostgreSQL recovery:**
   ```bash
   docker compose exec db pg_resetwal -f /var/lib/postgresql/data
   ```

3. **If recovery fails, restore from backup:**
   - Follow [Full Database Restore](#full-database-restore) procedure
   - Use most recent backup before corruption

**Prevention:**
- Regular backup verification
- Enable checksums on PostgreSQL data pages
- Monitor disk health

---

### Scenario 2: Accidental Data Deletion

**Symptoms:**
- Jobs, videos, or transcripts missing
- User reports data loss
- Audit logs show deletion events

**Recovery Actions:**

1. **Determine deletion time:**
   - Check application logs
   - Review audit trails
   - Identify affected data

2. **If within WAL retention (7 days):**
   - Use [Point-in-Time Recovery](#point-in-time-recovery-pitr)
   - Recover to timestamp just before deletion

3. **If outside WAL retention:**
   - Use [Full Database Restore](#full-database-restore)
   - May lose data between backup and deletion

**Prevention:**
- Implement soft deletes for critical data
- Require confirmation for bulk operations
- Regular user access audits

---

### Scenario 3: Complete Server Failure

**Symptoms:**
- Server unresponsive
- Hardware failure
- Infrastructure outage

**Recovery Actions:**

1. **Provision new server/infrastructure:**
   - Launch new VM or container host
   - Install Docker and docker-compose

2. **Clone repository:**
   ```bash
   git clone https://github.com/subculture-collective/transcript-create.git
   cd transcript-create
   ```

3. **Restore configuration:**
   ```bash
   # Restore .env from secure backup location
   cp /secure/backup/.env .env
   ```

4. **Restore database from remote backup:**
   ```bash
   # If using S3
   aws s3 cp s3://your-bucket/backups/postgres/latest.sql.gz /backups/
   
   # If using GCS
   gsutil cp gs://your-bucket/backups/postgres/latest.sql.gz /backups/
   ```

5. **Start services:**
   ```bash
   docker compose up -d db
   ```

6. **Restore database:**
   ```bash
   ./scripts/restore_db.sh --backup-file /backups/latest.sql.gz --force
   ```

7. **Restore media files (optional):**
   ```bash
   # Sync from cloud storage
   aws s3 sync s3://your-bucket/media/ /data/
   ```

8. **Start application:**
   ```bash
   docker compose up -d
   ```

9. **Verify system:**
   - Check health endpoints
   - Test critical functionality
   - Review logs for errors

**Estimated Time:** 1-2 hours (depending on data size and network speed)

---

### Scenario 4: Ransomware Attack

**Symptoms:**
- Files encrypted or inaccessible
- Ransom note present
- Unusual system behavior

**Recovery Actions:**

1. **Immediate isolation:**
   ```bash
   # Disconnect from network immediately
   docker compose down
   # Isolate affected systems
   ```

2. **Assess impact:**
   - Identify encrypted files
   - Check if backups are affected
   - Document attack timeline

3. **Do NOT pay ransom**
   - Contact authorities
   - Engage security incident response team

4. **Recover from clean backups:**
   - Verify backups are not encrypted
   - Use backups from before attack
   - Follow [Full Database Restore](#full-database-restore)

5. **Rebuild on clean infrastructure:**
   - Provision new servers
   - Apply security patches
   - Restore from verified backups

6. **Security hardening:**
   - Change all passwords and keys
   - Review access controls
   - Enable backup encryption
   - Implement additional monitoring

**Prevention:**
- Enable backup encryption
- Store backups offline or immutable
- Regular security audits
- Principle of least privilege
- Network segmentation

---

## Testing and Drills

### Quarterly Disaster Recovery Drill

**Schedule:** First Sunday of each quarter

**Procedure:**

1. **Plan the drill:**
   - Select scenario (database corruption, server failure, etc.)
   - Notify team members
   - Schedule maintenance window

2. **Execute recovery:**
   - Follow appropriate runbook
   - Document all steps and times
   - Note any issues or deviations

3. **Verify recovery:**
   - Check data integrity
   - Test all application features
   - Compare with pre-drill state

4. **Measure metrics:**
   - Record actual RTO (recovery time)
   - Verify RPO (data loss window)
   - Compare against objectives

5. **Document lessons learned:**
   - What worked well
   - What needs improvement
   - Action items for next drill

6. **Update documentation:**
   - Revise procedures based on findings
   - Update contact information
   - Improve automation where possible

---

## Monitoring and Alerts

### Backup Health Monitoring

**Prometheus Metrics:**
```yaml
# Add to config/prometheus/alerts.yml

groups:
  - name: backup_alerts
    interval: 5m
    rules:
      - alert: BackupTooOld
        expr: time() - backup_last_success_timestamp > 86400 * 1.1  # 26.4 hours
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Database backup is too old"
          description: "Last successful backup was more than 26 hours ago"

      - alert: BackupFailed
        expr: backup_last_status != 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Backup job failed"
          description: "Last backup job exited with non-zero status"

      - alert: BackupSizeAnomaly
        expr: abs(backup_size_bytes - backup_size_bytes offset 1d) / backup_size_bytes > 0.5
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Backup size changed significantly"
          description: "Backup size changed by more than 50% compared to yesterday"
```

### Alert Destinations

- **Email:** ops@example.com
- **Slack:** #alerts channel
- **PagerDuty:** Production on-call rotation
- **Grafana Dashboard:** Backup & DR Overview

---

## Backup Verification Checklist

### Weekly Verification (Automated)

- [ ] All database backups have valid checksums
- [ ] Gzip integrity verified for all backups
- [ ] Latest backup is less than 26 hours old
- [ ] Media backup is present and accessible
- [ ] WAL archives are being generated (if configured)
- [ ] Backup retention policy applied correctly
- [ ] Cloud sync successful (if configured)

### Monthly Verification (Manual)

- [ ] Perform test restore to staging environment
- [ ] Verify restored data matches production
- [ ] Test application against restored database
- [ ] Review backup storage capacity
- [ ] Audit backup access logs
- [ ] Update disaster recovery documentation
- [ ] Test encrypted backup restore (if enabled)

---

## Contact Information

### Emergency Contacts

| Role | Name | Phone | Email | Availability |
|------|------|-------|-------|--------------|
| Primary DBA | TBD | TBD | TBD | 24/7 |
| Backup DBA | TBD | TBD | TBD | Business hours |
| Infrastructure Lead | TBD | TBD | TBD | On-call rotation |
| Security Team | TBD | TBD | security@example.com | 24/7 |

### External Contacts

- **Cloud Provider Support:** [Support Portal]
- **Database Vendor:** PostgreSQL Community / Commercial Support
- **Incident Response Firm:** [Retainer details]

---

## Appendix

### A. Backup Script Reference

- **backup_db.sh:** Daily database backups with retention policy
- **backup_media.sh:** Media file backups with rsync
- **restore_db.sh:** Database restore from backups
- **verify_backup.sh:** Backup integrity verification

### B. WAL Archiving Configuration

Add to PostgreSQL configuration (`postgresql.conf`):

```ini
# Enable WAL archiving
wal_level = replica
archive_mode = on
archive_command = 'gzip < %p > /backups/wal_archive/%f.gz'
archive_timeout = 300  # 5 minutes

# Optional: increase max_wal_size for better performance
max_wal_size = 4GB
min_wal_size = 1GB
```

### C. Backup Storage Sizing

**Database Backups:**
- Compressed size: ~10-20% of database size
- Daily: 7 backups
- Weekly: 4 backups
- Monthly: 12 backups
- Example: 10 GB database → ~200 GB backup storage

**Media Backups:**
- Incremental backups save space
- Estimate: 1.5x media directory size
- Example: 100 GB media → ~150 GB backup storage

**WAL Archives:**
- Rate: ~16 MB per checkpoint (default)
- 7 days retention: ~10-50 GB (depending on write volume)

**Total Estimate:** (Database × 2) + (Media × 1.5) + 50 GB

### D. Cloud Storage Lifecycle Policies

**AWS S3:**
```json
{
  "Rules": [
    {
      "Id": "BackupLifecycle",
      "Status": "Enabled",
      "Transitions": [
        {
          "Days": 7,
          "StorageClass": "GLACIER_IR"
        },
        {
          "Days": 30,
          "StorageClass": "GLACIER"
        },
        {
          "Days": 90,
          "StorageClass": "DEEP_ARCHIVE"
        }
      ],
      "Expiration": {
        "Days": 365
      }
    }
  ]
}
```

**GCP Cloud Storage:**
```yaml
lifecycle:
  rule:
  - action:
      type: SetStorageClass
      storageClass: NEARLINE
    condition:
      age: 7
  - action:
      type: SetStorageClass
      storageClass: COLDLINE
    condition:
      age: 30
  - action:
      type: Delete
    condition:
      age: 365
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024-10-26 | System | Initial disaster recovery plan |

---

**Last Updated:** 2024-10-26  
**Next Review:** 2025-01-26 (Quarterly)
