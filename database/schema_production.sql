-- ============================================================
-- CareerLens AI — Production Database Schema Migration
-- ============================================================
-- Run this in your Supabase SQL Editor to initialize the new
-- jobs, jobs_analytics, and analytics precomputation tables.
-- ============================================================

-- Enable pg_trgm for full-text title search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 1. RAW JOBS (Preserves unmodified scraped data)
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(50) NOT NULL,              -- 'naukri' | 'foundit' | 'adzuna'
    source_job_id VARCHAR(100) NOT NULL,      -- Unique ID from source
    title VARCHAR(255) NOT NULL,
    company VARCHAR(255) NOT NULL,
    locations TEXT[] DEFAULT '{}',
    skills TEXT[] DEFAULT '{}',
    qualifications TEXT[] DEFAULT '{}',
    company_logo_url TEXT,
    min_experience INT,
    max_experience INT,
    min_salary NUMERIC,
    max_salary NUMERIC,
    salary_currency VARCHAR(10) DEFAULT 'INR',
    description TEXT,
    job_url TEXT,
    posted_at TIMESTAMPTZ,
    raw_data JSONB,                           -- Preserves original source JSON
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    cleaned_at TIMESTAMPTZ DEFAULT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_source_job UNIQUE (source, source_job_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_source_job_id ON jobs(source, source_job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_dirty ON jobs(cleaned_at, updated_at) WHERE cleaned_at IS NULL OR updated_at > cleaned_at;
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_jobs_is_active ON jobs(is_active);


-- 2. CLEANED JOBS (Warehouse for structured queries)
CREATE TABLE IF NOT EXISTS jobs_analytics (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fingerprint         VARCHAR(64) UNIQUE NOT NULL, -- MD5 dedup key
    source              VARCHAR(50)  NOT NULL,
    source_job_id       VARCHAR(100) NOT NULL,
    collected_at        DATE         NOT NULL,
    title               VARCHAR(255) NOT NULL,
    company             VARCHAR(255) NOT NULL,
    job_category        VARCHAR(100),
    job_field           VARCHAR(100),
    job_sub_field       VARCHAR(100),
    raw_location        TEXT,
    work_mode           VARCHAR(50),                  -- 'Remote' | 'Hybrid' | 'Onsite'
    city                VARCHAR(100),
    state               VARCHAR(100),
    country             VARCHAR(100) DEFAULT 'India',
    raw_experience      TEXT,
    min_exp             INT,
    max_exp             INT,
    raw_skills          TEXT[] DEFAULT '{}',
    standardized_skills TEXT[] DEFAULT '{}',
    description_raw     TEXT,
    description         TEXT,
    min_salary          NUMERIC,
    max_salary          NUMERIC,
    salary_currency     VARCHAR(10) DEFAULT 'INR',
    job_url             TEXT,
    company_logo_url    TEXT,
    is_active           BOOLEAN DEFAULT TRUE,
    last_seen_at        TIMESTAMPTZ DEFAULT NOW(),
    search_keywords     TEXT[] DEFAULT '{}',
    posted_at           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ja_city           ON jobs_analytics(city);
CREATE INDEX IF NOT EXISTS idx_ja_work_mode      ON jobs_analytics(work_mode);
CREATE INDEX IF NOT EXISTS idx_ja_job_field      ON jobs_analytics(job_field);
CREATE INDEX IF NOT EXISTS idx_ja_job_sub_field  ON jobs_analytics(job_sub_field);
CREATE INDEX IF NOT EXISTS idx_ja_collected_at   ON jobs_analytics(collected_at);
CREATE INDEX IF NOT EXISTS idx_ja_is_active      ON jobs_analytics(is_active);
CREATE INDEX IF NOT EXISTS idx_ja_title_trgm     ON jobs_analytics USING gin(title gin_trgm_ops);


-- 3. JOB SKILLS (1-to-many relationship for normalization)
CREATE TABLE IF NOT EXISTS job_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs_analytics(id) ON DELETE CASCADE,
    skill_name VARCHAR(100) NOT NULL,
    confidence NUMERIC DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_skills_name ON job_skills(skill_name);
CREATE INDEX IF NOT EXISTS idx_job_skills_job_id ON job_skills(job_id);


-- 4. SKILL DEMAND HISTORY (Historical demand trend metrics)
CREATE TABLE IF NOT EXISTS skill_demand_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_name VARCHAR(100) NOT NULL,
    demand_percentage NUMERIC NOT NULL,
    date DATE DEFAULT CURRENT_DATE,
    
    CONSTRAINT unique_skill_date UNIQUE (skill_name, date)
);

CREATE INDEX IF NOT EXISTS idx_sdh_skill_date ON skill_demand_history(skill_name, date);


-- 5. SKILL GAP ANALYSIS (Historical gap metrics comparing supply baselines)
CREATE TABLE IF NOT EXISTS skill_gap_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_name VARCHAR(100) NOT NULL,
    stream VARCHAR(50) NOT NULL,              -- 'cs' | 'data' | 'elec' | etc.
    supply_pct NUMERIC NOT NULL,
    demand_pct NUMERIC NOT NULL,
    gap_score NUMERIC NOT NULL,
    date DATE DEFAULT CURRENT_DATE,
    
    CONSTRAINT unique_gap_skill_stream_date UNIQUE (skill_name, stream, date)
);

CREATE INDEX IF NOT EXISTS idx_sga_skill_stream ON skill_gap_analysis(skill_name, stream, date);


-- 6. SALARY INSIGHTS (Median salary trends)
CREATE TABLE IF NOT EXISTS salary_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_name VARCHAR(100),
    job_field VARCHAR(100),
    city VARCHAR(100),
    exp_level VARCHAR(50),
    median_salary NUMERIC NOT NULL,
    date DATE DEFAULT CURRENT_DATE
);

CREATE INDEX IF NOT EXISTS idx_sal_insights_lookup ON salary_insights(skill_name, job_field, city, exp_level);


-- 7. LOCATION INSIGHTS (Geographic concentration)
CREATE TABLE IF NOT EXISTS location_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city VARCHAR(100) NOT NULL,
    job_count INT NOT NULL,
    avg_salary NUMERIC,
    date DATE DEFAULT CURRENT_DATE,
    
    CONSTRAINT unique_loc_city_date UNIQUE (city, date)
);


-- 8. COMPANY HIRING STATS (Company hiring trends)
CREATE TABLE IF NOT EXISTS company_hiring_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company VARCHAR(255) NOT NULL,
    job_count INT NOT NULL,
    date DATE DEFAULT CURRENT_DATE,
    
    CONSTRAINT unique_comp_date UNIQUE (company, date)
);
