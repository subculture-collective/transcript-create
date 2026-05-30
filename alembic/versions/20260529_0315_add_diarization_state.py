"""add diarization state columns

Revision ID: 20260529_0315
Revises: 003_transcript_cleanup
Create Date: 2026-05-29 03:15:00.000000
"""

from alembic import op


revision = "20260529_0315"
down_revision = "003_transcript_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE videos
        ADD COLUMN IF NOT EXISTS diarization_state TEXT NOT NULL DEFAULT 'pending',
        ADD COLUMN IF NOT EXISTS diarization_error TEXT
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'videos_diarization_state_check'
            ) THEN
                ALTER TABLE videos
                ADD CONSTRAINT videos_diarization_state_check
                CHECK (diarization_state IN ('pending','running','completed','failed','skipped'));
            END IF;
        END $$
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS videos_diarization_state_idx ON videos(diarization_state)")
    op.execute(
        """
        UPDATE videos
        SET diarization_state = CASE
            WHEN state = 'completed' THEN 'pending'
            WHEN state = 'failed' THEN 'skipped'
            ELSE diarization_state
        END
        WHERE diarization_state IS NULL OR diarization_state = 'pending'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS videos_diarization_state_idx")
    op.execute("ALTER TABLE videos DROP CONSTRAINT IF EXISTS videos_diarization_state_check")
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS diarization_error")
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS diarization_state")
