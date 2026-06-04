"""add_recurring_named_periods

Revision ID: 20260604_2100_recurring_periods
Revises: 20260604_1800_video_metadata
Create Date: 2026-06-04 21:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260604_2100_recurring_periods"
down_revision: Union[str, None] = "20260604_1800_video_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("archive_named_periods", sa.Column("recurring_month", sa.Integer(), nullable=True))
    op.add_column("archive_named_periods", sa.Column("recurring_day", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "archive_named_periods_recurring_month_check",
        "archive_named_periods",
        "recurring_month IS NULL OR (recurring_month >= 1 AND recurring_month <= 12)",
    )
    op.create_check_constraint(
        "archive_named_periods_recurring_day_check",
        "archive_named_periods",
        "recurring_day IS NULL OR (recurring_day >= 1 AND recurring_day <= 31)",
    )
    op.create_check_constraint(
        "archive_named_periods_recurring_pair_check",
        "archive_named_periods",
        "(recurring_month IS NULL AND recurring_day IS NULL) OR (recurring_month IS NOT NULL AND recurring_day IS NOT NULL)",
    )
    op.create_index(
        "archive_named_periods_recurring_date_idx",
        "archive_named_periods",
        ["recurring_month", "recurring_day"],
        unique=False,
    )
    op.execute("""
        UPDATE archive_named_periods
        SET status = 'hidden', updated_at = now()
        WHERE slug = 'christmas-2025' OR slug ~ '^[0-9]{4}-august-21$'
    """)
    op.execute("""
        INSERT INTO archive_named_periods (
            slug, label, kind, date_from, date_to, description, status, sort_order, recurring_month, recurring_day, created_at, updated_at
        ) VALUES
            ('christmas', 'Christmas', 'holiday', DATE '1970-12-25', DATE '1970-12-25', 'Christmas streams across every archive year', 'published', 719156, 12, 25, now(), now()),
            ('august-21', 'August 21', 'anniversary', DATE '1970-08-21', DATE '1970-08-21', 'August 21 streams across every archive year', 'published', 719030, 8, 21, now(), now())
        ON CONFLICT (slug) DO UPDATE SET
            label = EXCLUDED.label,
            kind = EXCLUDED.kind,
            date_from = EXCLUDED.date_from,
            date_to = EXCLUDED.date_to,
            description = EXCLUDED.description,
            status = EXCLUDED.status,
            sort_order = EXCLUDED.sort_order,
            recurring_month = EXCLUDED.recurring_month,
            recurring_day = EXCLUDED.recurring_day,
            updated_at = now()
    """)


def downgrade() -> None:
    op.drop_index("archive_named_periods_recurring_date_idx", table_name="archive_named_periods")
    op.drop_constraint("archive_named_periods_recurring_pair_check", "archive_named_periods", type_="check")
    op.drop_constraint("archive_named_periods_recurring_day_check", "archive_named_periods", type_="check")
    op.drop_constraint("archive_named_periods_recurring_month_check", "archive_named_periods", type_="check")
    op.drop_column("archive_named_periods", "recurring_day")
    op.drop_column("archive_named_periods", "recurring_month")
