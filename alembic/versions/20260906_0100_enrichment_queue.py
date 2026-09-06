"""Durable review-only enrichment queue.

Revision ID: 20260906_enrichment_queue
Revises: 20260815_chapter_review
"""

from alembic import op

revision = "20260906_enrichment_queue"
down_revision = "20260815_chapter_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE archive_enrichment_queue_state (
            model text NOT NULL,
            prompt text NOT NULL,
            initialized_at timestamptz NOT NULL DEFAULT now(),
            paused_reason text,
            PRIMARY KEY (model, prompt)
        );
        CREATE TABLE archive_enrichment_jobs (
            video_id uuid NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            model text NOT NULL,
            prompt text NOT NULL,
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'retry', 'parked', 'completed')),
            new_arrival boolean NOT NULL DEFAULT false,
            attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            available_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            last_run_id uuid REFERENCES archive_extraction_runs(id) ON DELETE SET NULL,
            reason text,
            PRIMARY KEY (video_id, model, prompt)
        );
        CREATE INDEX archive_enrichment_jobs_ready_idx
            ON archive_enrichment_jobs(model, prompt, status, available_at);
        CREATE TABLE archive_enrichment_supersessions (
            run_id uuid PRIMARY KEY REFERENCES archive_extraction_runs(id) ON DELETE CASCADE,
            video_id uuid NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            reason text NOT NULL,
            candidates jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
    """)


def downgrade() -> None:
    op.drop_table("archive_enrichment_supersessions")
    op.drop_table("archive_enrichment_jobs")
    op.drop_table("archive_enrichment_queue_state")
