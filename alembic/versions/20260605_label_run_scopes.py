"""add label extraction run scopes

Revision ID: 20260605_run_scopes
Revises: 20260605_people_role
Create Date: 2026-06-05 12:50:00.000000

"""

from collections.abc import Sequence
from typing import Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260605_run_scopes"
down_revision: Union[str, None] = "20260605_people_role"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("archive_extraction_runs_scope_check", "archive_extraction_runs", type_="check")
    op.create_check_constraint(
        "archive_extraction_runs_scope_check",
        "archive_extraction_runs",
        "scope IN ('video', 'video_title', 'batch', 'period', 'backfill')",
    )


def downgrade() -> None:
    op.drop_constraint("archive_extraction_runs_scope_check", "archive_extraction_runs", type_="check")
    op.create_check_constraint(
        "archive_extraction_runs_scope_check",
        "archive_extraction_runs",
        "scope IN ('video', 'batch', 'period', 'backfill')",
    )
