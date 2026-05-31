"""add_saved_searches_table

Revision ID: 20260531_1200_saved_searches
Revises: 20260529_0600
Create Date: 2026-05-31 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260531_1200_saved_searches"
down_revision: Union[str, None] = "20260529_0600"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_searches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "query", name="saved_searches_user_query_key"),
    )
    op.create_index("saved_searches_user_id_created_at_idx", "saved_searches", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("saved_searches_user_id_created_at_idx", table_name="saved_searches")
    op.drop_table("saved_searches")
