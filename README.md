# hermes home

Metro-style personal agent app: command in, live job steps, generated page out, action buttons back into state. Todos are backed by the Todoist cloud API; Hermes Home stores Todoist task IDs and cached display fields for rendering tiles and pages.

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
TODOIST_TOKEN=<api-token> \
TODOIST_DEFAULT_PROJECT_ID=<project-id> \
OBSIDIAN_VAULT_PATH=/absolute/path/to/obsidian-vault \
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run the web app:

```bash
cd web
VITE_API_BASE=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173/`.

## Todoist setup

Todos are backed by the Todoist cloud API. There is no self-hosted task service to run.

1. In Todoist, open **Settings -> Integrations -> Developer** and copy your API token.
2. Set `TODOIST_TOKEN` to that value (or point `TODOIST_TOKEN_FILE` at a file containing it).
3. Optionally set `TODOIST_DEFAULT_PROJECT_ID` to the project Hermes Home should use for captured todos. Leave it blank to fall back to the Todoist Inbox.
4. `TODOIST_TIMEOUT_SECONDS` (default `10`) bounds each Todoist API call.

Todoist priority is `1`-`4` where `4` is highest/urgent, labels are plain names, every task belongs to a project, and due dates accept natural language (`due_string`) or explicit `due_date`/`due_datetime`.

## Daily index & search

Notes, todos, and saved items are embedded so they can be searched semantically.

- `EMBEDDING_PROVIDER` selects the embedding backend (`openai` by default; set it to `null` or empty to disable embeddings).
- With the OpenAI provider, set `OPENAI_API_KEY`. `EMBEDDING_MODEL` defaults to `text-embedding-3-small` and `EMBEDDING_DIMENSION` to `1536`.
- An in-process scheduler runs inside the app: `HERMES_SCHEDULER_ENABLED` (default `true`) turns it on, `HERMES_REINDEX_HOUR` (default `3`) sets the daily reindex hour, and `HERMES_FORYOU_INTERVAL_MINUTES` (default `60`) controls how often saved items are enriched.
- Query the index with `GET /api/search` to retrieve semantically ranked notes, todos, and saved items.

## Router profile

The default agent profile is a **router**: it inspects each incoming command and dispatches it to the right specialist agent (todos, notes, or other) instead of handling everything in one place. Plain commands route automatically, so most users never pick an agent by hand.

## Ask tile

Agents can ask the user clarifying questions. Pending questions surface on the home screen in the **Ask** tile, where you answer inline; the answer flows back to the waiting job so it can finish.

## Pocket-style saved items (Apple Shortcut)

Share links into Hermes Home from any iOS app. Shared items land in the **For You** tile after background enrichment.

Build an Apple Shortcut that runs from the Share Sheet:

1. Create a new Shortcut and enable **Show in Share Sheet**, accepting URLs and text as input.
2. Add a **Get Contents of URL** action configured as:
   - **URL:** `https://<your-host>/api/saved-items`
   - **Method:** `POST`
   - **Headers:**
     - `Authorization: Bearer <HOME_API_TOKEN>`
     - `Content-Type: application/json`
   - **Request Body:** JSON
     - `url` -> Shortcut Input (or the Safari URL)
     - `title` -> the item name
     - `text` -> the shared text

   The JSON body looks like:

   ```json
   {"url": "<Shortcut Input / Safari URL>", "title": "<name>", "text": "<shared text>"}
   ```

`HOME_API_TOKEN` is the Bearer token the Shortcut sends; it must match the server's `HOME_API_TOKEN`. After Hermes enriches the item, it appears in the **For You** tile on the home screen.

## Unified HTTP deployment

The VPS deployment runs Postgres, the FastAPI app, a dedicated `webapp` container for the built PWA, and an edge `nginx` container from one Compose file. Nginx serves public traffic on port `80`, proxies `/` to `webapp`, and proxies `/api/` to the app container, so keep `VITE_API_BASE=` empty for same-origin browser requests.

Create production env values:

```bash
cp deploy/.env.production.example deploy/.env.production
python3 - <<'PY'
from pathlib import Path
import secrets

path = Path("deploy/.env.production")
text = path.read_text()
text = text.replace("HOME_API_TOKEN=change-me", f"HOME_API_TOKEN={secrets.token_urlsafe(32)}")
text = text.replace("POSTGRES_PASSWORD=change-me", f"POSTGRES_PASSWORD={secrets.token_urlsafe(32)}")
text = text.replace("VIKUNJA_POSTGRES_PASSWORD=change-me", f"VIKUNJA_POSTGRES_PASSWORD={secrets.token_urlsafe(32)}")
text = text.replace("VIKUNJA_SERVICE_SECRET=change-me", f"VIKUNJA_SERVICE_SECRET={secrets.token_urlsafe(32)}")
path.write_text(text)
PY
```

Edit `deploy/.env.production` for `PUBLIC_BASE_URL`, `CORS_ORIGINS`, Obsidian, and optional `AGENT_CMD`, then start the stack. Vikunja stays internal to the Compose network at `http://vikunja:3456`; nginx does not expose the Vikunja UI or API. If `AGENT_CMD` is set, it must point to a command that exists inside the app container; leave it empty for fallback-mode smoke tests.

Create the nginx Basic Auth password file and the host-side Vikunja token file path:

```bash
mkdir -p deploy/nginx deploy/data/obsidian-vault deploy/vikunja
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

Restart the app, webapp, and nginx after code or env changes:

```bash
bin/hermes-home-restart
```

Inspect logs:

```bash
docker compose --env-file deploy/.env.production -f deploy/compose.prod.yml logs -f app webapp nginx vikunja
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
