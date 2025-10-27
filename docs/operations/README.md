# Operations Documentation

This directory contains operational documentation for the transcript-create system.

## Available Documentation

### [Disaster Recovery Plan](disaster-recovery.md)
Comprehensive disaster recovery procedures including:
- Backup strategy (database, media, WAL archives)
- Recovery procedures (full restore, PITR, media recovery)
- Disaster scenario runbooks (corruption, deletion, server failure, ransomware)
- Testing and drill procedures
- RTO/RPO objectives and monitoring

### [Backup Operations Runbook](backup-operations.md)
Day-to-day backup operations guide including:
- Daily operational procedures
- Backup script usage and examples
- Monitoring and alerting setup
- Troubleshooting common issues
- Maintenance tasks (weekly, monthly, quarterly)
- Cloud storage operations

## Quick Links

### Running Backups

```bash
# Manual database backup
docker compose exec backup bash -c "cd /scripts && ./backup_db.sh"

# Manual media backup
docker compose exec backup bash -c "cd /scripts && ./backup_media.sh"

# Verify backups
docker compose exec backup bash -c "cd /scripts && ./verify_backup.sh"
```

### Restoring from Backup

```bash
# List available backups
docker compose exec backup bash -c "cd /scripts && ./restore_db.sh --list-backups"

# Restore from specific backup
docker compose exec backup bash -c "cd /scripts && ./restore_db.sh --backup-file /backups/daily/transcripts_daily_YYYYMMDD_HHMMSS.sql.gz"
```

### Monitoring

- **Grafana Dashboard:** http://localhost:3000 (see "Backup & Disaster Recovery" dashboard)
- **Prometheus Alerts:** Configured in `config/prometheus/alerts.yml`
- **Backup Logs:** `/backups/logs/`

## Backup Schedule

| Task | Schedule | Script |
|------|----------|--------|
| Database Backup | Daily 2:00 AM UTC | `backup_db.sh` |
| Media Backup | Daily 3:00 AM UTC | `backup_media.sh` |
| Backup Verification | Weekly Sunday 4:00 AM UTC | `verify_backup.sh` |
| Metrics Export | Every 5 minutes | `export_backup_metrics.sh` |

## Recovery Objectives

- **RTO (Recovery Time Objective):** < 1 hour
- **RPO (Recovery Point Objective):** < 5 minutes (with WAL archiving)

## Support

For issues or questions:
1. Check the [troubleshooting section](backup-operations.md#troubleshooting) in the operations runbook
2. Review backup logs in `/backups/logs/`
3. Check Prometheus alerts and Grafana dashboards
4. Refer to the disaster recovery plan for emergency procedures
