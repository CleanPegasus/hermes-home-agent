# hermes home

Metro-style personal agent app: command in, live job steps, generated page out, action buttons back into state. Todos are backed by Vikunja; Hermes Home stores Vikunja task IDs and cached display fields for rendering tiles and pages.

## local run

Install once:

```bash
python3 -m venv .venv
.venv/bin/pip install -e server
cd web && npm install
```

Run the API:

```bash
cd server
HOME_API_TOKEN=dev-token \
DATABASE_URL=sqlite:///./hermes-home-dev.db \
VIKUNJA_URL=http://127.0.0.1:3456 \
VIKUNJA_TOKEN=<api-token> \
VIKUNJA_DEFAULT_PROJECT_ID=<project-id> \
OBSIDIAN_VAULT_PATH=/absolute/path/to/obsidian-vault \
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run the web app:

```bash
cd web
VITE_API_BASE=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173/`.

## Hybrid systemd deployment

FastAPI app runs as a host systemd service so `AGENT_CMD` can call the local Hermes CLI directly. Docker Compose still runs Postgres, Vikunja, the built `webapp`, and edge `nginx`. Nginx serves public traffic on port `80`, proxies `/` to `webapp`, and proxies `/api/` to the host app through `host.docker.internal:8000`, so keep `VITE_API_BASE=` empty for same-origin browser requests.

Create production env values:

```bash
cp deploy/.env.production.example deploy/.env.production
python3 - <<'PY'
from pathlib import Path
import secrets

path = Path("deploy/.env.production")
text = path.read_text()
text = text.replace("HOME_API_TOKEN=change-me", f"HOME_API_TOKEN={secrets.token_urlsafe(32)}")
postgres_password = secrets.token_urlsafe(32)
text = text.replace("POSTGRES_PASSWORD=change-me", f"POSTGRES_PASSWORD={postgres_password}")
text = text.replace("postgresql+psycopg://hermes:change-me@127.0.0.1:5432/hermes_home", f"postgresql+psycopg://hermes:{postgres_password}@127.0.0.1:5432/hermes_home")
text = text.replace("VIKUNJA_POSTGRES_PASSWORD=change-me", f"VIKUNJA_POSTGRES_PASSWORD={secrets.token_urlsafe(32)}")
text = text.replace("VIKUNJA_SERVICE_SECRET=change-me", f"VIKUNJA_SERVICE_SECRET={secrets.token_urlsafe(32)}")
path.write_text(text)
PY
```

Edit `deploy/.env.production` for `PUBLIC_BASE_URL`, `CORS_ORIGINS`, `OBSIDIAN_VAULT_PATH`, and `AGENT_CMD`. The default `AGENT_CMD` expects the Hermes CLI at `/usr/local/bin/hermes` on the VPS host. Vikunja is reachable only on the VPS loopback at `http://127.0.0.1:3456`; nginx does not expose the Vikunja UI or API.

Create the nginx Basic Auth password file, Obsidian vault folder, and host-side Vikunja token file path:

```bash
mkdir -p deploy/nginx deploy/vikunja /opt/hermes-home/obsidian-vault
read -rp "Nginx username: " NGINX_USER
read -rsp "Nginx password: " NGINX_PASSWORD
printf '\n'
printf '%s:%s\n' "$NGINX_USER" "$(openssl passwd -apr1 "$NGINX_PASSWORD")" > deploy/nginx/.htpasswd
unset NGINX_PASSWORD
touch deploy/vikunja/api-token
```

After the first Vikunja user and API token are created, put that token in `deploy/vikunja/api-token` and set `VIKUNJA_DEFAULT_PROJECT_ID` to the project Hermes Home should use for captured todos. Until then, the stack still starts, but todo actions will report that Vikunja is not fully configured.

```bash
docker compose --env-file deploy/.env.production -f deploy/compose.prod.yml up -d --build
docker compose --env-file deploy/.env.production -f deploy/compose.prod.yml ps
```

Install or refresh the host FastAPI app service:

```bash
sudo bin/hermes-home-install-systemd
```

Restart the systemd app plus Docker support services after code or env changes:

```bash
sudo bin/hermes-home-restart
```

Inspect logs:

```bash
journalctl -u hermes-home.service -f
docker compose --env-file deploy/.env.production -f deploy/compose.prod.yml logs -f webapp nginx vikunja
```

Run the deployment self-check:

```bash
set -a
. deploy/.env.production
set +a

bin/hermes-deployment-self-check \
  --base-url http://127.0.0.1:${HTTP_PORT:-80} \
  --basic '<nginx-user>:<nginx-password>' \
  --expect-nginx-injection
```

## verification

```bash
cd server && ../.venv/bin/python -m pytest -q tests/test_api.py
cd web && npm test -- --run && npm run build
.venv/bin/python -m py_compile mcp/hermes_home_mcp/server.py mcp/hermes_home_mcp/__init__.py
docker compose config
```

For end-to-end browser tests, install Playwright from the web package once network access is available:

```bash
cd web
npm install -D @playwright/test@latest
npx playwright install --with-deps
npx playwright test
```

## hermes seam

Set `AGENT_CMD` to hand jobs to upstream Hermes. The app passes:

- `HERMES_HOME_JOB_ID`
- `HERMES_HOME_COMMAND`
- `HOME_API_TOKEN`
- `DATABASE_URL`
- `VIKUNJA_URL`
- `VIKUNJA_TOKEN`
- `VIKUNJA_DEFAULT_PROJECT_ID`
- `OBSIDIAN_VAULT_PATH`

If the command exits without publishing a page through the MCP/page contract, the job is marked failed. If `AGENT_CMD` is empty, the fallback agent creates a Vikunja task and publishes a sanitized generated page for local testing. If Vikunja is not configured, todo commands fail explicitly instead of falling back to local rows.

Notes are markdown files in the configured Obsidian vault. To export legacy DB notes after setting `OBSIDIAN_VAULT_PATH`, run `cd server && uv run python -m app.migrate_notes`; the command is idempotent and does not delete DB rows.

## deployment checks

Production deployments should set a non-default `HOME_API_TOKEN`, keep `VITE_API_BASE` empty for same-origin nginx, and leave `CODEX_ENABLED=false` unless an admin explicitly needs local Codex execution. Run:

```bash
bin/hermes-deployment-self-check --base-url http://127.0.0.1:8000 --token "$HOME_API_TOKEN"
```

For public nginx with Basic Auth and upstream bearer injection, test the browser path without sending the bearer token:

```bash
bin/hermes-deployment-self-check --base-url https://<public-host> --basic '<user>:<password>' --expect-nginx-injection
```

On startup the app marks stale `queued` or `running` rows as failed. A real durable worker/queue is still future work; this quick recovery prevents silent stuck jobs after restart.

## server install handoff

Give [docs/HERMES_SERVER_INSTALL.md](docs/HERMES_SERVER_INSTALL.md) to the Hermes agent or operator installing this on the server that already runs Hermes.
