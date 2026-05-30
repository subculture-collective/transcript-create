"""add caption ingest state for staged channel jobs

Revision ID: 20260529_0425
Revises: 20260529_0315
Create Date: 2026-05-29 04:25:00.000000
"""

from alembic import op


revision = "20260529_0425"
down_revision = "20260529_0315"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE videos
        ADD COLUMN IF NOT EXISTS caption_ingest_state TEXT NOT NULL DEFAULT 'pending',
        ADD COLUMN IF NOT EXISTS caption_ingest_error TEXT
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'videos_caption_ingest_state_check'
            ) THEN
                ALTER TABLE videos
                ADD CONSTRAINT videos_caption_ingest_state_check
                CHECK (caption_ingest_state IN ('pending','running','completed','unavailable','failed','skipped'));
            END IF;
        END $$
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS videos_caption_ingest_state_idx ON videos(caption_ingest_state)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS videos_caption_ingest_state_idx")
    op.execute("ALTER TABLE videos DROP CONSTRAINT IF EXISTS videos_caption_ingest_state_check")
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS caption_ingest_error")
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS caption_ingest_state")
