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
  external_id TEXT,
  provider TEXT NOT NULL DEFAULT 'todoist',
  title TEXT NOT NULL,
  notes TEXT,
  due_at TIMESTAMPTZ,
  scheduled_for TIMESTAMPTZ,
  tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  priority INTEGER,
  status TEXT NOT NULL DEFAULT 'open'
    CHECK (status IN ('open', 'done', 'dropped')),
  source TEXT NOT NULL DEFAULT 'user'
    CHECK (source IN ('user', 'agent', 'channel', 'vikunja', 'todoist')),
  things_id TEXT,
  project_id TEXT,
  project_title TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS todos_provider_external_id_idx ON todos (provider, external_id);
CREATE INDEX IF NOT EXISTS todos_status_created_at_idx ON todos (status, created_at DESC);
CREATE INDEX IF NOT EXISTS todos_due_at_idx ON todos (due_at) WHERE due_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  command TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued'
    CONSTRAINT jobs_status_check
    CHECK (status IN ('queued', 'running', 'done', 'failed', 'needs_approval', 'needs_clarification', 'cancelled')),
  page_id UUID,
  error TEXT,
  stdout_tail TEXT,
  stderr_tail TEXT,
  exit_code INTEGER,
  emoji TEXT,
  summary TEXT,
  profile_id TEXT,
  parent_job_id UUID,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS jobs_status_started_at_idx ON jobs (status, started_at DESC);

CREATE TABLE IF NOT EXISTS clarifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  choices JSONB NOT NULL DEFAULT '[]'::jsonb,
  draft JSONB NOT NULL DEFAULT '{}'::jsonb,
  answer TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'answered')),
  follow_up_job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  answered_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS clarifications_job_status_idx ON clarifications (job_id, status);

CREATE TABLE IF NOT EXISTS agent_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  emoji TEXT NOT NULL DEFAULT '🤖',
  color TEXT NOT NULL DEFAULT '#1BA1E2',
  persona TEXT NOT NULL DEFAULT '',
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS agent_profiles_default_idx ON agent_profiles (is_default);

CREATE TABLE IF NOT EXISTS pages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  html TEXT NOT NULL,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  pinned_at TIMESTAMPTZ
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
  expires_at TIMESTAMPTZ,
  decided_at TIMESTAMPTZ,
  result JSONB NOT NULL DEFAULT '{}'::jsonb,
  error TEXT
);

CREATE INDEX IF NOT EXISTS approvals_status_idx ON approvals (status);

CREATE TABLE IF NOT EXISTS action_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  idempotency_key TEXT NOT NULL UNIQUE,
  action TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
  source_page_id UUID REFERENCES pages(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'running'
    CHECK (status IN ('running', 'done', 'failed')),
  result JSONB NOT NULL DEFAULT '{}'::jsonb,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS action_runs_created_at_idx ON action_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS calendar_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  calendar_id TEXT NOT NULL DEFAULT 'primary',
  summary TEXT NOT NULL,
  starts_at TIMESTAMPTZ,
  ends_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'confirmed'
    CHECK (status IN ('confirmed', 'cancelled')),
  source_approval_id UUID REFERENCES approvals(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS calendar_events_starts_at_idx ON calendar_events (starts_at);

CREATE TABLE IF NOT EXISTS channel_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  channel TEXT NOT NULL,
  sender TEXT,
  subject TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'unread'
    CHECK (status IN ('unread', 'read', 'archived')),
  received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS channel_messages_received_at_idx ON channel_messages (received_at DESC);

CREATE TABLE IF NOT EXISTS spend_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant TEXT NOT NULL,
  amount_cents INTEGER NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  category TEXT,
  spent_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS spend_items_spent_at_idx ON spend_items (spent_at DESC);

CREATE TABLE IF NOT EXISTS connector_sync_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  connector TEXT NOT NULL,
  adapter TEXT NOT NULL DEFAULT 'json_file',
  source TEXT,
  status TEXT NOT NULL DEFAULT 'running'
    CHECK (status IN ('running', 'success', 'skipped', 'error')),
  imported INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS connector_sync_runs_connector_started_idx ON connector_sync_runs (connector, started_at DESC);
CREATE INDEX IF NOT EXISTS connector_sync_runs_started_at_idx ON connector_sync_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS codex_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  prompt TEXT NOT NULL,
  effort TEXT NOT NULL DEFAULT 'xhigh'
    CHECK (effort IN ('low', 'medium', 'high', 'xhigh')),
  workdir TEXT NOT NULL,
  command JSONB NOT NULL DEFAULT '[]'::jsonb,
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued', 'running', 'done', 'failed', 'cancelled')),
  process_id INTEGER,
  cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
  before_status TEXT,
  after_status TEXT,
  diff_stat TEXT,
  stdout_tail TEXT,
  stderr_tail TEXT,
  exit_code INTEGER,
  error TEXT,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS codex_runs_started_at_idx ON codex_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS calendar_sync (
  calendar_id TEXT PRIMARY KEY,
  sync_token TEXT,
  last_polled_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS index_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  content_hash TEXT,
  embedding JSONB,
  entry_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  indexed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS index_entries_source_idx ON index_entries (source_type, source_id);

CREATE TABLE IF NOT EXISTS saved_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url TEXT,
  title TEXT NOT NULL DEFAULT 'saved item',
  text TEXT,
  summary TEXT,
  tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  source TEXT NOT NULL DEFAULT 'shortcut'
    CHECK (source IN ('shortcut', 'agent')),
  status TEXT NOT NULL DEFAULT 'new'
    CHECK (status IN ('new', 'enriched', 'surfaced', 'archived')),
  score DOUBLE PRECISION,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  enriched_at TIMESTAMPTZ,
  surfaced_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS saved_items_status_created_idx ON saved_items (status, created_at DESC);

INSERT INTO categories (slug, name, color, created_by)
VALUES
  ('inbox', 'inbox', '#0050EF', 'seed'),
  ('home', 'home', '#1BA1E2', 'seed'),
  ('errands', 'errands', '#FA6800', 'seed'),
  ('health', 'health', '#A4C400', 'seed'),
  ('reference', 'reference', '#008A00', 'seed')
ON CONFLICT (slug) DO UPDATE SET
  name = EXCLUDED.name,
  color = EXCLUDED.color;

INSERT INTO tiles (key, size, color, sort, front, back)
VALUES
  ('jobs', 'w', '#0050EF', 10,
   '{"count":0,"emoji":"⚙️","line":"ready","sub":"last finished waits here"}'::jsonb,
   '{"line":"last finished","sub":"nothing yet","glyph":">"}'::jsonb),
  ('todos', 'm', '#1BA1E2', 20,
   '{"count":0,"emoji":"✅","line":"open","sub":"nothing due"}'::jsonb,
   '{"line":"last finished","sub":"nothing yet","glyph":"check"}'::jsonb),
  ('calendar', 'm', '#FA6800', 30,
   '{"count":0,"emoji":"📅","line":"today","sub":"no events synced"}'::jsonb,
   '{"line":"next","sub":"calendar read path pending","glyph":"cal"}'::jsonb),
  ('notes', 'm', '#008A00', 40,
   '{"count":0,"emoji":"📝","line":"filed","sub":"nothing yet"}'::jsonb,
   '{"line":"categories","sub":"inbox home errands","glyph":"note"}'::jsonb),
  ('ask', 'm', '#AA00FF', 22,
   '{"count":0,"emoji":"❓","line":"ask","sub":"no open questions"}'::jsonb,
   '{"line":"waiting on you","sub":"all clear","glyph":"?"}'::jsonb),
  ('foryou', 'm', '#F0A30A', 45,
   '{"count":0,"emoji":"✨","line":"for you","sub":"share to save"}'::jsonb,
   '{"line":"saved","sub":"all caught up","glyph":">"}'::jsonb),
  ('approvals', 's', '#E51400', 50,
   '{"count":0,"emoji":"🛡️","line":"appr","sub":""}'::jsonb,
   '{"line":"needs","sub":"none","glyph":"!"}'::jsonb),
  ('spend', 's', '#D80073', 60,
   '{"count":0,"emoji":"💸","line":"spend","sub":""}'::jsonb,
   '{"line":"quiet","sub":"no tools","glyph":"$"}'::jsonb),
  ('channels', 's', '#00ABA9', 70,
   '{"count":0,"emoji":"📨","line":"inbox","sub":""}'::jsonb,
   '{"line":"quiet","sub":"no connectors","glyph":"@"}'::jsonb),
  ('vitals', 's', '#A4C400', 80,
   '{"count":0,"emoji":"💓","line":"ok","sub":""}'::jsonb,
   '{"line":"system","sub":"local","glyph":"pulse"}'::jsonb),
  ('codex', 's', '#647687', 90,
   '{"emoji":"🛠️","glyph":"gear","line":"codex","sub":"yolo"}'::jsonb,
   '{"line":"web dir","sub":"feature work","glyph":">"}'::jsonb),
  ('history', 'w', '#0050EF', 95,
   '{"emoji":"🕘","line":"history","sub":"recent chats"}'::jsonb,
   '{"line":"timeline","sub":"summaries","glyph":">"}'::jsonb),
  ('profiles', 'w', '#A20025', 85,
   '{"emoji":"🎭","line":"profiles","sub":"agent modes"}'::jsonb,
   '{"line":"personas","sub":"choose a voice","glyph":">"}'::jsonb)
ON CONFLICT (key) DO UPDATE SET
  size = EXCLUDED.size,
  color = EXCLUDED.color,
  sort = EXCLUDED.sort,
  front = EXCLUDED.front,
  back = EXCLUDED.back,
  updated_at = CURRENT_TIMESTAMP;

INSERT INTO agent_profiles (slug, name, emoji, color, persona, is_default)
VALUES
  ('router', 'router', '🧭', '#0050EF', 'You are Hermes'' router. Read the incoming command and route it: todos to todos_create, notes to notes_create, and real work to jobs_handoff with the best profile. Never do the downstream work yourself.', TRUE),
  ('personal-assistant', 'personal assistant', '🪄', '#1BA1E2', 'You are a calm personal assistant for home operations. Prefer concise plans, clear next actions, and safe defaults.', FALSE),
  ('research-agent', 'research agent', '🧠', '#0050EF', 'You are a careful research agent. Gather context, cite sources when available, and summarize findings plainly.', FALSE),
  ('coding-agent', 'coding agent', '💻', '#647687', 'You are a coding agent. Read the repo first, write tests for behavior changes, and keep diffs focused.', FALSE),
  ('financial-helper', 'financial helper', '💰', '#D80073', 'You are a financial helper. Be conservative, separate facts from assumptions, and flag anything that needs review.', FALSE)
ON CONFLICT (slug) DO NOTHING;
