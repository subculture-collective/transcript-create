"""add_archive_intelligence_tables

Revision ID: 20260602_1545_ai
Revises: 20260602_1530_archive_stats
Create Date: 2026-06-02 15:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260602_1545_ai"
down_revision: Union[str, None] = "20260602_1530_archive_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "archive_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'automatic'")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'published'")),
        sa.Column("is_editable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "archive_topic_aliases",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("weight", sa.Numeric(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "archive_topic_mentions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("segment_id", sa.BigInteger(), nullable=True),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("score", sa.Numeric(), nullable=False, server_default=sa.text("1")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("topic_id", "video_id", "segment_id", "start_ms", name="archive_topic_mentions_topic_video_segment_start_uq"),
    )
    op.create_table(
        "archive_topic_period_stats",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.Text(), nullable=False),
        sa.Column("granularity", sa.Text(), nullable=False, server_default=sa.text("'month'")),
        sa.Column("mention_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("video_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("recent_mentions_90d", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("trend_score", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("top_video_ids", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("topic_id", "period", "granularity", name="archive_topic_period_stats_topic_period_granularity_uq"),
    )
    op.create_table(
        "archive_period_summaries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("period", sa.Text(), nullable=False),
        sa.Column("granularity", sa.Text(), nullable=False, server_default=sa.text("'month'")),
        sa.Column("video_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_duration_seconds", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("period", "granularity", name="archive_period_summaries_period_granularity_uq"),
    )
    op.create_table(
        "archive_search_trends",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("period", sa.Text(), nullable=False),
        sa.Column("granularity", sa.Text(), nullable=False, server_default=sa.text("'week'")),
        sa.Column("search_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.Column("trend_score", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'search'")),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.execute("CREATE INDEX IF NOT EXISTS archive_topics_status_source_idx ON archive_topics (status, source)")
    op.execute("CREATE INDEX IF NOT EXISTS archive_topic_aliases_alias_lower_idx ON archive_topic_aliases (LOWER(alias))")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS archive_topic_aliases_topic_alias_lower_uidx ON archive_topic_aliases (topic_id, LOWER(alias))"
    )
    op.execute("CREATE INDEX IF NOT EXISTS archive_topic_mentions_topic_id_idx ON archive_topic_mentions (topic_id)")
    op.execute("CREATE INDEX IF NOT EXISTS archive_topic_mentions_video_id_idx ON archive_topic_mentions (video_id)")
    op.execute("CREATE INDEX IF NOT EXISTS archive_topic_mentions_occurred_at_idx ON archive_topic_mentions (occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS archive_topic_period_stats_period_trend_idx ON archive_topic_period_stats (period, trend_score DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS archive_search_trends_period_trend_idx ON archive_search_trends (period, trend_score DESC)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS archive_search_trends_term_period_granularity_uidx ON archive_search_trends (LOWER(term), period, granularity)"
    )


def downgrade() -> None:
    op.drop_table("archive_search_trends")
    op.drop_table("archive_period_summaries")
    op.drop_table("archive_topic_period_stats")
    op.drop_table("archive_topic_mentions")
    op.drop_table("archive_topic_aliases")
    op.drop_table("archive_topics")
