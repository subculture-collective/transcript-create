"""
Add transcript_id to segments and add 'expanded' to job_state enum.

Revision ID: 20251102_01
Revises:
Create Date: 2025-11-02
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251102_01"
down_revision = "merge_multiple_heads_20251031"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Add transcript_id and idx columns and FK to transcripts
    with op.batch_alter_table("segments") as batch_op:
        batch_op.add_column(sa.Column("transcript_id", sa.UUID(), nullable=True))
        batch_op.add_column(sa.Column("idx", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "segments_transcript_id_fkey",
        source_table="segments",
        referent_table="transcripts",
        local_cols=["transcript_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # 2) Create trigger to backfill video_id when transcript_id is provided on insert
    op.execute(
        """
        CREATE OR REPLACE FUNCTION segments_set_video_from_transcript() RETURNS trigger AS $$
        BEGIN
            IF NEW.transcript_id IS NOT NULL AND NEW.video_id IS NULL THEN
                SELECT t.video_id INTO NEW.video_id FROM transcripts t WHERE t.id = NEW.transcript_id;
            END IF;
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            BEGIN
                CREATE TRIGGER segments_set_video_from_transcript_tr
                BEFORE INSERT ON segments
                FOR EACH ROW EXECUTE FUNCTION segments_set_video_from_transcript();
            EXCEPTION WHEN duplicate_object THEN NULL;
            END;
        END $$;
        """
    )

    # 3) Add 'expanded' to job_state enum if missing
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                WHERE t.typname = 'job_state' AND e.enumlabel = 'expanded'
            ) THEN
                ALTER TYPE job_state ADD VALUE 'expanded';
            END IF;
        END
        $$;
        """
    )


def downgrade():
    # Best-effort downgrade: drop trigger and function, keep column/enum additions as they are not safely removable
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'segments_set_video_from_transcript_tr'
            ) THEN
                DROP TRIGGER segments_set_video_from_transcript_tr ON segments;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS segments_set_video_from_transcript();
        """
    )
    try:
        op.drop_constraint("segments_transcript_id_fkey", table_name="segments", type_="foreignkey")
    except Exception:
        # Ignore errors if the constraint does not exist; this is a best-effort downgrade.
        pass
    try:
        with op.batch_alter_table("segments") as batch_op:
            batch_op.drop_column("transcript_id")
            batch_op.drop_column("idx")
    except Exception:
        # Ignore errors if the columns do not exist; this is a best-effort downgrade.
        pass
