"""add transcript blocks

Revision ID: 20260529_0600
Revises: 20260529_0425
Create Date: 2026-05-29 06:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260529_0600"
down_revision = "20260529_0425"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transcript_blocks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("speaker_label", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "segment_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("kind", sa.Text(), nullable=False, server_default="paragraph"),
        sa.Column("formatter_version", sa.Text(), nullable=False, server_default="rule-v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.CheckConstraint("kind IN ('paragraph', 'speaker_turn')", name="transcript_blocks_kind_check"),
        sa.UniqueConstraint("video_id", "block_index", name="transcript_blocks_video_index_unique"),
    )
    op.create_index("transcript_blocks_video_idx", "transcript_blocks", ["video_id"])
    op.create_index("transcript_blocks_video_time_idx", "transcript_blocks", ["video_id", "start_ms"])


def downgrade() -> None:
    op.drop_index("transcript_blocks_video_time_idx", table_name="transcript_blocks")
    op.drop_index("transcript_blocks_video_idx", table_name="transcript_blocks")
    op.drop_table("transcript_blocks")
