-- Migration V3: Add monthly_snapshots table for analytics history caching
-- Target table to cache historical active job metrics month-over-month.

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

-- Index for monthly lookups
CREATE INDEX IF NOT EXISTS idx_ms_month ON monthly_snapshots(month);
CREATE INDEX IF NOT EXISTS idx_ms_type_name ON monthly_snapshots(metric_type, metric_name);
