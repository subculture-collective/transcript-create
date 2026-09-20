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

### [Analytics Privacy and Credential Removal](analytics-privacy.md)
Deployment order, credential scrub/session rotation, the temporary legacy-write
guard, 90-day raw-event retention, and the roll-forward-only boundary.

### [Blocking Dependency and SAST Gates](security-gates.md)
Canonical pip-audit, Bandit, and npm-audit commands plus the expiring exception
contract.

### [Private Beta Deployment](../deployment/private-beta.md)
Digest-pinned deployment, ingress isolation, WAL-G restore rehearsal,
migration ordering, release evidence, and operator approval gates.

## Local and generic-stack quick links

> **Do not run the direct Compose examples below on a production deployment
> that uses the guarded release helper.** They are retained for local or generic
> stacks. Guarded production changes must follow the
> [private-beta deployment runbook](../deployment/private-beta.md) and use only
> the named, preflighted actions exposed by `scripts/compose_prod.sh`. Restore
> rehearsals run on the isolated staging host described by that runbook.

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
