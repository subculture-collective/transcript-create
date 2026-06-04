"""add_video_metadata

Revision ID: 20260604_1800_video_metadata
Revises: 20260604_named_periods
Create Date: 2026-06-04 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260604_1800_video_metadata"
down_revision: Union[str, None] = "20260604_named_periods"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "archive_people",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("aliases", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'published'")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "archive_video_people",
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_people.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default=sa.text("'guest'")),
        sa.Column("confidence", sa.Text(), nullable=False, server_default=sa.text("'admin'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("video_id", "person_id", name="archive_video_people_pkey"),
    )
    op.create_table(
        "archive_video_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default=sa.text("'category'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'published'")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "archive_video_taggings",
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_video_tags.id", ondelete="CASCADE"), nullable=False),
        sa.Column("confidence", sa.Text(), nullable=False, server_default=sa.text("'admin'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("video_id", "tag_id", name="archive_video_taggings_pkey"),
    )

    op.create_index("ix_archive_people_status", "archive_people", ["status"], unique=False)
    op.create_index("ix_archive_video_people_video_id", "archive_video_people", ["video_id"], unique=False)
    op.create_index("ix_archive_video_people_person_id", "archive_video_people", ["person_id"], unique=False)
    op.create_index("ix_archive_video_tags_status", "archive_video_tags", ["status"], unique=False)
    op.create_index("ix_archive_video_taggings_video_id", "archive_video_taggings", ["video_id"], unique=False)
    op.create_index("ix_archive_video_taggings_tag_id", "archive_video_taggings", ["tag_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_archive_video_taggings_tag_id", table_name="archive_video_taggings")
    op.drop_index("ix_archive_video_taggings_video_id", table_name="archive_video_taggings")
    op.drop_index("ix_archive_video_tags_status", table_name="archive_video_tags")
    op.drop_index("ix_archive_video_people_person_id", table_name="archive_video_people")
    op.drop_index("ix_archive_video_people_video_id", table_name="archive_video_people")
    op.drop_index("ix_archive_people_status", table_name="archive_people")
    op.drop_table("archive_video_taggings")
    op.drop_table("archive_video_tags")
    op.drop_table("archive_video_people")
    op.drop_table("archive_people")
