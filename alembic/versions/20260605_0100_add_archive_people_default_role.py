"""add_archive_people_default_role

Revision ID: 20260605_people_role
Revises: 20260604_2300_label_extraction
Create Date: 2026-06-05 01:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260605_people_role"
down_revision: Union[str, None] = "20260604_2300_label_extraction"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("archive_people", sa.Column("default_role", sa.Text(), nullable=True))
    op.create_check_constraint(
        "archive_people_default_role_check",
        "archive_people",
        "default_role IS NULL OR default_role IN ('guest', 'host', 'caller', 'subject', 'mentioned')",
    )


def downgrade() -> None:
    op.drop_constraint("archive_people_default_role_check", "archive_people", type_="check")
    op.drop_column("archive_people", "default_role")
