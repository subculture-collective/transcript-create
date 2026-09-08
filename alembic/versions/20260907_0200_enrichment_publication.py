"""Auditable enrichment publication and legacy cleanup snapshots."""

from alembic import op

revision = "20260907_enrichment_publication"
down_revision = "20260907_enrichment_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE archive_enrichment_maintenance (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            operation text NOT NULL,
            reason text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        CREATE TABLE archive_enrichment_maintenance_rows (
            batch_id uuid NOT NULL REFERENCES archive_enrichment_maintenance(id),
            table_name text NOT NULL,
            row_id text NOT NULL,
            row_data jsonb NOT NULL,
            PRIMARY KEY(batch_id,table_name,row_id)
        );
        CREATE TABLE archive_enrichment_approvals (
            run_id uuid PRIMARY KEY REFERENCES archive_extraction_runs(id),
            reason text NOT NULL,
            snapshot jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        CREATE INDEX archive_enrichment_maintenance_row_lookup
            ON archive_enrichment_maintenance_rows(table_name,row_id);
        CREATE INDEX archive_enrichment_maintenance_video_lookup
            ON archive_enrichment_maintenance_rows((row_data->>'video_id'))
            WHERE table_name IN ('archive_video_chapters','archive_label_assignments');
    """)


def downgrade() -> None:
    op.execute("DROP TABLE archive_enrichment_approvals")
    op.execute("DROP TABLE archive_enrichment_maintenance_rows")
    op.execute("DROP TABLE archive_enrichment_maintenance")
