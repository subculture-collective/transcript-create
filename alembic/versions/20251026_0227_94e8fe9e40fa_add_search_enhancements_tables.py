"""add_search_enhancements_tables

Revision ID: 94e8fe9e40fa
Revises: 90627b497f59
Create Date: 2025-10-26 02:27:48.774673

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "94e8fe9e40fa"
down_revision: Union[str, None] = "90627b497f59"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add metadata columns to videos for filtering
    op.execute("ALTER TABLE videos ADD COLUMN IF NOT EXISTS uploaded_at TIMESTAMPTZ")
    op.execute("ALTER TABLE videos ADD COLUMN IF NOT EXISTS channel_name TEXT")
    op.execute("ALTER TABLE videos ADD COLUMN IF NOT EXISTS language TEXT")
    op.execute("ALTER TABLE videos ADD COLUMN IF NOT EXISTS category TEXT")

    # Add indexes for filter performance
    op.execute("CREATE INDEX IF NOT EXISTS videos_uploaded_at_idx ON videos(uploaded_at)")
    op.execute("CREATE INDEX IF NOT EXISTS videos_duration_idx ON videos(duration_seconds)")
    op.execute("CREATE INDEX IF NOT EXISTS videos_channel_name_idx ON videos(channel_name)")
    op.execute("CREATE INDEX IF NOT EXISTS videos_language_idx ON videos(language)")

    # Create search_suggestions table for autocomplete
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS search_suggestions (
            id BIGSERIAL PRIMARY KEY,
            term TEXT NOT NULL,
            frequency INT NOT NULL DEFAULT 1,
            last_used TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS search_suggestions_term_idx ON search_suggestions(LOWER(term))")
    op.execute("CREATE INDEX IF NOT EXISTS search_suggestions_frequency_idx ON search_suggestions(frequency DESC)")

    # Create user_searches table for search history
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_searches (
            id BIGSERIAL PRIMARY KEY,
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            query TEXT NOT NULL,
            filters JSONB DEFAULT '{}'::jsonb,
            result_count INT,
            query_time_ms INT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """
    )
    op.execute("CREATE INDEX IF NOT EXISTS user_searches_user_id_idx ON user_searches(user_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS user_searches_query_idx ON user_searches(query)")
    op.execute("CREATE INDEX IF NOT EXISTS user_searches_created_at_idx ON user_searches(created_at DESC)")


def downgrade() -> None:
    # Drop new tables
    op.execute("DROP TABLE IF EXISTS user_searches")
    op.execute("DROP TABLE IF EXISTS search_suggestions")

    # Drop new indexes on videos
    op.execute("DROP INDEX IF EXISTS videos_language_idx")
    op.execute("DROP INDEX IF EXISTS videos_channel_name_idx")
    op.execute("DROP INDEX IF EXISTS videos_duration_idx")
    op.execute("DROP INDEX IF EXISTS videos_uploaded_at_idx")

    # Drop new columns from videos
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS category")
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS language")
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS channel_name")
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS uploaded_at")
