# Hermes Home V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable Hermes Home v1 slice: command in, live job steps, generated page out, action button updates state, no chat UI.

**Architecture:** The app server owns the HTTP API, durable state, SSE event stream, sanitizer, and the `invoke_agent` seam. The web client is a Vite TypeScript Metro shell driven entirely by server JSON. The MCP package and skills define the agent-facing contract without requiring an upstream Hermes clone for local verification.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy, SQLite for local tests/dev, Postgres schema for deployment, Vite + TypeScript, Vitest, plain HTML/CSS.

---

## File Structure

- `docs/PLAN.md`: Copy of the product build plan.
- `docs/upgrade.md`: Hermes version bump and golden-command ritual.
- `.env.example`: Runtime knobs for server, auth, database, and agent invocation.
- `docker-compose.yml`: Postgres + pgvector and app server.
- `db/schema.sql`: Postgres schema and seed data.
- `server/pyproject.toml`: Server package, dependencies, and pytest config.
- `server/app/models.py`: SQLAlchemy table definitions.
- `server/app/db.py`: Engine/session setup plus schema initialization.
- `server/app/sanitize.py`: Generated HTML sanitizer and page wrapper helpers.
- `server/app/jobs.py`: Job creation, fallback agent, AGENT_CMD invocation, page publish, tile refresh.
- `server/app/main.py`: FastAPI routes for tiles, todos, notes, jobs, pages, command, actions, and SSE.
- `server/tests/test_api.py`: End-to-end server tests through the HTTP API.
- `mcp/pyproject.toml`: MCP package metadata.
- `mcp/hermes_home_mcp/server.py`: Tool functions matching the planned MCP contract.
- `skills/deliver-as-page/SKILL.md`: Page-output-only behavior.
- `skills/deliver-as-page/template.html`: Generated page skeleton.
- `skills/keep-tiles-fresh/SKILL.md`: Tile update behavior.
- `skills/categorize-notes/SKILL.md`: Note category behavior.
- `web/package.json`: Vite app scripts and dependencies.
- `web/tsconfig.json`, `web/vite.config.ts`: TypeScript and Vite config.
- `web/index.html`, `web/public/manifest.webmanifest`, `web/public/sw.js`: PWA shell.
- `web/src/*.ts`, `web/src/styles.css`: Metro UI modules.
- `web/src/*.test.ts`: Client unit tests for API helpers and rendering.

## Task 1: Server Contract and Tests

**Files:**
- Create: `server/pyproject.toml`
- Create: `server/app/__init__.py`
- Create: `server/app/models.py`
- Create: `server/app/db.py`
- Create: `server/app/sanitize.py`
- Create: `server/app/jobs.py`
- Create: `server/app/main.py`
- Create: `server/tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Create tests that verify seed tiles, token auth, command-to-page flow, SSE events, action-button handling, and sanitized page storage.

- [ ] **Step 2: Run server tests to verify RED**

Run: `cd server && python -m pytest -q`

Expected: collection or import failures because the app modules do not exist yet.

- [ ] **Step 3: Implement SQLAlchemy models and database setup**

Implement focused models for categories, notes, todos, jobs, job_events, pages, tiles, approvals, and calendar_sync. Use SQLite-compatible JSON/text columns in code so local tests run without Docker while `db/schema.sql` remains the Postgres contract.

- [ ] **Step 4: Implement sanitizer and job pipeline**

Allow semantic generated-page tags, strip scripts/event handlers/external loads, store immutable pages, mark jobs done only through page publish, and provide a deterministic fallback agent when `AGENT_CMD` is not configured.

- [ ] **Step 5: Implement FastAPI routes**

Expose `/api/tiles`, `/api/todos`, `/api/notes`, `/api/jobs`, `/api/jobs/{id}/events`, `/api/pages/{id}`, `/api/command`, and `/api/actions`. Require bearer auth on every `/api/*` route.

- [ ] **Step 6: Run server tests to verify GREEN**

Run: `cd server && python -m pytest -q`

Expected: all tests pass.

## Task 2: Database, Docs, MCP, and Skills

**Files:**
- Create: `docs/PLAN.md`
- Create: `docs/upgrade.md`
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `db/schema.sql`
- Create: `mcp/pyproject.toml`
- Create: `mcp/hermes_home_mcp/__init__.py`
- Create: `mcp/hermes_home_mcp/server.py`
- Create: `skills/deliver-as-page/SKILL.md`
- Create: `skills/deliver-as-page/template.html`
- Create: `skills/keep-tiles-fresh/SKILL.md`
- Create: `skills/categorize-notes/SKILL.md`

- [ ] **Step 1: Write schema and deployment files**

Create the Postgres schema, seed categories, seed starter tiles, compose services, and documented env vars.

- [ ] **Step 2: Implement MCP tool surface**

Expose async tool functions for todos, notes, categories, calendar reads/write approvals, tiles, pages, and approvals. The functions should call the app database layer directly and log job events.

- [ ] **Step 3: Write skills**

Constrain Hermes to publish pages, keep tiles fresh after state changes, and categorize notes with dedupe/cap rules.

- [ ] **Step 4: Verify docs and schema parse**

Run: `python - <<'PY'\nfrom pathlib import Path\nfor p in ['db/schema.sql','.env.example','docker-compose.yml']:\n    assert Path(p).read_text().strip()\nprint('docs ok')\nPY`

Expected: `docs ok`.

## Task 3: Metro Web Client and Tests

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/vite.config.ts`
- Create: `web/index.html`
- Create: `web/public/manifest.webmanifest`
- Create: `web/public/sw.js`
- Create: `web/src/api.ts`
- Create: `web/src/tiles.ts`
- Create: `web/src/jobs.ts`
- Create: `web/src/pages.ts`
- Create: `web/src/todos.ts`
- Create: `web/src/notes.ts`
- Create: `web/src/main.ts`
- Create: `web/src/styles.css`
- Create: `web/src/api.test.ts`
- Create: `web/src/tiles.test.ts`

- [ ] **Step 1: Write failing client tests**

Test authenticated API headers, tile face rendering, and action-button parsing.

- [ ] **Step 2: Run client tests to verify RED**

Run: `cd web && npm test -- --run`

Expected: import failures because modules do not exist yet.

- [ ] **Step 3: Implement API and render modules**

Build a typed API client, live tile renderer, jobs SSE consumer, generated page iframe bridge, todos/notes/calendar/jobs views, and navigation state.

- [ ] **Step 4: Implement Metro CSS and PWA files**

Use black shell, flat semantic accents, lowercase display text, fixed grid units, WP-style input, tile flips, working dots, turnstile page entrance, and reduced-motion fallbacks.

- [ ] **Step 5: Run client tests and build**

Run: `cd web && npm test -- --run && npm run build`

Expected: tests pass and Vite emits `dist/`.

## Task 4: Local Integration

**Files:**
- Modify: `server/app/main.py`
- Modify: `server/app/jobs.py`
- Modify: `web/src/main.ts`

- [ ] **Step 1: Install dependencies**

Run server and web dependency installation from their package files.

- [ ] **Step 2: Start the server**

Run: `cd server && HOME_API_TOKEN=dev-token DATABASE_URL=sqlite:///./hermes-home.db python -m uvicorn app.main:app --reload --port 8000`

Expected: FastAPI listens on `http://127.0.0.1:8000`.

- [ ] **Step 3: Start the web app**

Run: `cd web && VITE_API_BASE=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1 --port 5173`

Expected: Vite listens on `http://127.0.0.1:5173`.

- [ ] **Step 4: Browser verification**

Open the app, submit a command, watch working steps, open the generated page, click a `data-action` button, and confirm the todos tile flips or count changes.

## Self-Review Notes

- The scope intentionally ships a local deterministic fallback agent so v1 can be tested without blocking on upstream Hermes installation.
- The production Hermes seam is isolated to `server/app/jobs.py` through `AGENT_CMD`.
- Calendar writes remain approval-gated; push notifications and full approval execution stay v1.1.
- SQLite is local-only for fast tests. `db/schema.sql` is the deployment contract for Postgres + pgvector.
