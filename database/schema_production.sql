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
    closed_at TIMESTAMPTZ DEFAULT NULL,

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
    closed_at           TIMESTAMPTZ DEFAULT NULL,
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
    skill_name VARCHAR(100) NOT NULL DEFAULT '',
    job_field VARCHAR(100) NOT NULL DEFAULT '',
    city VARCHAR(100) NOT NULL DEFAULT '',
    exp_level VARCHAR(50) NOT NULL DEFAULT '',
    median_salary NUMERIC NOT NULL,
    date DATE DEFAULT CURRENT_DATE,

    CONSTRAINT unique_salary_insight UNIQUE (skill_name, job_field, city, exp_level, date)
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


-- 9. CRAWL STATE TABLE
CREATE TABLE IF NOT EXISTS crawl_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(50) NOT NULL,
    domain VARCHAR(100) NOT NULL,
    keyword VARCHAR(255) NOT NULL,
    last_page INT DEFAULT 1,
    last_run TIMESTAMPTZ DEFAULT NOW(),
    next_run TIMESTAMPTZ DEFAULT NULL,
    status VARCHAR(20) DEFAULT 'success',
    error_count INT DEFAULT 0,
    CONSTRAINT unique_source_keyword UNIQUE (source, domain, keyword)
);

CREATE INDEX IF NOT EXISTS idx_crawl_state_lookup ON crawl_state(source, domain, keyword);


-- 10. JOB EVENTS TABLE
CREATE TABLE IF NOT EXISTS job_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL,
    event_type VARCHAR(50) NOT NULL, -- 'created', 'updated', 'closed', 'reopened'
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id);
CREATE INDEX IF NOT EXISTS idx_job_events_type_time ON job_events(event_type, timestamp);


-- 11. SKILL TAXONOMY TABLE
CREATE TABLE IF NOT EXISTS skill_taxonomy (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_name VARCHAR(100) UNIQUE NOT NULL,
    stream VARCHAR(50) NOT NULL,
    supply_score NUMERIC NOT NULL,
    category VARCHAR(100) DEFAULT NULL,
    aliases TEXT[] DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed initial skill taxonomy data
INSERT INTO skill_taxonomy (skill_name, stream, supply_score, aliases) VALUES
('Communication', 'biz', 75, ARRAY['communication']),
('Excel', 'biz', 68, ARRAY['excel']),
('Python', 'cs', 45, ARRAY['python']),
('SQL', 'data', 42, ARRAY['sql']),
('JavaScript', 'cs', 48, ARRAY['javascript', 'typescript']),
('Java', 'cs', 40, ARRAY['java']),
('Machine Learning', 'data', 18, ARRAY['machine learning', 'deep learning', 'tensorflow', 'pytorch']),
('AWS / Cloud', 'cs', 22, ARRAY['aws', 'azure', 'gcp']),
('DevOps / Docker', 'cs', 15, ARRAY['devops', 'docker', 'kubernetes', 'ci/cd']),
('Generative AI', 'data', 6, ARRAY['gen ai', 'large language models', 'retrieval augmented generation', 'langchain', 'prompt engineering']),
('Cybersecurity', 'cs', 10, ARRAY['cybersecurity']),
('Statistics', 'data', 25, ARRAY['statistics']),
('Project Management', 'biz', 32, ARRAY['project management', 'agile', 'scrum']),
('UI/UX Design', 'design', 14, ARRAY['ui/ux design', 'figma']),
('C / C++', 'cs', 35, ARRAY['c++']),
('Embedded Systems', 'elec', 12, ARRAY['embedded systems']),
('Data Engineering', 'data', 16, ARRAY['data engineering']),
('Tableau / PowerBI', 'data', 20, ARRAY['tableau', 'power bi'])
ON CONFLICT (skill_name) DO UPDATE SET
    stream = EXCLUDED.stream,
    supply_score = EXCLUDED.supply_score,
    aliases = EXCLUDED.aliases,
    updated_at = NOW();


-- 12. MONTHLY SNAPSHOTS (Caching historical active job metrics month-over-month)
CREATE TABLE IF NOT EXISTS monthly_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    month DATE NOT NULL, -- e.g. 2026-06-01
    metric_type VARCHAR(50) NOT NULL, -- 'field_share', 'city_share', 'skill_demand'
    metric_name VARCHAR(100) NOT NULL, -- e.g. 'Data Science & AI', 'Bangalore', 'Python'
    job_count INT DEFAULT 0,
    avg_salary NUMERIC NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_snapshot_metric UNIQUE (month, metric_type, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_ms_month ON monthly_snapshots(month);
CREATE INDEX IF NOT EXISTS idx_ms_type_name ON monthly_snapshots(metric_type, metric_name);

