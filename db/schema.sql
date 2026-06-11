CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS categories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  color TEXT NOT NULL,
  created_by TEXT NOT NULL DEFAULT 'seed'
    CHECK (created_by IN ('seed', 'agent', 'user')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id UUID REFERENCES categories(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  body_md TEXT NOT NULL DEFAULT '',
  embedding vector(1536),
  source_job_id UUID,
  archived BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS notes_category_created_at_idx ON notes (category_id, created_at DESC);
CREATE INDEX IF NOT EXISTS notes_created_at_idx ON notes (created_at DESC);

CREATE TABLE IF NOT EXISTS todos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  notes TEXT,
  due_at TIMESTAMPTZ,
  scheduled_for TIMESTAMPTZ,
  tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  status TEXT NOT NULL DEFAULT 'open'
    CHECK (status IN ('open', 'done', 'dropped')),
  source TEXT NOT NULL DEFAULT 'user'
    CHECK (source IN ('user', 'agent', 'channel')),
  things_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS todos_status_created_at_idx ON todos (status, created_at DESC);
CREATE INDEX IF NOT EXISTS todos_due_at_idx ON todos (due_at) WHERE due_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  command TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued', 'running', 'done', 'failed', 'needs_approval')),
  page_id UUID,
  error TEXT,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS jobs_status_started_at_idx ON jobs (status, started_at DESC);

CREATE TABLE IF NOT EXISTS pages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  html TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS pages_job_id_idx ON pages (job_id);
CREATE INDEX IF NOT EXISTS pages_created_at_idx ON pages (created_at DESC);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'jobs_page_id_fkey'
      AND conrelid = 'jobs'::regclass
  ) THEN
    ALTER TABLE jobs
      ADD CONSTRAINT jobs_page_id_fkey
      FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE SET NULL;
  END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS job_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  ts TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  kind TEXT NOT NULL DEFAULT 'step'
    CHECK (kind IN ('step', 'tool', 'warn')),
  text TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS job_events_job_ts_idx ON job_events (job_id, ts, id);

CREATE TABLE IF NOT EXISTS tiles (
  key TEXT PRIMARY KEY,
  size TEXT NOT NULL CHECK (size IN ('s', 'm', 'w')),
  color TEXT NOT NULL,
  sort INTEGER NOT NULL,
  front JSONB NOT NULL DEFAULT '{}'::jsonb,
  back JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS tiles_sort_idx ON tiles (sort, key);

CREATE TABLE IF NOT EXISTS approvals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  scope JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
  expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS approvals_status_idx ON approvals (status);

CREATE TABLE IF NOT EXISTS calendar_sync (
  calendar_id TEXT PRIMARY KEY,
  sync_token TEXT,
  last_polled_at TIMESTAMPTZ
);

INSERT INTO categories (slug, name, color, created_by)
VALUES
  ('work', 'work', '#0050EF', 'seed'),
  ('ideas', 'ideas', '#6A00FF', 'seed'),
  ('home', 'home', '#1BA1E2', 'seed'),
  ('personal', 'personal', '#008A00', 'seed'),
  ('health', 'health', '#A4C400', 'seed')
ON CONFLICT (slug) DO UPDATE SET
  name = EXCLUDED.name,
  color = EXCLUDED.color;

INSERT INTO tiles (key, size, color, sort, front, back)
VALUES
  ('jobs', 'w', '#0050EF', 10,
   '{"count":0,"line":"ready","sub":"last finished waits here"}'::jsonb,
   '{"line":"last finished","sub":"nothing yet","glyph":">"}'::jsonb),
  ('todos', 'm', '#1BA1E2', 20,
   '{"count":0,"line":"open","sub":"nothing due"}'::jsonb,
   '{"line":"last finished","sub":"nothing yet","glyph":"check"}'::jsonb),
  ('calendar', 'm', '#FA6800', 30,
   '{"count":0,"line":"today","sub":"no events synced"}'::jsonb,
   '{"line":"next","sub":"calendar read path pending","glyph":"cal"}'::jsonb),
  ('notes', 'm', '#008A00', 40,
   '{"count":0,"line":"filed","sub":"nothing yet"}'::jsonb,
   '{"line":"categories","sub":"work ideas home","glyph":"note"}'::jsonb),
  ('approvals', 's', '#E51400', 50,
   '{"count":0,"line":"appr","sub":""}'::jsonb,
   '{"line":"needs","sub":"none","glyph":"!"}'::jsonb),
  ('spend', 's', '#D80073', 60,
   '{"count":0,"line":"spend","sub":""}'::jsonb,
   '{"line":"quiet","sub":"no tools","glyph":"$"}'::jsonb)
ON CONFLICT (key) DO UPDATE SET
  size = EXCLUDED.size,
  color = EXCLUDED.color,
  sort = EXCLUDED.sort,
  front = EXCLUDED.front,
  back = EXCLUDED.back,
  updated_at = CURRENT_TIMESTAMP;
