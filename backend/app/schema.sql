-- Run this in Supabase SQL Editor (Settings → SQL Editor → New query).
-- Every statement is guarded (IF NOT EXISTS / DROP … IF EXISTS), so the whole file can be
-- re-run on a fresh or an existing database. Production should move to versioned
-- migrations — see docs/PRODUCTION_ARCHITECTURE.md §9.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS leads (
  id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  -- GAF scraped data
  company_name         TEXT          NOT NULL,
  gaf_contractor_id    TEXT          UNIQUE,
  address              TEXT,
  city                 TEXT,
  state                TEXT,
  postal_code          TEXT,
  country_code         TEXT          DEFAULT 'us',
  phone                TEXT,
  website              TEXT,
  gaf_profile_url      TEXT,
  certifications       TEXT[]        DEFAULT '{}',
  years_in_business    INTEGER,
  service_area         TEXT,
  rating               NUMERIC(3,2),
  review_count         INTEGER,
  -- Perplexity research
  research_summary     TEXT,
  research_sources     TEXT[]        DEFAULT '{}',
  -- AI-generated account insights
  lead_score           INTEGER       CHECK (lead_score BETWEEN 1 AND 10),
  score_rationale      TEXT,
  ai_summary           TEXT,
  talking_points       TEXT[]        DEFAULT '{}',
  recommended_approach TEXT,
  -- Pipeline state
  status               TEXT          NOT NULL DEFAULT 'scraped'
                       CHECK (status IN ('scraped', 'researched', 'enriched', 'failed')),
  error_message        TEXT,
  -- Timestamps
  scraped_at           TIMESTAMPTZ   DEFAULT NOW(),
  researched_at        TIMESTAMPTZ,
  enriched_at          TIMESTAMPTZ,
  created_at           TIMESTAMPTZ   DEFAULT NOW(),
  updated_at           TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_leads_lead_score ON leads (lead_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_leads_status     ON leads (status);

-- RLS: disabled for both tables. Acceptable ONLY for this single-tenant demo, where
-- FastAPI is the sole client and the Supabase key never reaches a browser. A
-- multi-tenant deployment needs auth + org ownership + RLS policies first — see
-- docs/PRODUCTION_ARCHITECTURE.md §2–4. (Enabling RLS here without policies would
-- simply block the backend's writes.)
ALTER TABLE leads DISABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS pipeline_runs (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at     TIMESTAMPTZ DEFAULT NOW(),
  finished_at    TIMESTAMPTZ,
  status         TEXT        NOT NULL DEFAULT 'running'
                 CHECK (status IN ('running', 'completed', 'failed')),
  postal_code    TEXT,
  country_code   TEXT,
  distance       INTEGER,
  leads_scraped  INTEGER     DEFAULT 0,
  leads_enriched INTEGER     DEFAULT 0,
  error_message  TEXT
);

ALTER TABLE pipeline_runs DISABLE ROW LEVEL SECURITY;

-- Migration: scoring redesign (2026-05-26)
ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS convertibility_score     INTEGER CHECK (convertibility_score BETWEEN 1 AND 10),
  ADD COLUMN IF NOT EXISTS convertibility_rationale TEXT,
  ADD COLUMN IF NOT EXISTS distance_miles           NUMERIC(6,2),
  ADD COLUMN IF NOT EXISTS distance_band            TEXT CHECK (distance_band IN ('near','mid','far')),
  ADD COLUMN IF NOT EXISTS priority_index           NUMERIC(4,2);

CREATE INDEX IF NOT EXISTS idx_leads_priority_index ON leads (priority_index DESC NULLS LAST);

-- Migration: pipeline hardening + decision-makers (2026-09-24)
-- Idempotent — safe to run on fresh or existing databases.
ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS segment         TEXT  CHECK (segment IN ('residential', 'commercial')),
  ADD COLUMN IF NOT EXISTS decision_makers JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Profile URLs were previously built as /commercial/{id}, which 404s on gaf.com.
-- The next scrape rewrites them from GAF's own clickUri.

ALTER TABLE pipeline_runs
  ADD COLUMN IF NOT EXISTS segment          TEXT    NOT NULL DEFAULT 'residential'
                                            CHECK (segment IN ('residential', 'commercial')),
  ADD COLUMN IF NOT EXISTS leads_failed     INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE pipeline_runs DROP CONSTRAINT IF EXISTS pipeline_runs_status_check;
ALTER TABLE pipeline_runs ADD CONSTRAINT pipeline_runs_status_check
  CHECK (status IN ('running', 'completed', 'failed', 'cancelled'));

-- At most ONE running pipeline at a time, enforced by the database (race-free):
-- a second concurrent INSERT fails with 23505 and the API answers 409.
CREATE UNIQUE INDEX IF NOT EXISTS one_running_pipeline
  ON pipeline_runs ((true)) WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started_at ON pipeline_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_leads_enriched_at        ON leads (enriched_at DESC NULLS LAST);

NOTIFY pgrst, 'reload schema';
