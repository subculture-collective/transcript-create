"""Auditable explicit enrichment recovery boundaries.

Revision ID: 20260907_enrichment_recovery
Revises: 20260906_enrichment_queue
"""
from alembic import op

revision = "20260907_enrichment_recovery"
down_revision = "20260906_enrichment_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE archive_enrichment_recoveries (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            model text NOT NULL,
            prompt text NOT NULL,
            previous_reason text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        CREATE INDEX archive_enrichment_recoveries_model_idx
          ON archive_enrichment_recoveries(model,prompt,created_at DESC);
    """)


def downgrade() -> None:
    op.drop_table("archive_enrichment_recoveries")
