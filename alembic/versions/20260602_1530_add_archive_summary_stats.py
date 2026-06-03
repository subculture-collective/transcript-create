"""add_archive_summary_stats

Revision ID: 20260602_1530_archive_stats
Revises: 20260531_1200_saved_searches
Create Date: 2026-06-02 15:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260602_1530_archive_stats"
down_revision: Union[str, None] = "20260531_1200_saved_searches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "archive_summary_stats",
        sa.Column("id", sa.Text(), primary_key=True, server_default=sa.text("'default'")),
        sa.Column("video_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duration_seconds", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("transcript_word_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("archive_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("archive_summary_stats")
