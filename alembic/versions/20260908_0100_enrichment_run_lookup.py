"""Bound approval lookups to the generating LLM run."""

from alembic import op

revision = "20260908_enrichment_run_lookup"
down_revision = "20260907_enrichment_publication"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX archive_enrichment_assignment_run_lookup
            ON archive_label_assignments(run_id, id) WHERE source = 'llm';
    """)


def downgrade() -> None:
    op.execute("DROP INDEX archive_enrichment_assignment_run_lookup")
