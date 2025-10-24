"""add_videos_thumbnail_url_example

EXAMPLE MIGRATION - This demonstrates the migration workflow.
Add a thumbnail_url column to the videos table to store YouTube thumbnail URLs.

Revision ID: b7c3b2171954
Revises: 5cd038a8f131
Create Date: 2025-10-24 17:43:58.006081

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c3b2171954"
down_revision: Union[str, None] = "5cd038a8f131"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add thumbnail_url column to videos table."""
    # Add the new column
    op.execute("ALTER TABLE videos ADD COLUMN IF NOT EXISTS thumbnail_url TEXT")

    # Create an index to support queries filtering by thumbnail presence
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_videos_thumbnail_url ON videos(thumbnail_url) WHERE thumbnail_url IS NOT NULL"
    )


def downgrade() -> None:
    """Remove thumbnail_url column from videos table."""
    # Drop the index first
    op.execute("DROP INDEX IF EXISTS idx_videos_thumbnail_url")

    # Then drop the column
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS thumbnail_url")
