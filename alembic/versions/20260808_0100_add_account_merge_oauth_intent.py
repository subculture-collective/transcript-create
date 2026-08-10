"""add account merge OAuth intent

Revision ID: 20260808_account_merge
Revises: 20260807_unstemmed_search
Create Date: 2026-08-08 21:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "20260808_account_merge"
down_revision: Union[str, None] = "20260807_unstemmed_search"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE oauth_requests DROP CONSTRAINT oauth_requests_intent_check")
    op.execute("ALTER TABLE oauth_requests DROP CONSTRAINT oauth_requests_check")
    op.execute(
        """
        ALTER TABLE oauth_requests
        ADD CONSTRAINT oauth_requests_intent_check
        CHECK (intent IN ('login', 'link', 'merge'))
        """
    )
    op.execute(
        """
        ALTER TABLE oauth_requests
        ADD CONSTRAINT oauth_requests_binding_check
        CHECK ((intent = 'login' AND link_user_id IS NULL)
            OR (intent IN ('link', 'merge') AND link_user_id IS NOT NULL))
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM oauth_requests WHERE intent = 'merge'")
    op.execute("ALTER TABLE oauth_requests DROP CONSTRAINT oauth_requests_binding_check")
    op.execute("ALTER TABLE oauth_requests DROP CONSTRAINT oauth_requests_intent_check")
    op.execute(
        """
        ALTER TABLE oauth_requests
        ADD CONSTRAINT oauth_requests_intent_check
        CHECK (intent IN ('login', 'link'))
        """
    )
    op.execute(
        """
        ALTER TABLE oauth_requests
        ADD CONSTRAINT oauth_requests_check
        CHECK ((intent = 'login' AND link_user_id IS NULL)
            OR (intent = 'link' AND link_user_id IS NOT NULL))
        """
    )
