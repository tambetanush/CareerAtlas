-- Live job listings shown on the public landing page.
-- Refreshed at most once a week by GET /api/public-jobs/ (app/public_jobs/router.py)
-- using the backend's service key. Not tied to any user.
-- Apply: uv run python scripts/apply_migrations.py 008_public_jobs.sql  (or the Supabase SQL editor)

CREATE TABLE IF NOT EXISTS public_jobs (
    id BIGSERIAL PRIMARY KEY,
    role_title TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT,
    location TEXT,
    apply_url TEXT NOT NULL,
    salary_min NUMERIC,
    salary_max NUMERIC,
    posted_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS public_jobs_fetched_at_idx ON public_jobs (fetched_at DESC);

ALTER TABLE public_jobs ENABLE ROW LEVEL SECURITY;

-- Anyone may read; only the service role (which bypasses RLS) writes.
DROP POLICY IF EXISTS "public_read_public_jobs" ON public_jobs;
CREATE POLICY "public_read_public_jobs" ON public_jobs FOR SELECT USING (true);
