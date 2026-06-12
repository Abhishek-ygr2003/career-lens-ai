-- ============================================================
-- CareerLens AI — Migration Script
-- ============================================================
-- Run this in Supabase SQL Editor to add new columns to
-- existing tables without dropping data.
-- Safe to run multiple times (IF NOT EXISTS / IF EXISTS guards).
-- ============================================================

-- ── jobs table ──────────────────────────────────────────────

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cleaned_at TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_jobs_dirty
    ON jobs(cleaned_at, updated_at)
    WHERE cleaned_at IS NULL OR updated_at > cleaned_at;
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_jobs_is_active ON jobs(is_active);

-- ── jobs_analytics table ────────────────────────────────────

ALTER TABLE jobs_analytics ADD COLUMN IF NOT EXISTS job_field VARCHAR(100);
ALTER TABLE jobs_analytics ADD COLUMN IF NOT EXISTS job_sub_field VARCHAR(100);
ALTER TABLE jobs_analytics ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE jobs_analytics ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE jobs_analytics ADD COLUMN IF NOT EXISTS search_keywords TEXT[] DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_ja_job_field     ON jobs_analytics(job_field);
CREATE INDEX IF NOT EXISTS idx_ja_job_sub_field ON jobs_analytics(job_sub_field);
CREATE INDEX IF NOT EXISTS idx_ja_is_active     ON jobs_analytics(is_active);
CREATE INDEX IF NOT EXISTS idx_ja_last_seen     ON jobs_analytics(last_seen_at);

-- ── collection_runs table ───────────────────────────────────

CREATE TABLE IF NOT EXISTS collection_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    keyword VARCHAR(255) NOT NULL,
    source VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'running',      -- 'running' | 'success' | 'failed'
    jobs_collected INT DEFAULT 0,
    jobs_new INT DEFAULT 0,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    error_text TEXT
);

CREATE INDEX IF NOT EXISTS idx_cr_keyword    ON collection_runs(keyword, source);
CREATE INDEX IF NOT EXISTS idx_cr_started_at ON collection_runs(started_at);
