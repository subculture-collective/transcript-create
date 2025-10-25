"""add_worker_heartbeat_table

Revision ID: 90627b497f59
Revises: b7c3b2171954
Create Date: 2025-10-25 23:02:10.967538

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '90627b497f59'
down_revision: Union[str, None] = 'b7c3b2171954'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add worker_heartbeat table for health monitoring."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS worker_heartbeat (
            id SERIAL PRIMARY KEY,
            worker_id TEXT NOT NULL,
            hostname TEXT,
            pid INT,
            last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
            metrics JSONB DEFAULT '{}'::jsonb,
            UNIQUE (worker_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS worker_heartbeat_last_seen_idx ON worker_heartbeat(last_seen)")


def downgrade() -> None:
    """Remove worker_heartbeat table."""
    op.execute("DROP TABLE IF EXISTS worker_heartbeat")
