"""add_archive_named_periods

Revision ID: 20260604_named_periods
Revises: 20260602_1545_ai
Create Date: 2026-06-04 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260604_named_periods"
down_revision: Union[str, None] = "20260602_1545_ai"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "archive_named_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'published'")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "archive_named_period_stats",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_named_periods.id", ondelete="CASCADE"), nullable=False),
        sa.Column("video_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_duration_seconds", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("top_topics", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("representative_videos", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("summary", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("period_id", name="archive_named_period_stats_period_id_uq"),
    )

    op.create_index("archive_named_periods_kind_status_sort_idx", "archive_named_periods", ["kind", "status", "sort_order"], unique=False)
    op.create_index("archive_named_periods_date_range_idx", "archive_named_periods", ["date_from", "date_to"], unique=False)
    op.create_index("archive_named_periods_kind_idx", "archive_named_periods", ["kind"], unique=False)
    op.create_index("archive_named_periods_status_idx", "archive_named_periods", ["status"], unique=False)
    op.create_index("archive_named_period_stats_period_id_idx", "archive_named_period_stats", ["period_id"], unique=False)


def downgrade() -> None:
    op.drop_index("archive_named_period_stats_period_id_idx", table_name="archive_named_period_stats")
    op.drop_table("archive_named_period_stats")
    op.drop_index("archive_named_periods_status_idx", table_name="archive_named_periods")
    op.drop_index("archive_named_periods_kind_idx", table_name="archive_named_periods")
    op.drop_index("archive_named_periods_date_range_idx", table_name="archive_named_periods")
    op.drop_index("archive_named_periods_kind_status_sort_idx", table_name="archive_named_periods")
    op.drop_table("archive_named_periods")
