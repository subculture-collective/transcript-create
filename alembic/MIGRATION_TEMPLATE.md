# Migration Template and Examples

This document provides templates and examples for creating database migrations.

## Basic Template

When you run `alembic revision -m "description"`, it creates a file like this:

```python
"""<description>

Revision ID: abc123
Revises: xyz789
Create Date: 2025-10-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'abc123'
down_revision: Union[str, None] = 'xyz789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply schema changes.
    
    Describe what this migration does and why.
    Note any special deployment considerations.
    """
    pass


def downgrade() -> None:
    """Revert schema changes.
    
    Describe what this rollback does.
    Note if there's potential for data loss.
    """
    pass
```

## Example 1: Adding a Column

### Simple Column Addition

```python
"""Add thumbnail_url to videos table

Store YouTube video thumbnail URLs for faster UI rendering.

Revision ID: def456
Revises: abc123
Create Date: 2025-10-26 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'def456'
down_revision: Union[str, None] = 'abc123'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add thumbnail_url column to videos table."""
    # Add column as nullable - backwards compatible
    op.execute("ALTER TABLE videos ADD COLUMN IF NOT EXISTS thumbnail_url TEXT")


def downgrade() -> None:
    """Remove thumbnail_url column from videos table."""
    # Safe to drop - data loss is acceptable for thumbnails (can be re-fetched)
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS thumbnail_url")
```

### Column with Default Value

```python
"""Add processing_priority to jobs table

Allow prioritization of job processing by adding a priority field.

Revision ID: ghi789
Revises: def456
Create Date: 2025-10-26 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'ghi789'
down_revision: Union[str, None] = 'def456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add processing_priority column to jobs table with default value."""
    # Add column with default - existing rows get default value
    op.execute("""
        ALTER TABLE jobs 
        ADD COLUMN IF NOT EXISTS processing_priority INT NOT NULL DEFAULT 100
    """)


def downgrade() -> None:
    """Remove processing_priority column."""
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS processing_priority")
```

## Example 2: Adding a Table

```python
"""Add video_metadata table for extended video information

Store additional metadata about videos that doesn't fit in the main videos table.

Revision ID: jkl012
Revises: ghi789
Create Date: 2025-10-26 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'jkl012'
down_revision: Union[str, None] = 'ghi789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create video_metadata table."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS video_metadata (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            view_count BIGINT,
            like_count BIGINT,
            comment_count BIGINT,
            channel_id TEXT,
            category_id TEXT,
            tags TEXT[],
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    
    # Add indexes
    op.execute("""
        CREATE INDEX IF NOT EXISTS video_metadata_video_id_idx 
        ON video_metadata(video_id)
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS video_metadata_channel_id_idx 
        ON video_metadata(channel_id)
    """)


def downgrade() -> None:
    """Drop video_metadata table."""
    # Indexes are dropped automatically with CASCADE
    op.execute("DROP TABLE IF EXISTS video_metadata CASCADE")
```

## Example 3: Adding an Index

### Simple Index

```python
"""Add index on videos.created_at for faster date queries

Improve performance of queries filtering/sorting by video creation date.

Revision ID: mno345
Revises: jkl012
Create Date: 2025-10-26 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'mno345'
down_revision: Union[str, None] = 'jkl012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add index on videos.created_at."""
    op.execute("""
        CREATE INDEX IF NOT EXISTS videos_created_at_idx 
        ON videos(created_at DESC)
    """)


def downgrade() -> None:
    """Remove index on videos.created_at."""
    op.execute("DROP INDEX IF EXISTS videos_created_at_idx")
```

### Concurrent Index (Production-Safe)

```python
"""Add index on segments.video_id for faster lookups

Create index concurrently to avoid locking the segments table during creation.
This is critical for production where segments table is heavily used.

NOTE: This migration requires manual execution in production due to CONCURRENTLY.
See deployment notes below.

Revision ID: pqr678
Revises: mno345
Create Date: 2025-10-26 12:00:00.000000

Deployment Notes:
- Index will be created concurrently (no table lock)
- May take several minutes on large tables
- Can be run during normal operation
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'pqr678'
down_revision: Union[str, None] = 'mno345'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add concurrent index on segments for video lookups."""
    # Get connection to run outside transaction
    connection = op.get_bind()
    
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction
    # Commit any open transaction
    connection.execute("COMMIT")
    
    # Create index concurrently
    connection.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS segments_video_lookup_idx 
        ON segments(video_id, created_at DESC)
    """)


def downgrade() -> None:
    """Remove concurrent index."""
    connection = op.get_bind()
    connection.execute("COMMIT")
    connection.execute("DROP INDEX CONCURRENTLY IF EXISTS segments_video_lookup_idx")
```

## Example 4: Modifying an Enum

```python
"""Add 'archived' state to job_state enum

Support archiving of old completed jobs for data retention.

Revision ID: stu901
Revises: pqr678
Create Date: 2025-10-26 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'stu901'
down_revision: Union[str, None] = 'pqr678'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'archived' value to job_state enum."""
    # PostgreSQL ALTER TYPE to add enum value
    op.execute("ALTER TYPE job_state ADD VALUE IF NOT EXISTS 'archived'")


def downgrade() -> None:
    """Remove 'archived' value from job_state enum.
    
    WARNING: Cannot remove enum values in PostgreSQL without recreating the type.
    This downgrade will fail if any rows use 'archived' state.
    """
    # Check if any rows use 'archived'
    op.execute("""
        DO $$
        DECLARE
            archived_count INTEGER;
        BEGIN
            SELECT COUNT(*) INTO archived_count 
            FROM jobs 
            WHERE state = 'archived';
            
            IF archived_count > 0 THEN
                RAISE EXCEPTION 'Cannot downgrade: % jobs in archived state', archived_count;
            END IF;
        END $$;
    """)
    
    # Note: Actually removing the enum value requires recreating the type
    # For simplicity, we just verify no data uses it
    # In a real rollback, you might migrate 'archived' -> 'completed' first
```

## Example 5: Data Migration

```python
"""Backfill youtube_video_id from legacy youtube_id field

Copy data from old youtube_id column to new youtube_video_id column.
Process in batches to avoid locking table.

Revision ID: vwx234
Revises: stu901
Create Date: 2025-10-26 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = 'vwx234'
down_revision: Union[str, None] = 'stu901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill youtube_video_id from youtube_id in batches."""
    connection = op.get_bind()
    
    # Process in batches of 1000 to avoid long-running transactions
    batch_size = 1000
    total_updated = 0
    
    while True:
        result = connection.execute(
            text("""
                UPDATE videos
                SET youtube_video_id = youtube_id
                WHERE id IN (
                    SELECT id 
                    FROM videos 
                    WHERE youtube_video_id IS NULL 
                    AND youtube_id IS NOT NULL
                    LIMIT :batch_size
                )
            """),
            {"batch_size": batch_size}
        )
        
        rows_updated = result.rowcount
        total_updated += rows_updated
        
        if rows_updated == 0:
            break
        
        print(f"Backfilled {total_updated} rows...")
    
    print(f"Backfill complete: {total_updated} total rows updated")


def downgrade() -> None:
    """No downgrade needed - data migration is non-destructive."""
    # The new column youtube_video_id will be dropped in a separate migration
    # if needed. This migration only copies data.
    pass
```

## Example 6: Adding a Constraint

```python
"""Add unique constraint on users.email

Ensure email addresses are unique across users for better data integrity.

NOTE: Migration will fail if duplicate emails exist. Clean up data first.

Revision ID: yza567
Revises: vwx234
Create Date: 2025-10-26 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'yza567'
down_revision: Union[str, None] = 'vwx234'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint on users.email."""
    # First, check for duplicates
    op.execute("""
        DO $$
        DECLARE
            duplicate_count INTEGER;
        BEGIN
            SELECT COUNT(*) INTO duplicate_count
            FROM (
                SELECT email, COUNT(*) 
                FROM users 
                WHERE email IS NOT NULL
                GROUP BY email 
                HAVING COUNT(*) > 1
            ) dups;
            
            IF duplicate_count > 0 THEN
                RAISE EXCEPTION 'Cannot add unique constraint: % duplicate emails found', duplicate_count;
            END IF;
        END $$;
    """)
    
    # Add unique constraint
    op.execute("""
        ALTER TABLE users 
        ADD CONSTRAINT users_email_unique 
        UNIQUE (email)
    """)


def downgrade() -> None:
    """Remove unique constraint on users.email."""
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_unique")
```

## Example 7: Creating a Trigger

```python
"""Add auto-update trigger for videos.updated_at

Automatically update updated_at timestamp when videos are modified.

Revision ID: bcd890
Revises: yza567
Create Date: 2025-10-26 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'bcd890'
down_revision: Union[str, None] = 'yza567'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create trigger function and trigger for auto-updating videos.updated_at."""
    # Create the trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION update_videos_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create the trigger
    op.execute("""
        DROP TRIGGER IF EXISTS videos_updated_at_trigger ON videos;
        
        CREATE TRIGGER videos_updated_at_trigger
        BEFORE UPDATE ON videos
        FOR EACH ROW
        EXECUTE FUNCTION update_videos_updated_at();
    """)


def downgrade() -> None:
    """Remove trigger and function for videos.updated_at."""
    # Drop trigger
    op.execute("DROP TRIGGER IF EXISTS videos_updated_at_trigger ON videos")
    
    # Drop function
    op.execute("DROP FUNCTION IF EXISTS update_videos_updated_at()")
```

## Migration Best Practices

### 1. Always Use IF EXISTS / IF NOT EXISTS

Makes migrations idempotent and safe to retry:

```python
# Good
op.execute("ALTER TABLE videos ADD COLUMN IF NOT EXISTS thumbnail_url TEXT")
op.execute("CREATE INDEX IF NOT EXISTS idx_videos_thumbnail ON videos(thumbnail_url)")

# Bad
op.execute("ALTER TABLE videos ADD COLUMN thumbnail_url TEXT")
op.execute("CREATE INDEX idx_videos_thumbnail ON videos(thumbnail_url)")
```

### 2. Include Descriptive Docstrings

```python
def upgrade() -> None:
    """Add caching table for video metadata.
    
    This table stores cached metadata from YouTube API to reduce API calls.
    Cache entries expire after 24 hours (handled in application code).
    """
    pass
```

### 3. Consider Backwards Compatibility

```python
# Good: Add nullable column, make NOT NULL later if needed
op.execute("ALTER TABLE videos ADD COLUMN new_field TEXT")

# Bad: Add NOT NULL column immediately (requires default value)
op.execute("ALTER TABLE videos ADD COLUMN new_field TEXT NOT NULL")
```

### 4. Batch Large Updates

```python
# Good: Process in batches
batch_size = 1000
while True:
    result = connection.execute(
        text("UPDATE large_table SET field = value WHERE id IN (SELECT id FROM large_table WHERE condition LIMIT :limit)"),
        {"limit": batch_size}
    )
    if result.rowcount == 0:
        break

# Bad: Update all rows at once
op.execute("UPDATE large_table SET field = value WHERE condition")
```

### 5. Test Both Directions

Always test both upgrade and downgrade:

```bash
# Test upgrade
python scripts/run_migrations.py upgrade

# Verify changes
psql $DATABASE_URL -c "\d videos"

# Test downgrade
python scripts/run_migrations.py downgrade

# Verify reverted
psql $DATABASE_URL -c "\d videos"

# Re-apply
python scripts/run_migrations.py upgrade
```

## Common Pitfalls to Avoid

### ❌ Don't: Modify Existing Migrations

```python
# Never do this after migration is committed
def upgrade() -> None:
    op.execute("ALTER TABLE videos ADD COLUMN old_field TEXT")
    op.execute("ALTER TABLE videos ADD COLUMN new_field TEXT")  # Added later - WRONG!
```

### ✅ Do: Create New Migration

```python
# Create a new migration instead
def upgrade() -> None:
    op.execute("ALTER TABLE videos ADD COLUMN new_field TEXT")
```

### ❌ Don't: Mix DDL and Data

```python
# Don't do this
def upgrade() -> None:
    op.execute("ALTER TABLE videos ADD COLUMN status TEXT")
    op.execute("UPDATE videos SET status = 'active' WHERE state = 'completed'")
```

### ✅ Do: Separate Migrations

```python
# Migration 1: Schema
def upgrade() -> None:
    op.execute("ALTER TABLE videos ADD COLUMN status TEXT")

# Migration 2: Data (separate file)
def upgrade() -> None:
    op.execute("UPDATE videos SET status = 'active' WHERE state = 'completed'")
```

### ❌ Don't: Forget Downgrade

```python
# Incomplete migration
def upgrade() -> None:
    op.execute("ALTER TABLE videos ADD COLUMN new_field TEXT")

def downgrade() -> None:
    pass  # WRONG! Should remove the column
```

### ✅ Do: Implement Downgrade

```python
def upgrade() -> None:
    op.execute("ALTER TABLE videos ADD COLUMN new_field TEXT")

def downgrade() -> None:
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS new_field")
```

## Additional Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [PostgreSQL ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html)
- [Production Migration Guide](../docs/PRODUCTION_MIGRATIONS.md)
- [Contributing Guidelines](../CONTRIBUTING.md#database-migrations)
