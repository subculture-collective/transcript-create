"""add_performance_indices

Add database indices for improved query performance on hot paths.

Revision ID: a1b2c3d4e5f6
Revises: 94e8fe9e40fa
Create Date: 2024-10-26 06:14:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "94e8fe9e40fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add performance indices for query optimization."""

    # Index for job queue ordering (worker hot path)
    # Covers the typical worker query: SELECT ... FROM jobs WHERE state IN (...) ORDER BY priority, created_at
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS jobs_queue_ordering_idx
        ON jobs(state, priority, created_at)
        """
    )

    # Partial index for pending/downloading jobs (very hot path for workers)
    # This index is smaller and faster for the most common worker queries
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS jobs_pending_idx
        ON jobs(created_at)
        WHERE state IN ('pending', 'downloading')
        """
    )

    # Index for user email lookups during authentication
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS users_email_idx
        ON users(email)
        """
    )

    # Composite index for quota checks (hot path for API rate limiting)
    # Covers: SELECT COUNT(*) FROM events WHERE user_id=? AND created_at >= ?
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS events_user_created_idx
        ON events(user_id, created_at DESC)
        """
    )

    # Index for session lookups (hot path for authentication)
    # Note: sessions_token_idx already exists, but we add an index on user_id for reverse lookups
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS sessions_user_id_idx
        ON sessions(user_id)
        """
    )


def downgrade() -> None:
    """Remove performance indices."""
    op.execute("DROP INDEX IF EXISTS sessions_user_id_idx")
    op.execute("DROP INDEX IF EXISTS events_user_created_idx")
    op.execute("DROP INDEX IF EXISTS users_email_idx")
    op.execute("DROP INDEX IF EXISTS jobs_pending_idx")
    op.execute("DROP INDEX IF EXISTS jobs_queue_ordering_idx")
