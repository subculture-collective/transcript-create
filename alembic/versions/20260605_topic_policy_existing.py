"""require existing canonical for automatic topic labels

Revision ID: 20260605_topic_policy
Revises: 20260605_run_scopes
Create Date: 2026-06-05 18:30:00.000000

"""

from collections.abc import Sequence
from typing import Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260605_topic_policy"
down_revision: Union[str, None] = "20260605_run_scopes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE archive_label_policies
        SET require_existing_canonical = true,
            updated_at = now()
        WHERE label_kind = 'topic'
          AND unit_type = 'window'
          AND extraction_tier IN ('cheap', 'balanced', 'premium')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE archive_label_policies
        SET require_existing_canonical = false,
            updated_at = now()
        WHERE label_kind = 'topic'
          AND unit_type = 'window'
          AND extraction_tier IN ('cheap', 'balanced', 'premium')
        """
    )
