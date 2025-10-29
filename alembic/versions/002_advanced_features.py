"""Advanced transcription features

Revision ID: 002_advanced_features
Revises: 001_initial_schema
Create Date: 2025-10-29 01:53:00.000000

"""
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_advanced_features'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add language column to transcripts if it doesn't exist (may already exist from schema.sql)
    # This is idempotent
    op.execute("""
        ALTER TABLE transcripts 
        ADD COLUMN IF NOT EXISTS detected_language TEXT;
    """)
    
    op.execute("""
        ALTER TABLE transcripts 
        ADD COLUMN IF NOT EXISTS language_probability REAL;
    """)
    
    # Add quality settings to job metadata - already JSONB so no schema change needed
    # Add translation support flag to job metadata - already JSONB so no schema change needed
    
    # Create translations table for storing translated transcripts
    op.execute("""
        CREATE TABLE IF NOT EXISTS translations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            transcript_id UUID NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
            target_language TEXT NOT NULL,
            provider TEXT NOT NULL, -- 'google', 'deepl', 'libretranslate'
            segments JSONB NOT NULL,
            full_text TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(transcript_id, target_language)
        );
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS translations_transcript_id_idx 
        ON translations(transcript_id);
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS translations_target_language_idx 
        ON translations(target_language);
    """)
    
    # Create user_vocabularies table for custom vocabulary/terminology
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_vocabularies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            terms JSONB NOT NULL, -- Array of {pattern, replacement, case_sensitive}
            is_global BOOLEAN NOT NULL DEFAULT false, -- Global vocab applies to all jobs
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS user_vocabularies_user_id_idx 
        ON user_vocabularies(user_id);
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS user_vocabularies_is_global_idx 
        ON user_vocabularies(is_global);
    """)
    
    # Add indexes on segments for confidence filtering
    op.execute("""
        CREATE INDEX IF NOT EXISTS segments_confidence_idx 
        ON segments(confidence) WHERE confidence IS NOT NULL;
    """)
    
    # Add word_timestamps column to segments for word-level timing
    op.execute("""
        ALTER TABLE segments 
        ADD COLUMN IF NOT EXISTS word_timestamps JSONB;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS segments_confidence_idx")
    op.execute("DROP INDEX IF EXISTS user_vocabularies_is_global_idx")
    op.execute("DROP INDEX IF EXISTS user_vocabularies_user_id_idx")
    op.execute("DROP TABLE IF EXISTS user_vocabularies")
    op.execute("DROP INDEX IF EXISTS translations_target_language_idx")
    op.execute("DROP INDEX IF EXISTS translations_transcript_id_idx")
    op.execute("DROP TABLE IF EXISTS translations")
    op.execute("ALTER TABLE segments DROP COLUMN IF EXISTS word_timestamps")
    op.execute("ALTER TABLE transcripts DROP COLUMN IF EXISTS language_probability")
    op.execute("ALTER TABLE transcripts DROP COLUMN IF EXISTS detected_language")
