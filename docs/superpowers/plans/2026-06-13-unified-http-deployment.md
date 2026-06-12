# Unified HTTP Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single HTTP Docker Compose deployment for Hermes Home with FastAPI, Vite static web, Postgres/pgvector, and nginx.

**Architecture:** Build the API and web app into reusable images, run Postgres as the only stateful service, and expose a single nginx entrypoint on port 80. Nginx serves the PWA from the web image and proxies `/api/` to the app container, so the browser uses same-origin API calls with `VITE_API_BASE=`.

**Tech Stack:** Docker Compose, nginx, Python 3.14 slim, FastAPI/Uvicorn, Node 20 build stage, Postgres pgvector.

---

### Task 1: Deployment Contract Tests

**Files:**
- Create: `server/tests/test_deployment_files.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert the production compose file, Dockerfiles, nginx config, env example, restart script, and README/runbook text exist and contain the expected wiring.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && uv --cache-dir /private/tmp/uv-cache run pytest -q tests/test_deployment_files.py`

Expected: failures for missing deployment files.

- [ ] **Step 3: Keep tests focused on public contracts**

The tests should check service names, ports, same-origin `VITE_API_BASE`, nginx `/api/` proxying, health checks, and documented restart commands.

### Task 2: Runtime Images

**Files:**
- Create: `server/Dockerfile`
- Create: `web/Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Implement API Dockerfile**

Build from `python:3.14-slim`, install `server/` plus `psycopg[binary]`, expose `8000`, and start `uvicorn app.main:create_app --factory`.

- [ ] **Step 2: Implement web Dockerfile**

Use `node:20-alpine` to run `npm ci` and `VITE_API_BASE= npm run build`, then copy `web/dist` into an nginx runtime image.

- [ ] **Step 3: Add `.dockerignore`**

Exclude git metadata, virtualenvs, node modules, build outputs, local DB files, and cache artifacts.

### Task 3: Compose And Nginx Stack

**Files:**
- Create: `deploy/compose.prod.yml`
- Create: `deploy/nginx/default.conf`
- Create: `deploy/.env.production.example`

- [ ] **Step 1: Implement compose services**

Create `postgres`, `app`, and `nginx` services. Use named Postgres data volume and bind-mount optional Obsidian vault data from `${OBSIDIAN_VAULT_HOST_PATH:-./data/obsidian-vault}`.

- [ ] **Step 2: Wire nginx**

Expose `${HTTP_PORT:-80}:80`, serve `/usr/share/nginx/html`, use SPA fallback, proxy `/api/` to `http://app:8000`, and disable proxy buffering for streams.

- [ ] **Step 3: Add production env example**

Document required production secrets and provider values: `HOME_API_TOKEN`, `POSTGRES_PASSWORD`, `AGENT_CMD`, Vikunja, Obsidian host path, and public base URL.

### Task 4: Operator Helpers And Docs

**Files:**
- Create: `bin/hermes-home-restart`
- Modify: `README.md`
- Modify: `docs/HERMES_SERVER_INSTALL.md`

- [ ] **Step 1: Add restart helper**

Add a script that runs `docker compose --env-file deploy/.env.production -f deploy/compose.prod.yml up -d --build --force-recreate app nginx` and tails app/nginx status.

- [ ] **Step 2: Update README**

Add a short production section with copyable setup, start, restart, logs, and self-check commands.

- [ ] **Step 3: Update install handoff**

Point the VPS install path at the unified HTTP compose stack and note that HTTPS can be layered later.

### Task 5: Verification

**Files:**
- All deployment files above.

- [ ] **Step 1: Run deployment contract tests**

Run: `cd server && uv --cache-dir /private/tmp/uv-cache run pytest -q tests/test_deployment_files.py`

Expected: all tests pass.

- [ ] **Step 2: Validate compose syntax**

Run: `docker compose --env-file deploy/.env.production.example -f deploy/compose.prod.yml config --quiet`

Expected: exit 0.

- [ ] **Step 3: Run existing server tests**

Run: `cd server && uv --cache-dir /private/tmp/uv-cache run pytest -q`

Expected: all existing server tests pass.

- [ ] **Step 4: Build web**

Run: `cd web && npm run build`

Expected: TypeScript and Vite build succeed.
