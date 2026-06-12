-- ============================================================
-- CareerLens AI — jobs (Raw Collection Table)
-- ============================================================

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(50) NOT NULL,              -- e.g., 'foundit'
    source_job_id VARCHAR(100) NOT NULL,      -- Unique ID from source (to prevent duplicates)
    title VARCHAR(255) NOT NULL,
    company VARCHAR(255) NOT NULL,
    locations TEXT[] DEFAULT '{}',            -- Array of city names/locations
    skills TEXT[] DEFAULT '{}',               -- Array of skill names
    qualifications TEXT[] DEFAULT '{}',       -- Array of qualification strings
    company_logo_url TEXT,                    -- Company logo URL
    min_experience INT,                       -- Minimum experience in years
    max_experience INT,                       -- Maximum experience in years
    min_salary NUMERIC,                       -- Minimum salary
    max_salary NUMERIC,                       -- Maximum salary
    salary_currency VARCHAR(10),              -- e.g., 'INR'
    description TEXT,                         -- Description of the job
    job_url TEXT,                             -- Direct URL to job posting
    posted_at TIMESTAMPTZ,                    -- Original posting date
    raw_data JSONB,                           -- Raw JSON payload for audits/history
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Incremental cleaning: NULL = never cleaned
    cleaned_at TIMESTAMPTZ DEFAULT NULL,

    -- Stale job detection
    is_active BOOLEAN DEFAULT TRUE,
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),

    -- Ensure uniqueness for source + source_job_id
    CONSTRAINT unique_source_job UNIQUE (source, source_job_id)
);

-- Index definitions
CREATE INDEX IF NOT EXISTS idx_jobs_source_job_id ON jobs(source, source_job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_title ON jobs(title);

-- Incremental cleaning index — efficient lookup for dirty rows
CREATE INDEX IF NOT EXISTS idx_jobs_dirty
    ON jobs(cleaned_at, updated_at)
    WHERE cleaned_at IS NULL OR updated_at > cleaned_at;

-- Stale job detection index
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_jobs_is_active ON jobs(is_active);
