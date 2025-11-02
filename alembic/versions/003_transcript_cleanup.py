"""Add transcript cleanup support

Revision ID: 003_transcript_cleanup
Revises: 002_advanced_features
Create Date: 2025-11-02 23:12:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "003_transcript_cleanup"
down_revision = "002_advanced_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add columns to support transcript cleanup features.
    
    This migration is OPTIONAL. The cleanup system can work without these columns
    by computing cleaned text on-demand. However, adding these columns enables:
    - Caching of cleaned transcripts for faster retrieval
    - Storing cleanup configuration used for each transcript
    - Tracking cleanup statistics
    """
    
    # Add cleanup metadata to transcripts table
    op.execute(
        """
        ALTER TABLE transcripts
        ADD COLUMN IF NOT EXISTS cleanup_config JSONB;
    """
    )
    
    op.execute(
        """
        ALTER TABLE transcripts
        ADD COLUMN IF NOT EXISTS is_cleaned BOOLEAN DEFAULT false;
    """
    )
    
    # Add cleaned text column to segments table
    # This allows caching the cleaned version alongside the raw text
    op.execute(
        """
        ALTER TABLE segments
        ADD COLUMN IF NOT EXISTS text_cleaned TEXT;
    """
    )
    
    op.execute(
        """
        ALTER TABLE segments
        ADD COLUMN IF NOT EXISTS cleanup_applied BOOLEAN DEFAULT false;
    """
    )
    
    # Add likely_hallucination flag for Whisper hallucination detection
    op.execute(
        """
        ALTER TABLE segments
        ADD COLUMN IF NOT EXISTS likely_hallucination BOOLEAN DEFAULT false;
    """
    )
    
    # Add sentence_boundary flag for segmentation
    op.execute(
        """
        ALTER TABLE segments
        ADD COLUMN IF NOT EXISTS sentence_boundary BOOLEAN DEFAULT false;
    """
    )
    
    # Create index on cleanup_applied for efficient queries
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS segments_cleanup_applied_idx
        ON segments(cleanup_applied);
    """
    )
    
    # Create index on likely_hallucination for filtering
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS segments_likely_hallucination_idx
        ON segments(likely_hallucination) WHERE likely_hallucination = true;
    """
    )
    
    # Add full-text search index on cleaned text if available
    op.execute(
        """
        ALTER TABLE segments ADD COLUMN IF NOT EXISTS text_cleaned_tsv tsvector;
    """
    )
    
    # Create trigger function for cleaned text tsvector (if text_cleaned exists)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION segments_cleaned_tsv_trigger() RETURNS trigger LANGUAGE plpgsql AS $segments_cleaned_tsv$
        BEGIN
            IF NEW.text_cleaned IS NOT NULL THEN
                NEW.text_cleaned_tsv := to_tsvector('english', NEW.text_cleaned);
            ELSE
                NEW.text_cleaned_tsv := NULL;
            END IF;
            RETURN NEW;
        END
        $segments_cleaned_tsv$;
    """
    )
    
    # Create or replace trigger on segments table
    op.execute(
        """
        DROP TRIGGER IF EXISTS segments_cleaned_tsv_update ON segments;
        CREATE TRIGGER segments_cleaned_tsv_update
        BEFORE INSERT OR UPDATE OF text_cleaned ON segments
        FOR EACH ROW EXECUTE FUNCTION segments_cleaned_tsv_trigger();
    """
    )
    
    # Create GIN index for full-text search on cleaned text
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS segments_text_cleaned_tsv_idx
        ON segments USING GIN (text_cleaned_tsv);
    """
    )
    
    # Optional: Create a view for commonly accessed cleaned transcripts
    op.execute(
        """
        CREATE OR REPLACE VIEW cleaned_segments_view AS
        SELECT 
            s.id,
            s.video_id,
            s.transcript_id,
            s.idx,
            s.start_ms,
            s.end_ms,
            s.text AS text_raw,
            COALESCE(s.text_cleaned, s.text) AS text_cleaned,
            s.speaker_label,
            s.confidence,
            s.likely_hallucination,
            s.sentence_boundary,
            s.cleanup_applied,
            s.created_at
        FROM segments s
        ORDER BY s.video_id, s.start_ms;
    """
    )
    
    # Add comment to explain the cleanup columns
    op.execute(
        """
        COMMENT ON COLUMN segments.text_cleaned IS 
        'Cleaned version of text with normalization, punctuation, and filler removal applied. NULL if cleanup not yet performed.';
    """
    )
    
    op.execute(
        """
        COMMENT ON COLUMN segments.likely_hallucination IS 
        'True if this segment was detected as a potential Whisper hallucination (e.g., repetitive text at end).';
    """
    )
    
    op.execute(
        """
        COMMENT ON COLUMN segments.sentence_boundary IS 
        'True if this segment ends a complete sentence.';
    """
    )


def downgrade() -> None:
    """
    Remove transcript cleanup support columns.
    
    WARNING: This will drop all cached cleaned transcripts and cleanup configuration.
    """
    
    # Drop view
    op.execute("DROP VIEW IF EXISTS cleaned_segments_view;")
    
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS segments_text_cleaned_tsv_idx")
    op.execute("DROP INDEX IF EXISTS segments_likely_hallucination_idx")
    op.execute("DROP INDEX IF EXISTS segments_cleanup_applied_idx")
    
    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS segments_cleaned_tsv_update ON segments")
    op.execute("DROP FUNCTION IF EXISTS segments_cleaned_tsv_trigger")
    
    # Drop columns from segments table
    op.execute("ALTER TABLE segments DROP COLUMN IF EXISTS text_cleaned_tsv")
    op.execute("ALTER TABLE segments DROP COLUMN IF EXISTS sentence_boundary")
    op.execute("ALTER TABLE segments DROP COLUMN IF EXISTS likely_hallucination")
    op.execute("ALTER TABLE segments DROP COLUMN IF EXISTS cleanup_applied")
    op.execute("ALTER TABLE segments DROP COLUMN IF EXISTS text_cleaned")
    
    # Drop columns from transcripts table
    op.execute("ALTER TABLE transcripts DROP COLUMN IF EXISTS is_cleaned")
    op.execute("ALTER TABLE transcripts DROP COLUMN IF EXISTS cleanup_config")
