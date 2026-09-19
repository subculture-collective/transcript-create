"""Opt-in creator updates and passage discussions."""

from alembic import op

revision = "20260919_community"
down_revision = "20260908_enrichment_run_lookup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE community_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES community_posts(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('update','discussion','reply')),
    body TEXT NOT NULL CHECK (length(trim(body)) BETWEEN 1 AND 5000),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','hidden')),
    video_id UUID REFERENCES videos(id) ON DELETE CASCADE,
    start_ms INTEGER,
    end_ms INTEGER,
    pinned BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((kind='reply') = (parent_id IS NOT NULL)),
    CHECK ((video_id IS NULL AND start_ms IS NULL AND end_ms IS NULL) OR
           (video_id IS NOT NULL AND start_ms IS NOT NULL AND end_ms IS NOT NULL AND start_ms>=0 AND end_ms>start_ms)),
    CHECK (kind!='discussion' OR video_id IS NOT NULL)
);
CREATE INDEX community_posts_feed ON community_posts(pinned DESC, created_at DESC, id DESC) WHERE status='published' AND parent_id IS NULL;
CREATE INDEX community_posts_author ON community_posts(author_id, created_at DESC);
CREATE INDEX community_posts_parent ON community_posts(parent_id, created_at, id);
CREATE TABLE community_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
    reporter_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 1000),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(post_id, reporter_id)
);
CREATE INDEX community_reports_queue ON community_reports(status, created_at);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE community_reports; DROP TABLE community_posts;")
