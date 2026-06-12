# Hermes Home Server Install Handoff

This document is written for the Hermes agent or operator installing Hermes Home on a server that already runs upstream Hermes.

## Goal

Install Hermes Home beside the existing Hermes agent so a phone/PWA can send commands to the app server, Hermes can use the `hermes-home-mcp` tools, todos are managed in Vikunja, and every job ends as a generated HTML page instead of a chat reply.

The required v1 smoke test is:

1. Open the web app.
2. Submit `add buy oat milk to my todos`.
3. Watch job steps appear.
4. Open the generated page.
5. Click `mark done`.
6. Confirm the todos tile returns to `0` and its back face shows the completed item.

## Assumptions

- Server already has Hermes installed and able to run a named or dedicated `home` profile.
- Server has a Vikunja instance and an API token with task read/write access.
- Server has Docker Compose.
- Server has Python 3.12+ and Node 20+ available on the host.
- Server is reachable over a private network or tailnet. Do not expose this app publicly without adding the deployment's normal auth, TLS, and firewall controls.
- Replace `<repo-url>` below with the GitHub repo URL that contains this project.
- Replace `/opt/hermes-home` with the desired install directory if needed.

## Files That Matter

- `docker-compose.yml`: Postgres with pgvector plus the FastAPI app server.
- `db/schema.sql`: Postgres schema and seed data.
- `server/`: FastAPI app server.
- `mcp/`: Hermes Home MCP server package.
- `skills/`: custom Hermes skills to pin outside autonomous skill curation.
- `web/`: Vite TypeScript PWA.
- `.env.example`: env var template.

## Install The App Server

Clone the repo:

```bash
sudo mkdir -p /opt/hermes-home
sudo chown "$USER":"$USER" /opt/hermes-home
git clone <repo-url> /opt/hermes-home
cd /opt/hermes-home
```

Create the environment file:

```bash
cp .env.example .env
python3 - <<'PY'
from pathlib import Path
import secrets

path = Path(".env")
text = path.read_text()
text = text.replace("HOME_API_TOKEN=dev-token", f"HOME_API_TOKEN={secrets.token_urlsafe(32)}")
text = text.replace("POSTGRES_PASSWORD=hermes_dev_password", f"POSTGRES_PASSWORD={secrets.token_urlsafe(32)}")
text = text.replace("PUBLIC_BASE_URL=http://127.0.0.1:8000", "PUBLIC_BASE_URL=http://127.0.0.1:8000")
path.write_text(text)
PY
```

Edit `.env` and set:

```dotenv
HERMES_ENV=production
CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173,https://<tailnet-hostname>
PUBLIC_BASE_URL=https://<tailnet-hostname>
VITE_API_BASE=
VIKUNJA_URL=https://<vikunja-host>
VIKUNJA_TOKEN=<api-token>
VIKUNJA_DEFAULT_PROJECT_ID=<project-id>
OBSIDIAN_VAULT_PATH=/opt/hermes-home/obsidian-vault
SERVER_PORT=8000
POSTGRES_PORT=5432
CODEX_ENABLED=false
HERMES_STRICT_DEPLOYMENT_CHECKS=true
```

Create the Vikunja API token in Vikunja under Settings > API Tokens. Give it task read/write access for the project Hermes should use for natural-language todo capture. Do not commit the token; keep it only in the deployed `.env`.

Set `OBSIDIAN_VAULT_PATH` to the vault folder that the server can read and write. Hermes Home stores notes as markdown files with YAML frontmatter in that folder; sync the folder externally with Obsidian Sync, Syncthing, iCloud, or your existing vault sync path.

Start Postgres and the app server:

```bash
docker compose up -d postgres app
docker compose ps
docker compose logs --tail=100 app
```

Verify the API:

```bash
set -a
. ./.env
set +a

curl -fsS \
  -H "Authorization: Bearer $HOME_API_TOKEN" \
  http://127.0.0.1:${SERVER_PORT:-8000}/api/tiles
```

Expected: JSON with seeded `jobs`, `todos`, `calendar`, `notes`, `approvals`, and `spend` tiles.

If this server already has legacy notes in the database, export them into the vault once:

```bash
cd /opt/hermes-home/server
set -a
. ../.env
set +a
uv run python -m app.migrate_notes
uv run python -m app.migrate_notes
```

Expected: the first run reports migrated rows, and the second run reports `migrated=0` with skipped rows. The command never deletes database notes.

Run the deployment self-check:

```bash
bin/hermes-deployment-self-check --base-url http://127.0.0.1:${SERVER_PORT:-8000} --token "$HOME_API_TOKEN"
```

Expected: `ok: True` and no `fail` rows. This checks non-default API token state, Codex production gating, database kind, agent configuration, connector setup, and whether the upstream app receives a bearer `Authorization` header.

## Build And Serve The Web App

Build the PWA:

```bash
cd /opt/hermes-home/web
npm ci
VITE_API_BASE= npm run build
```

Leaving `VITE_API_BASE` empty makes the browser call `/api/...` on the same origin that served the app. Use this for nginx deployments that inject the upstream bearer token. Only set `VITE_API_BASE` for separate-origin local development.

Serve `web/dist` with the server's existing static-site mechanism. The simplest tailnet-only option is Caddy or nginx on localhost, then `tailscale serve` in front of it.

Example nginx server block:

```nginx
server {
    listen 127.0.0.1:5173;
    server_name hermes-home.local;
    root /opt/hermes-home/web/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

For a public same-origin nginx deployment, protect the whole site with HTTP Basic Auth and proxy `/api/` to the app server. Keep the real bearer token outside the repo and template it into the deployed nginx config:

```nginx
server {
    listen 80;
    server_name <public-host-or-ip>;
    root /opt/hermes-home/web/dist;
    index index.html;

    auth_basic "Hermes Home";
    auth_basic_user_file /etc/nginx/.hermes-home.htpasswd;

    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization "Bearer <HOME_API_TOKEN>";
        proxy_buffering off;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

Do not add a trailing slash to the `proxy_pass` URL in the `/api/` location; the FastAPI app expects the `/api/...` prefix. Browser users should only enter the Basic Auth username and password. They should not enter `HOME_API_TOKEN` into the app.

After nginx is loaded, test the same-origin token injection path without sending the bearer token from the client:

```bash
bin/hermes-deployment-self-check \
  --base-url http://<public-host-or-ip> \
  --basic '<basic-user>:<basic-password>' \
  --expect-nginx-injection
```

If this returns `401` or reports `request_authorization` as a warning, nginx is not overwriting the browser's Basic `Authorization` header with `Bearer <HOME_API_TOKEN>` before proxying to FastAPI.

If using Tailscale:

```bash
tailscale serve --bg https / http://127.0.0.1:5173
tailscale serve status
```

The PWA needs HTTPS for service worker install behavior on a phone. Tailnet HTTPS is enough for v1.

## Install The MCP Server For Hermes

Create a dedicated Python environment for the MCP package:

```bash
cd /opt/hermes-home
python3 -m venv .venv-mcp
.venv-mcp/bin/pip install -U pip
.venv-mcp/bin/pip install -e './mcp[mcp,postgres]'
```

Smoke test the MCP entrypoint:

```bash
set -a
. /opt/hermes-home/.env
set +a

DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_PORT:-5432}/${POSTGRES_DB}" \
  /opt/hermes-home/.venv-mcp/bin/hermes-home-mcp --help
```

If the MCP runtime does not support `--help`, it may start and wait on stdio. Stop it with `Ctrl-C`; that still proves the entrypoint imports.

Register this stdio server in the Hermes `home` profile. The exact config file depends on the Hermes deployment, but the command should be:

```json
{
  "mcpServers": {
    "hermes-home": {
      "command": "/opt/hermes-home/.venv-mcp/bin/hermes-home-mcp",
      "env": {
        "DATABASE_URL": "postgresql+psycopg://hermes:<password>@127.0.0.1:5432/hermes_home",
        "HOME_API_TOKEN": "<same token as app server>",
        "OBSIDIAN_VAULT_PATH": "/opt/hermes-home/obsidian-vault"
      }
    }
  }
}
```

Use the actual values from `/opt/hermes-home/.env`. Keep this MCP server enabled only for the Hermes `home` profile.

## Install And Pin The Custom Skills

Copy or symlink these directories into the skill path used by the Hermes `home` profile:

```bash
/opt/hermes-home/skills/deliver-as-page
/opt/hermes-home/skills/keep-tiles-fresh
/opt/hermes-home/skills/categorize-notes
```

Pin them outside any autonomous skill curator or consolidation process. These skills define product behavior and should not be silently rewritten.

Hermes must follow these rules in the `home` profile:

- Never answer a Home command with chat prose.
- Always call `pages_publish` before ending a job.
- After state-changing tools, refresh the relevant tile with `tiles_update`.
- Calendar writes must use approval flow in v1.

## Wire The App Server To Hermes

The app server invokes Hermes through `AGENT_CMD`. Set this in `/opt/hermes-home/.env`.

The app server provides these env vars to the command:

- `HERMES_HOME_JOB_ID`: active job id.
- `HERMES_HOME_COMMAND`: user command text.
- `DATABASE_URL`: app database URL.
- `HOME_API_TOKEN`: API bearer token.
- `OBSIDIAN_VAULT_PATH`: Obsidian vault folder for markdown-backed notes.

Example shape:

```dotenv
AGENT_CMD=/usr/local/bin/hermes run --profile home --input-env HERMES_HOME_COMMAND
```

Use the real Hermes CLI/API command for this server. The only hard requirement is that the invoked Hermes process reads `HERMES_HOME_COMMAND`, uses the `home` profile and `hermes-home` MCP server, and publishes through `pages_publish` before exit.

If `AGENT_CMD` is empty, the app server uses a local fallback agent. That is useful for checking the app, but it is not the real Hermes integration.

Restart the app after editing `.env`:

```bash
cd /opt/hermes-home
docker compose up -d app
docker compose logs --tail=100 app
```

Queued or running jobs found during app startup are marked failed with a recovery event. That prevents stuck rows after restart, but it is not a durable worker queue; long-running external job ownership should move to a persistent queue before multi-worker deployment.

## End-To-End Smoke Test

Open the PWA URL from a browser on the tailnet.

Submit:

```text
add buy oat milk to my todos
```

Then verify from the API:

```bash
set -a
. /opt/hermes-home/.env
set +a

curl -fsS -H "Authorization: Bearer $HOME_API_TOKEN" \
  "http://127.0.0.1:${SERVER_PORT:-8000}/api/jobs"

curl -fsS -H "Authorization: Bearer $HOME_API_TOKEN" \
  "http://127.0.0.1:${SERVER_PORT:-8000}/api/todos"

curl -fsS -H "Authorization: Bearer $HOME_API_TOKEN" \
  "http://127.0.0.1:${SERVER_PORT:-8000}/api/tiles"
```

Expected:

- One job reaches `done`.
- The job has a `page_id`.
- `job_events` includes short step logs.
- A page exists and contains no script tags.
- One Vikunja-backed todo is open and includes `provider: "vikunja"` plus an `external_id`.
- The todos tile count is `1` from the refreshed Vikunja cache.
- Clicking the generated page's `mark done` action marks the Vikunja task done and returns the todos tile count to `0`.

## Failure Modes

If the job fails with `agent exited without publishing a page`:

- Hermes ran but did not call `pages_publish`.
- Confirm the `deliver-as-page` skill is installed and active.
- Confirm the `hermes-home` MCP server is registered in the `home` profile.
- Confirm the MCP server receives the same `DATABASE_URL` as the app server.

If todo routes or commands return a Vikunja configuration error:

- Confirm `VIKUNJA_URL` points to the Vikunja instance root or `/api/v1`.
- Confirm `VIKUNJA_TOKEN` is set and has task read/write permissions.
- Confirm `VIKUNJA_DEFAULT_PROJECT_ID` or `VIKUNJA_PROJECT_ID` is set for todo creation.

If the app server cannot connect to Postgres:

```bash
docker compose ps
docker compose logs --tail=100 postgres
docker compose exec postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

If the PWA loads but API calls fail:

- For same-origin nginx, confirm the web app was rebuilt with `VITE_API_BASE=` so requests go to `/api/...` on the public origin.
- Confirm nginx applies `auth_basic` to `/api/` and sets `Authorization: Bearer <HOME_API_TOKEN>` only when proxying upstream.
- Confirm `curl -u '<user>:<password>' http://<public-host-or-ip>/api/session` returns JSON.
- For separate-origin local development, confirm `VITE_API_BASE` was set before `npm run build`, `CORS_ORIGINS` includes the PWA origin, and the browser has the correct token in localStorage key `HOME_API_TOKEN`.

If action buttons do nothing:

- Confirm the generated page has `button data-action="todos.complete"` and valid JSON `data-payload`.
- Confirm the app server supports the action in `server/app/jobs.py`.
- Confirm the shell action button appears below the iframe.

## Upgrade And Rollback

Use `docs/upgrade.md` for Hermes or skill upgrades.

Rollback is:

```bash
cd /opt/hermes-home
git fetch origin
git checkout <last-known-good-ref>
docker compose up -d app
cd web
npm ci
VITE_API_BASE= npm run build
```

Then rerun the end-to-end smoke test.
