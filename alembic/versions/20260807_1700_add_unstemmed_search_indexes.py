"""add unstemmed transcript search indexes

Revision ID: 20260807_unstemmed_search
Revises: 20260807_event_token
Create Date: 2026-08-07 17:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "20260807_unstemmed_search"
down_revision: Union[str, None] = "20260807_event_token"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS segments_text_simple_tsv_idx
            ON segments USING GIN (to_tsvector('simple', COALESCE(text, '')))
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS youtube_segments_text_simple_tsv_idx
            ON youtube_segments USING GIN (to_tsvector('simple', COALESCE(text, '')))
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS youtube_segments_text_simple_tsv_idx")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS segments_text_simple_tsv_idx")
