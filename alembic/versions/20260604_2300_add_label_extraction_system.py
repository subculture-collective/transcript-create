"""add_label_extraction_system

Revision ID: 20260604_2300_label_extraction
Revises: 20260604_2100_recurring_periods
Create Date: 2026-06-04 23:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260604_2300_label_extraction"
down_revision: Union[str, None] = "20260604_2100_recurring_periods"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "archive_extraction_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("extraction_tier", sa.Text(), nullable=False, server_default=sa.text("'cheap'")),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("config_hash", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'running'")),
        sa.Column("metrics", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("scope IN ('video', 'batch', 'period', 'backfill')", name="archive_extraction_runs_scope_check"),
        sa.CheckConstraint("extraction_tier IN ('cheap', 'balanced', 'premium')", name="archive_extraction_runs_extraction_tier_check"),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed', 'cancelled')", name="archive_extraction_runs_status_check"),
    )

    op.create_table(
        "archive_labels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_labels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("canonical_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_labels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'candidate'")),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("publish_tier", sa.Text(), nullable=False, server_default=sa.text("'shadow'")),
        sa.Column("confidence_score", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_extraction_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "kind IN ('topic', 'person', 'series', 'category', 'event', 'game', 'org', 'meme', 'place', 'issue')",
            name="archive_labels_kind_check",
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'review', 'published', 'hidden', 'rejected', 'merged')",
            name="archive_labels_status_check",
        ),
        sa.CheckConstraint("source IN ('admin', 'automatic', 'hybrid', 'seed')", name="archive_labels_source_check"),
        sa.CheckConstraint("publish_tier IN ('gold', 'silver', 'bronze', 'shadow')", name="archive_labels_publish_tier_check"),
    )

    op.create_table(
        "archive_transcript_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("segment_ids", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("text_hash", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("transcript_quality", sa.Numeric(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("video_id", "source", "start_ms", "end_ms", "text_hash", name="archive_transcript_windows_video_source_start_end_hash_uq"),
        sa.CheckConstraint("source IN ('whisper', 'youtube')", name="archive_transcript_windows_source_check"),
    )

    op.create_table(
        "archive_video_chapters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_index", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'candidate'")),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_extraction_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("video_id", "chapter_index", name="archive_video_chapters_video_chapter_index_uq"),
        sa.CheckConstraint("status IN ('candidate', 'published', 'rejected', 'hidden')", name="archive_video_chapters_status_check"),
        sa.CheckConstraint("source IN ('automatic', 'manual', 'hybrid')", name="archive_video_chapters_source_check"),
    )

    op.create_table(
        "archive_label_aliases",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("label_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_labels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("normalized_alias", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False, server_default=sa.text("'en'")),
        sa.Column("weight", sa.Numeric(), nullable=False, server_default=sa.text("1")),
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'automatic'")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("is_ambiguous", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("label_id", "normalized_alias", name="archive_label_aliases_label_normalized_alias_uq"),
        sa.CheckConstraint("source IN ('admin', 'automatic', 'hybrid', 'seed')", name="archive_label_aliases_source_check"),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="archive_label_aliases_status_check"),
    )

    op.create_table(
        "archive_label_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("label_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_labels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_type", sa.Text(), nullable=False),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_video_chapters.id", ondelete="CASCADE"), nullable=True),
        sa.Column("window_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_transcript_windows.id", ondelete="CASCADE"), nullable=True),
        sa.Column("segment_source", sa.Text(), nullable=True),
        sa.Column("segment_id", sa.BigInteger(), nullable=True),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'candidate'")),
        sa.Column("publish_tier", sa.Text(), nullable=False, server_default=sa.text("'shadow'")),
        sa.Column("confidence_score", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("evidence", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_extraction_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assignment_key", sa.Text(), nullable=False, unique=True),
        sa.Column("component_scores", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("unit_type IN ('vod', 'chapter', 'window', 'segment')", name="archive_label_assignments_unit_type_check"),
        sa.CheckConstraint(
            "status IN ('candidate', 'auto_published', 'admin_approved', 'rejected', 'shadow')",
            name="archive_label_assignments_status_check",
        ),
        sa.CheckConstraint(
            "source IN ('alias', 'keyphrase', 'search', 'title', 'embedding_cluster', 'llm', 'metadata', 'admin', 'hybrid')",
            name="archive_label_assignments_source_check",
        ),
        sa.CheckConstraint("publish_tier IN ('gold', 'silver', 'bronze', 'shadow')", name="archive_label_assignments_publish_tier_check"),
    )

    op.create_table(
        "archive_label_feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("label_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_labels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("archive_label_assignments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("old_value", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("new_value", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "archive_label_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("label_kind", sa.Text(), nullable=False),
        sa.Column("unit_type", sa.Text(), nullable=False),
        sa.Column("extraction_tier", sa.Text(), nullable=False, server_default=sa.text("'balanced'")),
        sa.Column("min_publish_score", sa.Numeric(), nullable=False, server_default=sa.text("0.90")),
        sa.Column("min_review_score", sa.Numeric(), nullable=False, server_default=sa.text("0.65")),
        sa.Column("min_evidence_count", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column("min_distinct_videos", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("require_existing_canonical", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("auto_publish_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("label_kind", "unit_type", "extraction_tier", name="archive_label_policies_label_kind_unit_type_extraction_tier_uq"),
        sa.CheckConstraint("label_kind IN ('topic', 'person', 'series', 'category', 'event', 'game', 'org', 'meme', 'place', 'issue')", name="archive_label_policies_label_kind_check"),
        sa.CheckConstraint("unit_type IN ('vod', 'chapter', 'window', 'segment')", name="archive_label_policies_unit_type_check"),
        sa.CheckConstraint("extraction_tier IN ('cheap', 'balanced', 'premium')", name="archive_label_policies_extraction_tier_check"),
    )

    op.execute("CREATE INDEX IF NOT EXISTS archive_labels_kind_status_idx ON archive_labels (kind, status)")
    op.execute("CREATE INDEX IF NOT EXISTS archive_labels_status_confidence_idx ON archive_labels (status, confidence_score DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS archive_label_aliases_normalized_idx ON archive_label_aliases (normalized_alias)")
    op.execute("CREATE INDEX IF NOT EXISTS archive_transcript_windows_video_idx ON archive_transcript_windows (video_id, source, start_ms)")
    op.execute("CREATE INDEX IF NOT EXISTS archive_label_assignments_video_unit_idx ON archive_label_assignments (video_id, unit_type, status)")
    op.execute("CREATE INDEX IF NOT EXISTS archive_label_assignments_label_status_idx ON archive_label_assignments (label_id, status, confidence_score DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS archive_label_assignments_public_idx ON archive_label_assignments (status, publish_tier, unit_type, video_id)")
    op.execute("CREATE INDEX IF NOT EXISTS archive_label_assignments_time_idx ON archive_label_assignments (video_id, start_ms, end_ms)")
    op.execute("CREATE INDEX IF NOT EXISTS archive_video_chapters_video_idx ON archive_video_chapters (video_id, chapter_index)")
    op.execute("CREATE INDEX IF NOT EXISTS archive_extraction_runs_status_idx ON archive_extraction_runs (status, started_at DESC)")

    op.execute(
        """
        INSERT INTO archive_label_policies (
            label_kind, unit_type, extraction_tier, min_publish_score, min_review_score,
            min_evidence_count, min_distinct_videos, require_existing_canonical,
            auto_publish_enabled, config
        ) VALUES
            ('topic', 'window', 'cheap', 0.92, 0.65, 2, 1, false, true, jsonb_build_object('extractors', jsonb_build_array('alias', 'keyphrase'))),
            ('topic', 'vod', 'cheap', 0.94, 0.70, 3, 1, false, true, jsonb_build_object('min_duration_share', 0.05)),
            ('person', 'window', 'cheap', 0.95, 0.75, 2, 1, true, true, jsonb_build_object('person_presence_requires_seed', true)),
            ('series', 'vod', 'cheap', 0.90, 0.70, 2, 2, false, true, jsonb_build_object('series_requires_cross_video', true)),
            ('category', 'vod', 'cheap', 0.88, 0.65, 2, 1, false, true, jsonb_build_object('allowed_auto_categories', jsonb_build_array('gaming', 'chadvice', 'okbuddy', 'guests'))),
            ('topic', 'window', 'balanced', 0.90, 0.62, 2, 1, false, true, jsonb_build_object('extractors', jsonb_build_array('alias', 'keyphrase', 'llm'))),
            ('topic', 'vod', 'balanced', 0.92, 0.68, 3, 1, false, true, jsonb_build_object('min_duration_share', 0.04)),
            ('topic', 'window', 'premium', 0.88, 0.60, 2, 1, false, true, jsonb_build_object('extractors', jsonb_build_array('alias', 'keyphrase', 'llm', 'embedding_cluster')))
        ON CONFLICT (label_kind, unit_type, extraction_tier) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("archive_label_feedback")
    op.drop_table("archive_label_assignments")
    op.drop_table("archive_label_aliases")
    op.drop_table("archive_video_chapters")
    op.drop_table("archive_transcript_windows")
    op.drop_table("archive_label_policies")
    op.drop_table("archive_labels")
    op.drop_table("archive_extraction_runs")
