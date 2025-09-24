CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS videos (
  id TEXT PRIMARY KEY,
  url TEXT,
  title TEXT,
  channel_id TEXT,
  published_at TIMESTAMPTZ,
  duration_sec INTEGER
);

CREATE TABLE IF NOT EXISTS runs (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  video_id TEXT REFERENCES videos(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT now(),
  engine TEXT,
  language TEXT,
  chunk_sec INTEGER,
  overlap_sec INTEGER,
  status TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
  id SERIAL PRIMARY KEY,
  video_id TEXT REFERENCES videos(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  kind TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
