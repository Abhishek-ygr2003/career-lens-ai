-- ============================================================
-- CareerLens AI — jobs_analytics (Unified Analytics Warehouse)
-- ============================================================
-- Run this ONCE in your Supabase SQL Editor to create the table.
-- ============================================================

-- Enable pg_trgm for full-text title search (run once per DB)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS jobs_analytics (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Stable deduplication key (MD5 of title+company+city+source_job_id)
    fingerprint         VARCHAR(64) UNIQUE NOT NULL,

    -- Source metadata
    source              VARCHAR(50)  NOT NULL,        -- 'naukri' | 'foundit'
    source_job_id       VARCHAR(100) NOT NULL,
    collected_at        DATE         NOT NULL,         -- Date the job was scraped

    -- Job identity
    title               VARCHAR(255) NOT NULL,
    company             VARCHAR(255) NOT NULL,
    job_category        VARCHAR(100),                  -- Legacy: 'Data Science', 'Machine Learning'
    job_field           VARCHAR(100),                  -- Top-level: 'AI / ML', 'Data', 'Software'
    job_sub_field       VARCHAR(100),                  -- Sub-level: 'MLOps', 'Data Science', etc.

    -- Location — raw value preserved alongside structured hierarchy
    raw_location        TEXT,                          -- Original string from source API
    work_mode           VARCHAR(50),                   -- 'Remote' | 'Hybrid' | 'Onsite'
    city                VARCHAR(100),                  -- e.g. 'Bangalore'
    state               VARCHAR(100),                  -- e.g. 'Karnataka'
    country             VARCHAR(100) DEFAULT 'India',

    -- Experience — raw string preserved alongside parsed ints
    raw_experience      TEXT,                          -- e.g. '0-3 Yrs'
    min_exp             INT,
    max_exp             INT,

    -- Skills — raw array preserved alongside normalized array
    raw_skills          TEXT[] DEFAULT '{}',
    standardized_skills TEXT[] DEFAULT '{}',

    -- Description — original (may contain HTML) + cleaned plain text
    description_raw     TEXT,
    description         TEXT,

    -- Salary
    min_salary          NUMERIC,
    max_salary          NUMERIC,
    salary_currency     VARCHAR(10) DEFAULT 'INR',

    -- Links & assets
    job_url             TEXT,
    company_logo_url    TEXT,

    -- Stale job detection
    is_active           BOOLEAN DEFAULT TRUE,
    last_seen_at        TIMESTAMPTZ DEFAULT NOW(),

    -- Search keywords that brought this job in
    search_keywords     TEXT[] DEFAULT '{}',

    -- Timestamps
    posted_at           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Indexes for common dashboard query patterns
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_ja_job_category   ON jobs_analytics(job_category);
CREATE INDEX IF NOT EXISTS idx_ja_job_field      ON jobs_analytics(job_field);
CREATE INDEX IF NOT EXISTS idx_ja_job_sub_field  ON jobs_analytics(job_sub_field);
CREATE INDEX IF NOT EXISTS idx_ja_city           ON jobs_analytics(city);
CREATE INDEX IF NOT EXISTS idx_ja_work_mode      ON jobs_analytics(work_mode);
CREATE INDEX IF NOT EXISTS idx_ja_source         ON jobs_analytics(source);
CREATE INDEX IF NOT EXISTS idx_ja_collected_at   ON jobs_analytics(collected_at);
CREATE INDEX IF NOT EXISTS idx_ja_min_exp        ON jobs_analytics(min_exp);
CREATE INDEX IF NOT EXISTS idx_ja_max_exp        ON jobs_analytics(max_exp);
CREATE INDEX IF NOT EXISTS idx_ja_is_active      ON jobs_analytics(is_active);
CREATE INDEX IF NOT EXISTS idx_ja_last_seen      ON jobs_analytics(last_seen_at);
-- Trigram index for keyword search on title (requires pg_trgm)
CREATE INDEX IF NOT EXISTS idx_ja_title_trgm     ON jobs_analytics USING gin(title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_ja_company        ON jobs_analytics(company);
