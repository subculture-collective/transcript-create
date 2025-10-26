# Database Migrations

This directory contains Alembic database migrations for managing schema evolution.

## Overview

We use [Alembic](https://alembic.sqlalchemy.org/) for database migrations to:

- Track schema changes over time
- Enable safe schema evolution across environments
- Provide repeatable, testable database deployments
- Support both forward (upgrade) and backward (downgrade) migrations

## Directory Structure

```
alembic/
├── versions/           # Migration files (one per schema change)
├── env.py             # Alembic environment configuration
├── script.py.mako     # Template for new migration files
└── README             # This file
```

## Migration Files

Migration files are stored in `versions/` and follow this naming pattern:

```
YYYYMMDD_HHMM_<revision_id>_<description>.py
```

Example: `20251024_1740_5cd038a8f131_initial_schema_baseline.py`

Each migration file contains:

- **Metadata**: Revision ID, parent revision, creation date
- **upgrade()**: Function to apply schema changes
- **downgrade()**: Function to revert schema changes

## Initial Migration

The baseline migration (`5cd038a8f131_initial_schema_baseline.py`) captures the existing schema from `sql/schema.sql`. This serves as the foundation for all future migrations.

### For New Deployments

Simply run migrations on an empty database:

```bash
python scripts/run_migrations.py upgrade
```

### For Existing Deployments

If you have an existing database created from `sql/schema.sql`, stamp it at the baseline:

```bash
python scripts/run_migrations.py stamp head
```

This tells Alembic your database is already at the baseline, preventing it from trying to re-create existing tables.

## Creating Migrations

See the [Database Migrations](../CONTRIBUTING.md#database-migrations) section in CONTRIBUTING.md for detailed guidelines on:

- Creating new migrations
- Testing migrations
- Best practices
- Common scenarios
- Example code

## CI/CD Integration

Migrations are automatically validated in CI via `.github/workflows/migrations-ci.yml`:

- Fresh database test (empty → fully migrated)
- Existing schema test (stamp → no-op upgrade)
- Up/down test (upgrade → downgrade → upgrade)

All tests must pass before changes can be merged.

## Docker Compose

When running with Docker Compose, migrations are automatically applied on startup:

```bash
docker compose up -d
```

The `migrations` service runs `python scripts/run_migrations.py upgrade` before the API and worker services start.

## Manual Migration Operations

### Check Current Revision

```bash
python scripts/run_migrations.py current
```

### View Migration History

```bash
python scripts/run_migrations.py history
```

### Upgrade to Latest

```bash
python scripts/run_migrations.py upgrade
```

### Downgrade One Revision

```bash
python scripts/run_migrations.py downgrade
```

### Create New Migration

```bash
alembic revision -m "descriptive_name"
```

## Important Notes

1. **Never modify existing migrations** once they're committed and deployed
2. **Always test both upgrade and downgrade** before committing
3. **Keep migrations atomic** - one logical change per migration
4. **Document complex migrations** with comments
5. **Consider data safety** - migrations can delete data if not careful
6. **Test with production-like data** when possible

## Troubleshooting

### "Table already exists" error

Your database may have been created from `sql/schema.sql`. Stamp it:

```bash
python scripts/run_migrations.py stamp head
```

### "Can't locate revision" error

The `alembic_version` table may be out of sync. Check current revision:

```bash
python scripts/run_migrations.py current
```

### Migration conflicts

If multiple people create migrations simultaneously, you may need to merge them:

1. Rebase your branch
2. Update the `down_revision` in your migration to point to the latest
3. Test the migration sequence

## Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Contributing Guidelines](../CONTRIBUTING.md)
- [Migration CI Workflow](../.github/workflows/migrations-ci.yml)
