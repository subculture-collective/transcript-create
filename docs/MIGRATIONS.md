# Database Migration Guide

This document provides a comprehensive guide to working with database migrations in the Transcript Create project.

## Quick Start

### For New Installations
```bash
# Apply all migrations
python scripts/run_migrations.py upgrade
```

### For Existing Installations
If you have a database that was created from `sql/schema.sql`:
```bash
# Stamp the database as being at the baseline
python scripts/run_migrations.py stamp head
```

## Why Migrations?

Before migrations, we applied `sql/schema.sql` directly to the database. This worked for initial setup but had limitations:

- No version control for schema changes
- No way to track which changes have been applied
- Difficult to coordinate schema changes across environments
- No built-in rollback mechanism
- Schema drift between environments

With Alembic migrations, we get:

✅ **Version Control**: Every schema change is tracked in a migration file  
✅ **Repeatability**: Same migrations produce same schema across environments  
✅ **Rollback**: Migrations can be reversed if needed  
✅ **CI/CD Integration**: Schema changes are tested automatically  
✅ **Documentation**: Each migration documents what changed and why  

## Common Operations

### Check Current Migration
```bash
python scripts/run_migrations.py current
```

### View Migration History
```bash
python scripts/run_migrations.py history
```

### Apply All Pending Migrations
```bash
python scripts/run_migrations.py upgrade
```

### Rollback One Migration
```bash
python scripts/run_migrations.py downgrade
```

### Create New Migration
```bash
alembic revision -m "descriptive_name"
```

## Creating Migrations

### Step 1: Create Migration File

```bash
alembic revision -m "add_column_to_videos"
```

This creates: `alembic/versions/YYYYMMDD_HHMM_abc123_add_column_to_videos.py`

### Step 2: Implement upgrade() and downgrade()

```python
def upgrade() -> None:
    """Add new column."""
    op.execute("ALTER TABLE videos ADD COLUMN thumbnail_url TEXT")

def downgrade() -> None:
    """Remove new column."""
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS thumbnail_url")
```

### Step 3: Test Locally

```bash
# Apply migration
python scripts/run_migrations.py upgrade

# Test downgrade
python scripts/run_migrations.py downgrade

# Re-apply
python scripts/run_migrations.py upgrade
```

## Best Practices

### DO ✅

- Test both upgrade and downgrade before committing
- Use IF EXISTS / IF NOT EXISTS for idempotency
- Keep migrations atomic - one logical change per migration
- Add descriptive comments for complex changes
- Run migrations as part of deployment

### DON'T ❌

- Never modify existing migrations once committed to main
- Don't skip migrations - always apply sequentially
- Don't mix DDL and data migrations
- Don't forget to test downgrade

## Common Scenarios

See [CONTRIBUTING.md](../CONTRIBUTING.md#database-migrations) for detailed examples of:
- Adding tables
- Adding columns
- Creating indexes
- Data migrations
- Enum changes

## Troubleshooting

### "Table already exists"
Database created from schema.sql - stamp it:
```bash
python scripts/run_migrations.py stamp head
```

### Migration Conflicts
Two migrations created simultaneously:
1. Pull latest main
2. Update your migration's `down_revision`
3. Test and commit

### Failed Migration
Either fix forward or rollback:
```bash
# Rollback
python scripts/run_migrations.py downgrade <previous_revision>

# Fix and re-apply
python scripts/run_migrations.py upgrade
```

## Resources

- [CONTRIBUTING.md - Database Migrations](../CONTRIBUTING.md#database-migrations)
- [alembic/README.md](../alembic/README.md)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
