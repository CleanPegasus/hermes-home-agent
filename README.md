# hermes home

Metro-style personal agent app: command in, live job steps, generated page out, action buttons back into state. The local build uses a deterministic fallback agent when `AGENT_CMD` is empty, so the full loop works before wiring upstream Hermes.

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
HOME_API_TOKEN=dev-token DATABASE_URL=sqlite:///./hermes-home-dev.db ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run the web app:

```bash
cd web
VITE_API_BASE=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173/`.

## verification

```bash
cd server && ../.venv/bin/python -m pytest -q tests/test_api.py
cd web && npm test -- --run && npm run build
.venv/bin/python -m py_compile mcp/hermes_home_mcp/server.py mcp/hermes_home_mcp/__init__.py
docker compose config
```

## hermes seam

Set `AGENT_CMD` to hand jobs to upstream Hermes. The app passes:

- `HERMES_HOME_JOB_ID`
- `HERMES_HOME_COMMAND`
- `HOME_API_TOKEN`
- `DATABASE_URL`

If the command exits without publishing a page through the MCP/page contract, the job is marked failed. If `AGENT_CMD` is empty, the fallback agent creates a todo and publishes a sanitized generated page for local testing.

## server install handoff

Give [docs/HERMES_SERVER_INSTALL.md](docs/HERMES_SERVER_INSTALL.md) to the Hermes agent or operator installing this on the server that already runs Hermes.
