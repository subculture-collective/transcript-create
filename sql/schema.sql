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
        'expanded'
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
    meta JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    youtube_id TEXT NOT NULL,
    title TEXT,
    duration_seconds INT,
    raw_path TEXT,
    wav_path TEXT,
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
    role TEXT NOT NULL DEFAULT 'user', -- user, pro, admin
    stripe_customer_id TEXT,
    stripe_subscription_status TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (oauth_provider, oauth_subject)
);
CREATE INDEX IF NOT EXISTS users_role_idx ON users(role);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT NOT NULL, -- random opaque token stored in cookie
    user_agent TEXT,
    ip_address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS sessions_token_idx ON sessions(token);

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
    session_token TEXT,
    type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS events_created_idx ON events(created_at);
CREATE INDEX IF NOT EXISTS events_type_idx ON events(type);

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
