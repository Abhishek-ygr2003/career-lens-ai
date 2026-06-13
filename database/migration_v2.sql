-- ============================================================
-- CareerLens AI — Migration V2
-- ============================================================

-- 1. ADD LIFECYCLE TRACKING COLUMNS
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE jobs_analytics ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ DEFAULT NULL;

-- 2. DEDUPLICATE AND CONSTRAINT SALARY_INSIGHTS
-- Clean nulls first
UPDATE salary_insights SET skill_name = '' WHERE skill_name IS NULL;
UPDATE salary_insights SET job_field = '' WHERE job_field IS NULL;
UPDATE salary_insights SET city = '' WHERE city IS NULL;
UPDATE salary_insights SET exp_level = '' WHERE exp_level IS NULL;

-- Remove duplicates
DELETE FROM salary_insights a USING salary_insights b
WHERE a.id < b.id 
  AND a.skill_name = b.skill_name
  AND a.job_field = b.job_field
  AND a.city = b.city
  AND a.exp_level = b.exp_level
  AND a.date = b.date;

-- Set constraints & defaults
ALTER TABLE salary_insights ALTER COLUMN skill_name SET DEFAULT '';
ALTER TABLE salary_insights ALTER COLUMN skill_name SET NOT NULL;
ALTER TABLE salary_insights ALTER COLUMN job_field SET DEFAULT '';
ALTER TABLE salary_insights ALTER COLUMN job_field SET NOT NULL;
ALTER TABLE salary_insights ALTER COLUMN city SET DEFAULT '';
ALTER TABLE salary_insights ALTER COLUMN city SET NOT NULL;
ALTER TABLE salary_insights ALTER COLUMN exp_level SET DEFAULT '';
ALTER TABLE salary_insights ALTER COLUMN exp_level SET NOT NULL;

-- Add unique constraint
ALTER TABLE salary_insights DROP CONSTRAINT IF EXISTS unique_salary_insight;
ALTER TABLE salary_insights ADD CONSTRAINT unique_salary_insight UNIQUE (skill_name, job_field, city, exp_level, date);

-- 3. CREATE CRAWL STATE TABLE
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

-- 4. CREATE JOB EVENTS TABLE
CREATE TABLE IF NOT EXISTS job_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL,
    event_type VARCHAR(50) NOT NULL, -- 'created', 'updated', 'closed', 'reopened'
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id);
CREATE INDEX IF NOT EXISTS idx_job_events_type_time ON job_events(event_type, timestamp);

-- 5. CREATE SKILL TAXONOMY TABLE
CREATE TABLE IF NOT EXISTS skill_taxonomy (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_name VARCHAR(100) UNIQUE NOT NULL,
    stream VARCHAR(50) NOT NULL, -- 'cs', 'data', 'elec', 'biz', 'fin', 'design', 'all'
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

-- 6. DYNAMIC PRECOMPUTATION STORED PROCEDURE
CREATE OR REPLACE FUNCTION run_precompute_analytics()
RETURNS void AS $$
DECLARE
    today_date DATE := CURRENT_DATE;
BEGIN
    -- 6.1. Skill Demand History
    WITH date_totals AS (
        SELECT collected_at, COUNT(*) as total_jobs
        FROM jobs_analytics
        WHERE is_active = TRUE
        GROUP BY collected_at
    ),
    skill_matches AS (
        SELECT 
            ja.collected_at,
            t.skill_name,
            COUNT(DISTINCT ja.id) as matches
        FROM jobs_analytics ja
        CROSS JOIN skill_taxonomy t
        WHERE ja.is_active = TRUE
          AND EXISTS (
              SELECT 1 
              FROM unnest(ja.standardized_skills) as s
              WHERE LOWER(s) = ANY(
                  SELECT LOWER(a) FROM unnest(t.aliases) as a
              )
          )
        GROUP BY ja.collected_at, t.skill_name
    )
    INSERT INTO skill_demand_history (skill_name, demand_percentage, date)
    SELECT 
        t.skill_name,
        ROUND((COALESCE(sm.matches, 0)::numeric / dt.total_jobs) * 100, 1) as demand_percentage,
        dt.collected_at as date
    FROM date_totals dt
    CROSS JOIN skill_taxonomy t
    LEFT JOIN skill_matches sm ON sm.collected_at = dt.collected_at AND sm.skill_name = t.skill_name
    ON CONFLICT (skill_name, date) 
    DO UPDATE SET demand_percentage = EXCLUDED.demand_percentage;

    -- 6.2. Skill Gap Analysis
    INSERT INTO skill_gap_analysis (skill_name, stream, supply_pct, demand_pct, gap_score, date)
    SELECT 
        sdh.skill_name,
        t.stream,
        t.supply_score as supply_pct,
        sdh.demand_percentage as demand_pct,
        ROUND(sdh.demand_percentage - t.supply_score, 1) as gap_score,
        sdh.date
    FROM skill_demand_history sdh
    JOIN skill_taxonomy t ON t.skill_name = sdh.skill_name
    ON CONFLICT (skill_name, stream, date) 
    DO UPDATE SET 
        supply_pct = EXCLUDED.supply_pct,
        demand_pct = EXCLUDED.demand_pct,
        gap_score = EXCLUDED.gap_score;

    -- 6.3. Salary Insights
    -- Wipe today's salary insights to avoid duplicate primary key updates
    DELETE FROM salary_insights WHERE date = today_date;

    -- Breakdown 1: By Skill
    WITH job_salaries AS (
        SELECT 
            ja.id,
            CASE 
                WHEN ja.min_salary IS NOT NULL AND ja.max_salary IS NOT NULL THEN (ja.min_salary + ja.max_salary) / 2.0
                WHEN ja.min_salary IS NOT NULL THEN ja.min_salary
                WHEN ja.max_salary IS NOT NULL THEN ja.max_salary
                ELSE NULL
            END as salary_mid
        FROM jobs_analytics ja
        WHERE ja.is_active = TRUE
          AND (ja.min_salary IS NOT NULL OR ja.max_salary IS NOT NULL)
    ),
    skill_salaries AS (
        SELECT 
            t.skill_name,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY js.salary_mid) as median_salary
        FROM jobs_analytics ja
        JOIN job_salaries js ON js.id = ja.id
        CROSS JOIN skill_taxonomy t
        WHERE EXISTS (
            SELECT 1 FROM unnest(ja.standardized_skills) as s
            WHERE LOWER(s) = ANY(
                SELECT LOWER(a) FROM unnest(t.aliases) as a
            )
        )
        GROUP BY t.skill_name
    )
    INSERT INTO salary_insights (skill_name, job_field, city, exp_level, median_salary, date)
    SELECT 
        skill_name,
        '' as job_field,
        '' as city,
        '' as exp_level,
        ROUND(median_salary::numeric, 0) as median_salary,
        today_date as date
    FROM skill_salaries;

    -- Breakdown 2: By Job Field
    WITH job_salaries AS (
        SELECT 
            job_field,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY 
                CASE 
                    WHEN min_salary IS NOT NULL AND max_salary IS NOT NULL THEN (min_salary + max_salary) / 2.0
                    WHEN min_salary IS NOT NULL THEN min_salary
                    WHEN max_salary IS NOT NULL THEN max_salary
                    ELSE NULL
                END
            ) as median_salary
        FROM jobs_analytics
        WHERE is_active = TRUE AND (min_salary IS NOT NULL OR max_salary IS NOT NULL) AND job_field IS NOT NULL AND job_field != 'Other'
        GROUP BY job_field
    )
    INSERT INTO salary_insights (skill_name, job_field, city, exp_level, median_salary, date)
    SELECT 
        '' as skill_name,
        job_field,
        '' as city,
        '' as exp_level,
        ROUND(median_salary::numeric, 0) as median_salary,
        today_date as date
    FROM job_salaries;

    -- Breakdown 3: By City
    WITH job_salaries AS (
        SELECT 
            city,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY 
                CASE 
                    WHEN min_salary IS NOT NULL AND max_salary IS NOT NULL THEN (min_salary + max_salary) / 2.0
                    WHEN min_salary IS NOT NULL THEN min_salary
                    WHEN max_salary IS NOT NULL THEN max_salary
                    ELSE NULL
                END
            ) as median_salary
        FROM jobs_analytics
        WHERE is_active = TRUE AND (min_salary IS NOT NULL OR max_salary IS NOT NULL) AND city IS NOT NULL
        GROUP BY city
    )
    INSERT INTO salary_insights (skill_name, job_field, city, exp_level, median_salary, date)
    SELECT 
        '' as skill_name,
        '' as job_field,
        city,
        '' as exp_level,
        ROUND(median_salary::numeric, 0) as median_salary,
        today_date as date
    FROM job_salaries;

    -- Breakdown 4: By Experience Band
    WITH job_salaries AS (
        SELECT 
            CASE 
                WHEN min_exp IS NULL THEN 'Unknown'
                WHEN min_exp <= 2 THEN 'Fresher'
                WHEN min_exp <= 5 THEN 'Junior'
                WHEN min_exp <= 8 THEN 'Mid'
                ELSE 'Senior'
            END as exp_band,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY 
                CASE 
                    WHEN min_salary IS NOT NULL AND max_salary IS NOT NULL THEN (min_salary + max_salary) / 2.0
                    WHEN min_salary IS NOT NULL THEN min_salary
                    WHEN max_salary IS NOT NULL THEN max_salary
                    ELSE NULL
                END
            ) as median_salary
        FROM jobs_analytics
        WHERE is_active = TRUE AND (min_salary IS NOT NULL OR max_salary IS NOT NULL)
        GROUP BY 
            CASE 
                WHEN min_exp IS NULL THEN 'Unknown'
                WHEN min_exp <= 2 THEN 'Fresher'
                WHEN min_exp <= 5 THEN 'Junior'
                WHEN min_exp <= 8 THEN 'Mid'
                ELSE 'Senior'
            END
    )
    INSERT INTO salary_insights (skill_name, job_field, city, exp_level, median_salary, date)
    SELECT 
        '' as skill_name,
        '' as job_field,
        '' as city,
        exp_band as exp_level,
        ROUND(median_salary::numeric, 0) as median_salary,
        today_date as date
    FROM job_salaries;

    -- 6.4. Location Insights
    INSERT INTO location_insights (city, job_count, avg_salary, date)
    SELECT 
        city,
        COUNT(*) as job_count,
        ROUND(AVG(
            CASE 
                WHEN min_salary IS NOT NULL AND max_salary IS NOT NULL THEN (min_salary + max_salary) / 2.0
                WHEN min_salary IS NOT NULL THEN min_salary
                WHEN max_salary IS NOT NULL THEN max_salary
                ELSE NULL
            END
        )::numeric, 0) as avg_salary,
        today_date as date
    FROM jobs_analytics
    WHERE is_active = TRUE AND city IS NOT NULL
    GROUP BY city
    ON CONFLICT (city, date) DO UPDATE SET 
        job_count = EXCLUDED.job_count,
        avg_salary = EXCLUDED.avg_salary;

    -- 6.5. Company Hiring Stats
    INSERT INTO company_hiring_stats (company, job_count, date)
    SELECT 
        company,
        COUNT(*) as job_count,
        today_date as date
    FROM jobs_analytics
    WHERE is_active = TRUE AND company IS NOT NULL AND company != 'Unknown'
    GROUP BY company
    ON CONFLICT (company, date) DO UPDATE SET 
        job_count = EXCLUDED.job_count;
END;
$$ LANGUAGE plpgsql;
