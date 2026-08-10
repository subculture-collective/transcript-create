-- Enable required extensions (if not already)
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid

DO $$ BEGIN
    CREATE TYPE job_state AS ENUM (
        'pending',
        'downloading',
        'transcoding',
        'transcribing',
        'diarizing',
        'persisting',
        'completed',
        'failed',
        'expanded',
        'needs_attention'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind TEXT NOT NULL CHECK (kind IN ('single','channel')),
    input_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    state job_state NOT NULL DEFAULT 'pending',
    error TEXT,
    priority INT NOT NULL DEFAULT 100,
    meta JSONB DEFAULT '{}'::jsonb,
    owner_user_id UUID,
    canonical_source TEXT,
    idempotency_key TEXT,
    stage TEXT NOT NULL DEFAULT 'queued',
    completed_units INT NOT NULL DEFAULT 0,
    total_units INT,
    heartbeat_at TIMESTAMPTZ,
    cancellation_requested_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    attempt_count INT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    last_failure_summary TEXT,
    quarantined_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS jobs_owner_created_idx ON jobs(owner_user_id, created_at);
CREATE INDEX IF NOT EXISTS jobs_next_attempt_idx ON jobs(next_attempt_at);
CREATE UNIQUE INDEX IF NOT EXISTS jobs_active_canonical_unique_idx
    ON jobs(owner_user_id, kind, canonical_source)
    WHERE owner_user_id IS NOT NULL AND canonical_source IS NOT NULL
      AND state NOT IN ('failed', 'completed', 'needs_attention');
CREATE UNIQUE INDEX IF NOT EXISTS jobs_owner_idempotency_unique_idx
    ON jobs(owner_user_id, idempotency_key)
    WHERE owner_user_id IS NOT NULL AND idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    youtube_id TEXT NOT NULL,
    title TEXT,
    duration_seconds INT,
    raw_path TEXT,
    wav_path TEXT,
    caption_ingest_state TEXT NOT NULL DEFAULT 'pending' CHECK (caption_ingest_state IN ('pending','running','completed','unavailable','failed','skipped')),
    caption_ingest_error TEXT,
    diarization_state TEXT NOT NULL DEFAULT 'pending' CHECK (diarization_state IN ('pending','running','completed','failed','skipped')),
    diarization_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    state job_state NOT NULL DEFAULT 'pending',
    error TEXT,
    idx INT,
    uploaded_at TIMESTAMPTZ,
    channel_name TEXT,
    language TEXT,
    category TEXT,
    UNIQUE (job_id, youtube_id)
);
CREATE INDEX IF NOT EXISTS videos_job_id_idx ON videos(job_id);
CREATE INDEX IF NOT EXISTS videos_state_idx ON videos(state);
CREATE INDEX IF NOT EXISTS videos_uploaded_at_idx ON videos(uploaded_at);
CREATE INDEX IF NOT EXISTS videos_duration_idx ON videos(duration_seconds);
CREATE INDEX IF NOT EXISTS videos_channel_name_idx ON videos(channel_name);
CREATE INDEX IF NOT EXISTS videos_language_idx ON videos(language);

CREATE TABLE IF NOT EXISTS transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    full_text TEXT,
    language TEXT,
    model TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS transcripts_video_id_idx ON transcripts(video_id);

CREATE TABLE IF NOT EXISTS segments (
    id BIGSERIAL PRIMARY KEY,
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    transcript_id UUID REFERENCES transcripts(id) ON DELETE CASCADE,
    idx INT,
    start_ms INT NOT NULL,
    end_ms INT NOT NULL,
    text TEXT NOT NULL,
    speaker_label TEXT,
    confidence REAL,
    avg_logprob REAL,
    temperature REAL,
    token_count INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS segments_video_time_idx ON segments(video_id, start_ms);

CREATE TABLE IF NOT EXISTS transcript_blocks (
    id BIGSERIAL PRIMARY KEY,
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    block_index INT NOT NULL,
    start_ms INT NOT NULL,
    end_ms INT NOT NULL,
    speaker_label TEXT,
    text TEXT NOT NULL,
    segment_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    kind TEXT NOT NULL DEFAULT 'paragraph' CHECK (kind IN ('paragraph', 'speaker_turn')),
    formatter_version TEXT NOT NULL DEFAULT 'rule-v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (video_id, block_index)
);
CREATE INDEX IF NOT EXISTS transcript_blocks_video_idx ON transcript_blocks(video_id);
CREATE INDEX IF NOT EXISTS transcript_blocks_video_time_idx ON transcript_blocks(video_id, start_ms);

-- ---
-- Full-text search support for segments
-- Adds a tsvector column, GIN index, and triggers to keep it in sync
-- ---
ALTER TABLE segments ADD COLUMN IF NOT EXISTS text_tsv tsvector;

CREATE OR REPLACE FUNCTION segments_tsv_trigger() RETURNS trigger LANGUAGE plpgsql AS $segments_tsv$
BEGIN
    NEW.text_tsv := to_tsvector('english', COALESCE(NEW.text, ''));
    RETURN NEW;
END
$segments_tsv$;

DO $$ BEGIN
    CREATE TRIGGER segments_tsv_update
    BEFORE INSERT OR UPDATE OF text ON segments
    FOR EACH ROW EXECUTE FUNCTION segments_tsv_trigger();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS segments_text_tsv_idx ON segments USING GIN (text_tsv);
CREATE INDEX IF NOT EXISTS segments_text_simple_tsv_idx
    ON segments USING GIN (to_tsvector('simple', COALESCE(text, '')));

-- Set video_id automatically when only transcript_id is provided on insert
CREATE OR REPLACE FUNCTION segments_set_video_from_transcript() RETURNS trigger LANGUAGE plpgsql AS $set_video$
BEGIN
    IF NEW.transcript_id IS NOT NULL AND NEW.video_id IS NULL THEN
        SELECT t.video_id INTO NEW.video_id FROM transcripts t WHERE t.id = NEW.transcript_id;
    END IF;
    RETURN NEW;
END
$set_video$;

DO $$ BEGIN
    CREATE TRIGGER segments_set_video_from_transcript_tr
    BEFORE INSERT ON segments
    FOR EACH ROW EXECUTE FUNCTION segments_set_video_from_transcript();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---
-- YouTube auto-generated transcript storage
-- Stores raw YouTube caption tracks (auto-captions) and their segments
-- ---

CREATE TABLE IF NOT EXISTS youtube_transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    language TEXT,
    kind TEXT DEFAULT 'auto', -- 'auto' for auto-captions; future-proof for 'manual'
    source_url TEXT,          -- caption track URL (json3) used for ingestion
    full_text TEXT,           -- concatenated caption text for quick retrieval
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS youtube_transcripts_video_unique ON youtube_transcripts(video_id);
CREATE INDEX IF NOT EXISTS youtube_transcripts_video_idx ON youtube_transcripts(video_id);

CREATE TABLE IF NOT EXISTS youtube_segments (
    id BIGSERIAL PRIMARY KEY,
    youtube_transcript_id UUID NOT NULL REFERENCES youtube_transcripts(id) ON DELETE CASCADE,
    start_ms INT NOT NULL,
    end_ms INT NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS youtube_segments_time_idx ON youtube_segments(youtube_transcript_id, start_ms);

-- Full-text search support for youtube_segments
ALTER TABLE youtube_segments ADD COLUMN IF NOT EXISTS text_tsv tsvector;

-- Function must exist before creating trigger
CREATE OR REPLACE FUNCTION youtube_segments_tsv_trigger() RETURNS trigger LANGUAGE plpgsql AS $yt_segments_tsv$
BEGIN
    NEW.text_tsv := to_tsvector('english', COALESCE(NEW.text, ''));
    RETURN NEW;
END
$yt_segments_tsv$;

DO $$ BEGIN
    CREATE TRIGGER youtube_segments_tsv_update
    BEFORE INSERT OR UPDATE OF text ON youtube_segments
    FOR EACH ROW EXECUTE FUNCTION youtube_segments_tsv_trigger();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS youtube_segments_text_tsv_idx ON youtube_segments USING GIN (text_tsv);
CREATE INDEX IF NOT EXISTS youtube_segments_text_simple_tsv_idx
    ON youtube_segments USING GIN (to_tsvector('simple', COALESCE(text, '')));

-- ---
-- Users, sessions, and favorites for web frontend
-- ---

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT,
    name TEXT,
    avatar_url TEXT,
    oauth_provider TEXT,
    oauth_subject TEXT,
    plan TEXT NOT NULL DEFAULT 'free',
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'moderator', 'admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (oauth_provider, oauth_subject)
);
CREATE INDEX IF NOT EXISTS users_role_idx ON users(role);

ALTER TABLE jobs ADD CONSTRAINT jobs_owner_user_id_fkey
    FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS user_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('google', 'twitch')),
    subject TEXT NOT NULL,
    provider_email TEXT,
    provider_email_verified BOOLEAN,
    provider_name TEXT,
    provider_avatar_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    UNIQUE (provider, subject),
    UNIQUE (user_id, provider)
);
CREATE INDEX IF NOT EXISTS user_identities_user_id_idx ON user_identities(user_id);

CREATE TABLE IF NOT EXISTS oauth_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_hash CHAR(64) NOT NULL UNIQUE,
    nonce_hash CHAR(64) NOT NULL,
    provider TEXT NOT NULL CHECK (provider IN ('google', 'twitch')),
    intent TEXT NOT NULL CHECK (intent IN ('login', 'link', 'merge')),
    link_user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    CONSTRAINT oauth_requests_binding_check
    CHECK ((intent = 'login' AND link_user_id IS NULL)
        OR (intent IN ('link', 'merge') AND link_user_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS oauth_requests_expiry_idx ON oauth_requests(expires_at);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE, -- SHA-256 hash of opaque cookie token
    user_agent TEXT,
    ip_address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS sessions_user_id_idx ON sessions(user_id);

CREATE TABLE IF NOT EXISTS source_deletions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL,
    youtube_id TEXT NOT NULL,
    owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    deleted_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    deleted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    backup_exclusion_until TIMESTAMPTZ NOT NULL,
    raw_path TEXT,
    wav_path TEXT,
    cleanup_status TEXT NOT NULL DEFAULT 'pending' CHECK (cleanup_status IN ('pending', 'completed')),
    cleanup_attempts INTEGER NOT NULL DEFAULT 0,
    cleanup_error TEXT,
    cleanup_started_at TIMESTAMPTZ,
    cleanup_completed_at TIMESTAMPTZ,
    cleanup_lease_until TIMESTAMPTZ,
    cleanup_next_attempt_at TIMESTAMPTZ,
    cleanup_lease_token UUID,
    UNIQUE (video_id)
);
CREATE INDEX IF NOT EXISTS source_deletions_cleanup_pending_idx
    ON source_deletions (cleanup_status, cleanup_next_attempt_at, cleanup_lease_until)
    WHERE cleanup_status = 'pending';

CREATE TABLE IF NOT EXISTS favorites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    start_ms INT NOT NULL,
    end_ms INT NOT NULL,
    text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS favorites_user_idx ON favorites(user_id);
CREATE INDEX IF NOT EXISTS favorites_video_idx ON favorites(video_id);

-- ---
-- Analytics events
-- ---
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    analytics_subject_id CHAR(64),
    type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT events_analytics_subject_format_check
        CHECK (analytics_subject_id IS NULL OR analytics_subject_id ~ '^[0-9a-f]{64}$')
);
CREATE INDEX IF NOT EXISTS events_created_idx ON events(created_at);
CREATE INDEX IF NOT EXISTS events_type_idx ON events(type);
CREATE INDEX IF NOT EXISTS events_analytics_subject_idx ON events(analytics_subject_id);
CREATE INDEX IF NOT EXISTS events_user_created_idx ON events(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS event_daily_aggregates (
    day DATE NOT NULL,
    type TEXT NOT NULL,
    count BIGINT NOT NULL CHECK (count >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day, type)
);

-- ---
-- Search enhancements: suggestions and search history
-- ---

CREATE TABLE IF NOT EXISTS search_suggestions (
    id BIGSERIAL PRIMARY KEY,
    term TEXT NOT NULL,
    frequency INT NOT NULL DEFAULT 1,
    last_used TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS search_suggestions_term_idx ON search_suggestions(LOWER(term));
CREATE INDEX IF NOT EXISTS search_suggestions_frequency_idx ON search_suggestions(frequency DESC);

CREATE TABLE IF NOT EXISTS user_searches (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    filters JSONB DEFAULT '{}'::jsonb,
    result_count INT,
    query_time_ms INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS user_searches_user_id_idx ON user_searches(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS user_searches_query_idx ON user_searches(query);
CREATE INDEX IF NOT EXISTS user_searches_created_at_idx ON user_searches(created_at DESC);

-- ---
-- Security: API keys and audit logs
-- ---

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE, -- SHA-256 hash of the API key
    key_prefix TEXT NOT NULL, -- First 8 chars for display (e.g., "tc_abc12...")
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ, -- NULL = never expires
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    scopes TEXT -- Comma-separated API scopes for future use
);
CREATE INDEX IF NOT EXISTS api_keys_user_id_idx ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS api_keys_key_hash_idx ON api_keys(key_hash);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL, -- login_success, login_failed, api_key_created, etc.
    resource_type TEXT, -- Type of resource affected (video, job, etc.)
    resource_id TEXT, -- ID of resource affected
    ip_address TEXT,
    user_agent TEXT,
    success BOOLEAN NOT NULL DEFAULT true,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS audit_logs_user_id_idx ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS audit_logs_action_idx ON audit_logs(action);
CREATE INDEX IF NOT EXISTS audit_logs_created_at_idx ON audit_logs(created_at);

-- ---
-- Advanced user search and vocabulary features
-- ---

CREATE TABLE IF NOT EXISTS user_vocabularies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    terms JSONB NOT NULL,
    is_global BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS user_vocabularies_user_id_idx ON user_vocabularies(user_id);
CREATE INDEX IF NOT EXISTS user_vocabularies_is_global_idx ON user_vocabularies(is_global);

CREATE TABLE IF NOT EXISTS saved_searches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT saved_searches_user_query_key UNIQUE (user_id, query)
);
CREATE INDEX IF NOT EXISTS saved_searches_user_id_created_at_idx
    ON saved_searches(user_id, created_at);

-- ---
-- Archive label extraction system
-- ---

CREATE TABLE IF NOT EXISTS archive_extraction_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope TEXT NOT NULL,
    extraction_tier TEXT NOT NULL DEFAULT 'cheap',
    video_id UUID REFERENCES videos(id) ON DELETE SET NULL,
    model_name TEXT,
    model_version TEXT,
    prompt_version TEXT,
    config_hash TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    CONSTRAINT archive_extraction_runs_scope_check CHECK (scope IN ('video', 'batch', 'period', 'backfill')),
    CONSTRAINT archive_extraction_runs_extraction_tier_check CHECK (extraction_tier IN ('cheap', 'balanced', 'premium')),
    CONSTRAINT archive_extraction_runs_status_check CHECK (status IN ('running', 'completed', 'failed', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS archive_labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    kind TEXT NOT NULL,
    parent_id UUID REFERENCES archive_labels(id) ON DELETE SET NULL,
    canonical_id UUID REFERENCES archive_labels(id) ON DELETE SET NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'candidate',
    source TEXT NOT NULL,
    publish_tier TEXT NOT NULL DEFAULT 'shadow',
    confidence_score NUMERIC NOT NULL DEFAULT 0,
    created_by_run_id UUID REFERENCES archive_extraction_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT archive_labels_kind_check CHECK (kind IN ('topic', 'person', 'series', 'category', 'event', 'game', 'org', 'meme', 'place', 'issue')),
    CONSTRAINT archive_labels_status_check CHECK (status IN ('candidate', 'review', 'published', 'hidden', 'rejected', 'merged')),
    CONSTRAINT archive_labels_source_check CHECK (source IN ('admin', 'automatic', 'hybrid', 'seed')),
    CONSTRAINT archive_labels_publish_tier_check CHECK (publish_tier IN ('gold', 'silver', 'bronze', 'shadow'))
);

CREATE TABLE IF NOT EXISTS archive_transcript_windows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    segment_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    text_hash TEXT NOT NULL,
    text TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    transcript_quality NUMERIC NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT archive_transcript_windows_video_source_start_end_hash_uq
        UNIQUE (video_id, source, start_ms, end_ms, text_hash),
    CONSTRAINT archive_transcript_windows_source_check CHECK (source IN ('whisper', 'youtube'))
);

CREATE TABLE IF NOT EXISTS archive_video_chapters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    chapter_index INTEGER NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    title TEXT,
    summary TEXT,
    confidence_score NUMERIC NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'candidate',
    source TEXT NOT NULL,
    run_id UUID REFERENCES archive_extraction_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT archive_video_chapters_video_chapter_index_uq UNIQUE (video_id, chapter_index),
    CONSTRAINT archive_video_chapters_status_check CHECK (status IN ('candidate', 'published', 'rejected', 'hidden')),
    CONSTRAINT archive_video_chapters_source_check CHECK (source IN ('automatic', 'manual', 'hybrid'))
);

CREATE TABLE IF NOT EXISTS archive_label_aliases (
    id BIGSERIAL PRIMARY KEY,
    label_id UUID NOT NULL REFERENCES archive_labels(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    weight NUMERIC NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'automatic',
    status TEXT NOT NULL DEFAULT 'active',
    is_ambiguous BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT archive_label_aliases_label_normalized_alias_uq UNIQUE (label_id, normalized_alias),
    CONSTRAINT archive_label_aliases_source_check CHECK (source IN ('admin', 'automatic', 'hybrid', 'seed')),
    CONSTRAINT archive_label_aliases_status_check CHECK (status IN ('active', 'inactive'))
);

CREATE TABLE IF NOT EXISTS archive_label_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label_id UUID NOT NULL REFERENCES archive_labels(id) ON DELETE CASCADE,
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    unit_type TEXT NOT NULL,
    chapter_id UUID REFERENCES archive_video_chapters(id) ON DELETE CASCADE,
    window_id UUID REFERENCES archive_transcript_windows(id) ON DELETE CASCADE,
    segment_source TEXT,
    segment_id BIGINT,
    start_ms INTEGER,
    end_ms INTEGER,
    status TEXT NOT NULL DEFAULT 'candidate',
    publish_tier TEXT NOT NULL DEFAULT 'shadow',
    confidence_score NUMERIC NOT NULL DEFAULT 0,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    source TEXT NOT NULL,
    run_id UUID REFERENCES archive_extraction_runs(id) ON DELETE SET NULL,
    assignment_key TEXT NOT NULL UNIQUE,
    component_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT archive_label_assignments_unit_type_check CHECK (unit_type IN ('vod', 'chapter', 'window', 'segment')),
    CONSTRAINT archive_label_assignments_status_check CHECK (status IN ('candidate', 'auto_published', 'admin_approved', 'rejected', 'shadow')),
    CONSTRAINT archive_label_assignments_source_check CHECK (source IN ('alias', 'keyphrase', 'search', 'title', 'embedding_cluster', 'llm', 'metadata', 'admin', 'hybrid')),
    CONSTRAINT archive_label_assignments_publish_tier_check CHECK (publish_tier IN ('gold', 'silver', 'bronze', 'shadow'))
);

CREATE TABLE IF NOT EXISTS archive_label_feedback (
    id BIGSERIAL PRIMARY KEY,
    label_id UUID REFERENCES archive_labels(id) ON DELETE SET NULL,
    assignment_id UUID REFERENCES archive_label_assignments(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    old_value JSONB NOT NULL DEFAULT '{}'::jsonb,
    new_value JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason TEXT,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS archive_labels_kind_status_idx ON archive_labels(kind, status);
CREATE INDEX IF NOT EXISTS archive_labels_status_confidence_idx ON archive_labels(status, confidence_score DESC);
CREATE INDEX IF NOT EXISTS archive_label_aliases_normalized_idx ON archive_label_aliases(normalized_alias);
CREATE INDEX IF NOT EXISTS archive_transcript_windows_video_idx ON archive_transcript_windows(video_id, source, start_ms);
CREATE INDEX IF NOT EXISTS archive_label_assignments_video_unit_idx ON archive_label_assignments(video_id, unit_type, status);
CREATE INDEX IF NOT EXISTS archive_label_assignments_label_status_idx ON archive_label_assignments(label_id, status, confidence_score DESC);
CREATE INDEX IF NOT EXISTS archive_label_assignments_public_idx ON archive_label_assignments(status, publish_tier, unit_type, video_id);
CREATE INDEX IF NOT EXISTS archive_label_assignments_time_idx ON archive_label_assignments(video_id, start_ms, end_ms);
CREATE INDEX IF NOT EXISTS archive_video_chapters_video_idx ON archive_video_chapters(video_id, chapter_index);
CREATE INDEX IF NOT EXISTS archive_extraction_runs_status_idx ON archive_extraction_runs(status, started_at DESC);

-- ---
-- Citation-backed archive opinion history
-- ---

CREATE TABLE IF NOT EXISTS archive_opinions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_slug TEXT NOT NULL,
    normalized_claim TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate', 'published', 'corrected', 'retracted')),
    current_revision INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (subject_slug, normalized_claim)
);

CREATE TABLE IF NOT EXISTS archive_opinion_revisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    opinion_id UUID NOT NULL REFERENCES archive_opinions(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    stance TEXT NOT NULL,
    summary TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    model_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    time_bucket TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_generated BOOLEAN NOT NULL DEFAULT true,
    status TEXT NOT NULL CHECK (status IN ('candidate', 'published', 'corrected', 'retracted')),
    correction_reason TEXT,
    corrected_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (opinion_id, revision)
);
CREATE INDEX IF NOT EXISTS ix_archive_opinions_subject_status
    ON archive_opinions(subject_slug, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_archive_opinion_revisions_opinion
    ON archive_opinion_revisions(opinion_id, revision DESC);
