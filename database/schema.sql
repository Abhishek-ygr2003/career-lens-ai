-- Create jobs table
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
    
    -- Ensure uniqueness for source + source_job_id
    CONSTRAINT unique_source_job UNIQUE (source, source_job_id)
);

-- Index definitions
CREATE INDEX IF NOT EXISTS idx_jobs_source_job_id ON jobs(source, source_job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_title ON jobs(title);
