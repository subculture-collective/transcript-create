# Production Database Migration Runbook

This document provides comprehensive procedures for safely applying database migrations in production environments.

## Pre-Migration Checklist

Before running any migration in production:

- [ ] **Backup database** - Create a full database backup
- [ ] **Review migration code** - Ensure migrations have been reviewed and approved
- [ ] **Test in staging** - Apply and test migrations in a production-like staging environment
- [ ] **Check disk space** - Ensure sufficient disk space for the migration (indexes, new columns, etc.)
- [ ] **Verify dependencies** - Confirm application code is compatible with both old and new schema
- [ ] **Plan maintenance window** - Schedule during low-traffic period if downtime is required
- [ ] **Notify stakeholders** - Alert team members and users if necessary
- [ ] **Prepare rollback plan** - Know how to revert the migration if issues occur

## Migration Execution Steps

### Step 1: Pre-Migration Backup

```bash
# Create a full database backup
export TIMESTAMP=$(date +%Y%m%d_%H%M%S)
export BACKUP_FILE="transcripts_backup_${TIMESTAMP}.dump"

# Using pg_dump
pg_dump -h <host> -U <user> -d transcripts -F c -f ${BACKUP_FILE}

# Verify backup file exists and has reasonable size
ls -lh ${BACKUP_FILE}

# Optional: Test restore to a temporary database
createdb transcripts_restore_test
pg_restore -h <host> -U <user> -d transcripts_restore_test ${BACKUP_FILE}
dropdb transcripts_restore_test
```

### Step 2: Verify Current State

```bash
# Check current migration revision
python scripts/run_migrations.py current

# View pending migrations
python scripts/run_migrations.py history | grep -A 5 "head"

# Verify database health
psql $DATABASE_URL -c "SELECT pg_database_size('transcripts');"
psql $DATABASE_URL -c "SELECT count(*) FROM jobs;"
psql $DATABASE_URL -c "SELECT count(*) FROM videos;"
```

### Step 3: Run Migrations

**Option A: Zero Downtime (Recommended)**
```bash
# Ensure application is compatible with both old and new schema
# Run migrations while application is live
python scripts/run_migrations.py upgrade

# Monitor logs for errors
tail -f /var/log/app.log
```

**Option B: With Downtime**
```bash
# Stop application services
docker compose stop api worker
# or: systemctl stop transcript-api transcript-worker

# Run migrations
python scripts/run_migrations.py upgrade

# Verify schema changes
psql $DATABASE_URL -c "\dt"
psql $DATABASE_URL -c "\di"  # Check indexes

# Start application services
docker compose start api worker
# or: systemctl start transcript-api transcript-worker
```

### Step 4: Post-Migration Verification

```bash
# Verify migration applied
python scripts/run_migrations.py current

# Check application health
curl http://localhost:8000/health

# Verify database functions
psql $DATABASE_URL << EOF
-- Check triggers still work
SELECT tgname, tgtype FROM pg_trigger WHERE tgname LIKE '%tsv%';

-- Check indexes are valid
SELECT schemaname, tablename, indexname, indexdef 
FROM pg_indexes 
WHERE schemaname = 'public' 
ORDER BY tablename, indexname;

-- Check foreign key constraints
SELECT conname, conrelid::regclass, confrelid::regclass, contype
FROM pg_constraint
WHERE contype = 'f';
EOF

# Monitor application logs for errors
docker compose logs -f --tail=100 api worker

# Test core functionality
curl -X POST http://localhost:8000/jobs -H "Content-Type: application/json" -d '{"kind":"single","input_url":"https://youtube.com/watch?v=test"}'
```

### Step 5: Monitor Production

```bash
# Watch for errors in logs
docker compose logs -f api worker | grep -i error

# Monitor database performance
psql $DATABASE_URL << EOF
SELECT 
    schemaname,
    tablename,
    n_tup_ins as inserts,
    n_tup_upd as updates,
    n_tup_del as deletes
FROM pg_stat_user_tables
ORDER BY tablename;
EOF

# Check for slow queries
psql $DATABASE_URL << EOF
SELECT 
    query,
    calls,
    total_exec_time / 1000 as total_seconds,
    mean_exec_time / 1000 as mean_seconds
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
EOF
```

## Rollback Procedures

### Scenario 1: Migration Failed During Execution

```bash
# If migration fails, Alembic typically rolls back automatically
# Check current state
python scripts/run_migrations.py current

# If partially applied, manually downgrade
python scripts/run_migrations.py downgrade -1

# Investigate error
docker compose logs migrations
```

### Scenario 2: Migration Succeeded but Application Issues

```bash
# Downgrade the migration
python scripts/run_migrations.py downgrade -1

# Verify downgrade
python scripts/run_migrations.py current

# Restart services with old schema
docker compose restart api worker
```

### Scenario 3: Data Corruption or Critical Issues

```bash
# Stop all services immediately
docker compose stop api worker

# Restore from backup
dropdb transcripts
createdb transcripts
pg_restore -h <host> -U <user> -d transcripts ${BACKUP_FILE}

# Verify restore
psql $DATABASE_URL -c "SELECT count(*) FROM jobs;"

# Stamp database at backup revision
python scripts/run_migrations.py current  # Check what revision backup was at
python scripts/run_migrations.py stamp <revision_id>

# Restart services
docker compose start api worker
```

## Zero-Downtime Migration Patterns

### Pattern 1: Adding a Column (Safe)

```python
def upgrade() -> None:
    """Add new optional column."""
    # Add column as nullable initially
    op.execute("ALTER TABLE videos ADD COLUMN thumbnail_url TEXT")

def downgrade() -> None:
    """Remove column."""
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS thumbnail_url")
```

**Deployment:**
1. Deploy migration (column added as nullable)
2. Deploy new code that uses the column
3. Optionally backfill data in a follow-up migration
4. Optionally add NOT NULL constraint in another migration if needed

### Pattern 2: Removing a Column (Requires Coordination)

**Phase 1 - Stop Writing:**
```python
def upgrade() -> None:
    """Stop using column (no schema change yet)."""
    pass  # Deploy code that doesn't write to column

def downgrade() -> None:
    pass
```

**Phase 2 - Remove Column:**
```python
def upgrade() -> None:
    """Remove unused column."""
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS old_field")

def downgrade() -> None:
    """Restore column."""
    op.execute("ALTER TABLE videos ADD COLUMN old_field TEXT")
```

**Deployment:**
1. Deploy code that stops writing to column
2. Wait for in-flight requests to complete
3. Deploy migration that removes column

### Pattern 3: Adding an Index (Can Be Slow)

```python
def upgrade() -> None:
    """Add index concurrently to avoid locks."""
    # CONCURRENT requires autocommit mode
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_videos_created ON videos(created_at)")

def downgrade() -> None:
    """Remove index."""
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_videos_created")
```

**Note:** `CREATE INDEX CONCURRENTLY` cannot run inside a transaction block. You may need to set:
```python
# In migration file
revision = "abc123"
down_revision = "xyz789"

def upgrade() -> None:
    # Get connection and set isolation level
    connection = op.get_bind()
    connection.execute("COMMIT")  # End current transaction
    connection.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_videos_created ON videos(created_at)")

def downgrade() -> None:
    connection = op.get_bind()
    connection.execute("COMMIT")
    connection.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_videos_created")
```

### Pattern 4: Renaming a Column (Requires Multiple Phases)

**Phase 1 - Add New Column:**
```python
def upgrade() -> None:
    """Add new column with better name."""
    op.execute("ALTER TABLE videos ADD COLUMN youtube_video_id TEXT")

def downgrade() -> None:
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS youtube_video_id")
```

**Phase 2 - Dual Write:**
Deploy code that writes to both `youtube_id` and `youtube_video_id`.

**Phase 3 - Backfill:**
```python
def upgrade() -> None:
    """Copy data from old to new column."""
    op.execute("UPDATE videos SET youtube_video_id = youtube_id WHERE youtube_video_id IS NULL")

def downgrade() -> None:
    pass  # Data stays in new column
```

**Phase 4 - Switch Read:**
Deploy code that reads from `youtube_video_id`.

**Phase 5 - Remove Old Column:**
```python
def upgrade() -> None:
    """Remove old column."""
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS youtube_id")

def downgrade() -> None:
    op.execute("ALTER TABLE videos ADD COLUMN youtube_id TEXT")
```

## Blue-Green Deployment Considerations

### Database Schema Compatibility

When using blue-green deployments, both versions of the application must work with the same database schema during the switchover period.

**Strategy:**
1. **Backwards-compatible changes only**: New schema must work with old code
2. **Deploy schema first**: Apply migrations before deploying new application version
3. **Graceful degradation**: Old application should handle new columns/tables gracefully
4. **Forward-compatible**: Old code should work with new schema

### Example: Adding a Table

```python
def upgrade() -> None:
    """Add new feature table."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS new_feature (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            video_id UUID REFERENCES videos(id) ON DELETE CASCADE,
            data JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

def downgrade() -> None:
    """Remove feature table."""
    op.execute("DROP TABLE IF EXISTS new_feature CASCADE")
```

**Deployment:**
1. Apply migration (old code ignores new table)
2. Deploy new code (uses new table)
3. Verify functionality
4. Switch traffic to new deployment
5. Decommission old deployment

## Performance Considerations

### Large Table Migrations

For tables with millions of rows:

**DO:**
- Use `ADD COLUMN ... DEFAULT NULL` (instant in PostgreSQL 11+)
- Create indexes with `CONCURRENTLY` option
- Batch large updates in data migrations
- Test on production-sized dataset first
- Monitor query performance after migration

**DON'T:**
- Use `ADD COLUMN ... DEFAULT <value>` without NOT NULL (requires full table rewrite in older PostgreSQL)
- Create indexes without CONCURRENTLY (locks table)
- Update all rows in a single transaction
- Add constraints without validation

### Testing Performance

```bash
# Create production-sized test database
pg_dump -h prod-host -U user -d transcripts -F c > prod_backup.dump
createdb transcripts_perf_test
pg_restore -d transcripts_perf_test prod_backup.dump

# Test migration performance
export DATABASE_URL="postgresql+psycopg://user:pass@localhost/transcripts_perf_test"
time python scripts/run_migrations.py upgrade

# Check table sizes
psql $DATABASE_URL << EOF
SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
EOF
```

## Common Issues and Solutions

### Issue: Migration Hangs

**Symptoms:** Migration runs but never completes

**Causes:**
- Table locked by long-running query
- Index creation on large table
- Transaction waiting for locks

**Solutions:**
```bash
# Check for locks
psql $DATABASE_URL << EOF
SELECT 
    pid,
    usename,
    application_name,
    state,
    query,
    age(clock_timestamp(), query_start) AS age
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY age DESC;
EOF

# Check blocking queries
psql $DATABASE_URL << EOF
SELECT
    blocked.pid AS blocked_pid,
    blocked.query AS blocked_query,
    blocking.pid AS blocking_pid,
    blocking.query AS blocking_query
FROM pg_stat_activity blocked
JOIN pg_stat_activity blocking 
    ON blocking.pid = ANY(pg_blocking_pids(blocked.pid));
EOF

# If necessary, terminate blocking query
psql $DATABASE_URL -c "SELECT pg_terminate_backend(<pid>);"
```

### Issue: Out of Disk Space

**Prevention:**
```bash
# Check disk space before migration
df -h /var/lib/postgresql

# Estimate index size
psql $DATABASE_URL << EOF
SELECT pg_size_pretty(pg_relation_size('segments')) AS table_size;
-- Index will be approximately same size as table
EOF
```

**Recovery:**
- Free up disk space
- Migrate to larger volume
- Drop unused indexes/tables

### Issue: Migration Succeeds but Application Fails

**Diagnosis:**
```bash
# Check application logs
docker compose logs api worker | grep -i error

# Verify schema matches expectations
psql $DATABASE_URL -c "\d videos"
```

**Solutions:**
- Rollback migration: `python scripts/run_migrations.py downgrade -1`
- Fix application code
- Create corrective migration

## Migration Review Checklist

Before merging a migration PR:

- [ ] **Code Review**
  - [ ] Both `upgrade()` and `downgrade()` implemented
  - [ ] SQL syntax is correct
  - [ ] Uses IF EXISTS/IF NOT EXISTS for idempotency
  - [ ] No hardcoded values (use config/settings)

- [ ] **Testing**
  - [ ] Tests pass in CI
  - [ ] Manual upgrade/downgrade tested locally
  - [ ] Tested with sample data
  - [ ] Tested on production-sized dataset (if applicable)

- [ ] **Performance**
  - [ ] Estimated migration duration documented
  - [ ] Large table modifications use appropriate techniques
  - [ ] Indexes created with CONCURRENTLY if needed

- [ ] **Safety**
  - [ ] No data loss in downgrade (if possible)
  - [ ] Backwards compatible with current code
  - [ ] No breaking changes without coordination

- [ ] **Documentation**
  - [ ] Migration purpose documented in docstring
  - [ ] Special deployment instructions noted
  - [ ] Related to issue/ticket

## Emergency Contacts

In case of migration issues:

1. **Check CI logs**: GitHub Actions logs for migration tests
2. **Check application logs**: `docker compose logs api worker`
3. **Check database logs**: `docker compose logs db`
4. **Database health**: `curl http://localhost:8000/health`
5. **Rollback**: Follow rollback procedures above

## Additional Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [PostgreSQL ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html)
- [PostgreSQL CREATE INDEX CONCURRENTLY](https://www.postgresql.org/docs/current/sql-createindex.html#SQL-CREATEINDEX-CONCURRENTLY)
- [Zero-Downtime Database Migrations](https://autumn.revolt.chat/attachments/01HTGWBP2H9E2X2JZF8N6NKQPD)
- [Project Migration Guide](./MIGRATIONS.md)
- [Contributing - Database Migrations](../CONTRIBUTING.md#database-migrations)
