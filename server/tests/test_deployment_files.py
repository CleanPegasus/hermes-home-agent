from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_production_compose_wires_http_nginx_webapp_postgres_vikunja_and_host_api() -> None:
    text = read("deploy/compose.prod.yml")

    assert "postgres:" in text
    assert "pgvector/pgvector:pg16" in text
    assert '"127.0.0.1:${POSTGRES_PORT:-5432}:5432"' in text
    assert "vikunja-postgres:" in text
    assert "POSTGRES_DB: ${VIKUNJA_POSTGRES_DB:-vikunja}" in text
    assert "vikunja:" in text
    assert "image: vikunja/vikunja:${VIKUNJA_IMAGE_TAG:-latest}" in text
    assert "VIKUNJA_DATABASE_TYPE: postgres" in text
    assert "VIKUNJA_DATABASE_HOST: vikunja-postgres" in text
    assert "VIKUNJA_SERVICE_SECRET: ${VIKUNJA_SERVICE_SECRET:?VIKUNJA_SERVICE_SECRET is required}" in text
    assert "vikunja-files:" in text
    assert "/app/vikunja/files" in text
    assert '"127.0.0.1:${VIKUNJA_PORT:-3456}:3456"' in text
    vikunja_block = text.split("  vikunja:", 1)[1].split("\n  nginx:", 1)[0]
    assert "ports:" in vikunja_block
    assert "\n  app:" not in text
    assert "webapp:" in text
    assert "dockerfile: web/Dockerfile" in text
    webapp_block = text.split("  webapp:", 1)[1].split("\n  nginx:", 1)[0]
    assert "ports:" not in webapp_block
    assert "HOME_API_TOKEN" not in webapp_block
    assert "nginx:" in text
    assert "dockerfile: deploy/nginx/Dockerfile" in text
    assert "${HTTP_PORT:-80}:80" in text
    assert "APP_UPSTREAM: ${APP_UPSTREAM:-host.docker.internal:8000}" in text
    assert "host.docker.internal:host-gateway" in text
    nginx_block = text.split("  nginx:", 1)[1].split("\nvolumes:", 1)[0]
    assert "\n      app:" not in nginx_block
    assert "webapp:" in text and "condition: service_healthy" in text
    assert "postgres-data:" in text
    assert "vikunja-postgres-data:" in text
    assert "${NGINX_HTPASSWD_HOST_PATH:-./nginx/.htpasswd}:/etc/nginx/auth/.htpasswd:ro" in text
    assert "HOME_API_TOKEN: ${HOME_API_TOKEN:?HOME_API_TOKEN is required}" in text
    assert "NGINX_BASIC_AUTH_REALM: ${NGINX_BASIC_AUTH_REALM:-Hermes Home}" in text


def test_nginx_proxies_webapp_and_api_while_enforcing_basic_auth() -> None:
    text = read("deploy/nginx/default.conf.template")

    assert "listen 80" in text
    assert 'auth_basic "${NGINX_BASIC_AUTH_REALM}"' in text
    assert "auth_basic_user_file /etc/nginx/auth/.htpasswd" in text
    assert "location /api/" in text
    assert "proxy_pass http://${APP_UPSTREAM}" in text
    assert "proxy_buffering off" in text
    assert 'proxy_set_header Authorization "Bearer ${HOME_API_TOKEN}"' in text
    assert "location /" in text
    assert "proxy_pass http://webapp:80" in text
    assert 'proxy_set_header Authorization ""' in text


def test_runtime_dockerfiles_build_api_and_static_web() -> None:
    server = read("server/Dockerfile")
    web = read("web/Dockerfile")
    edge_nginx = read("deploy/nginx/Dockerfile")
    web_nginx = read("web/nginx/default.conf")

    assert "FROM python:3.14-slim" in server
    assert 'CMD ["python", "-m", "uvicorn", "app.main:create_app"' in server
    assert '"psycopg[binary]>=3.2"' in server
    assert "EXPOSE 8000" in server

    assert "FROM node:20-alpine AS build" in web
    assert "VITE_API_BASE=" in web
    assert "npm run build" in web
    assert "FROM nginx:" in web
    assert "COPY web/nginx/default.conf /etc/nginx/conf.d/default.conf" in web
    assert "COPY --from=build /app/web/dist /usr/share/nginx/html" in web
    assert "root /usr/share/nginx/html" in web_nginx
    assert "try_files $uri $uri/ /index.html" in web_nginx
    assert "COPY deploy/nginx/default.conf.template /etc/nginx/templates/default.conf.template" in edge_nginx


def test_production_env_example_and_restart_helper_are_operator_ready() -> None:
    env = read("deploy/.env.production.example")
    restart = read("bin/hermes-home-restart")
    unit = read("deploy/systemd/hermes-home.service")
    install = read("bin/hermes-home-install-systemd")

    assert "HOME_API_TOKEN=change-me" in env
    assert "POSTGRES_PASSWORD=change-me" in env
    assert "VIKUNJA_POSTGRES_PASSWORD=change-me" in env
    assert "VIKUNJA_SERVICE_SECRET=change-me" in env
    assert "HTTP_PORT=80" in env
    assert "VITE_API_BASE=" in env
    assert "NGINX_HTPASSWD_HOST_PATH=./nginx/.htpasswd" in env
    assert "NGINX_BASIC_AUTH_REALM=Hermes Home" in env
    assert "APP_UPSTREAM=host.docker.internal:8000" in env
    assert "SERVER_PORT=8000" in env
    assert "POSTGRES_PORT=5432" in env
    assert "VIKUNJA_PORT=3456" in env
    assert "AGENT_CMD=/usr/local/bin/hermes run --profile home --input-env HERMES_HOME_COMMAND" in env
    assert "VIKUNJA_URL=http://127.0.0.1:3456" in env
    assert "VIKUNJA_TOKEN_FILE=" in env
    assert "VIKUNJA_API_TOKEN_FILE_HOST_PATH=./vikunja/api-token" in env
    assert "VIKUNJA_DEFAULT_PROJECT_ID=1" in env
    assert "OBSIDIAN_VAULT_PATH=/opt/hermes-home/obsidian-vault" in env

    assert "docker compose" in restart
    assert 'ENV_FILE="${HERMES_HOME_PROD_ENV_FILE:-deploy/.env.production}"' in restart
    assert 'COMPOSE_FILE="${HERMES_HOME_PROD_COMPOSE_FILE:-deploy/compose.prod.yml}"' in restart
    assert 'SYSTEMD_SERVICE="${HERMES_HOME_SYSTEMD_SERVICE:-hermes-home.service}"' in restart
    assert '--env-file "$ENV_FILE"' in restart
    assert '-f "$COMPOSE_FILE"' in restart
    assert "up -d --build --force-recreate postgres vikunja-postgres vikunja webapp nginx" in restart
    assert "systemctl restart \"$SYSTEMD_SERVICE\"" in restart
    assert "journalctl -u \"$SYSTEMD_SERVICE\" -n 80 --no-pager" in restart
    assert "logs --tail=80 webapp nginx vikunja" in restart

    assert "WorkingDirectory=/opt/hermes-home/server" in unit
    assert "EnvironmentFile=/opt/hermes-home/deploy/.env.production" in unit
    assert "ExecStart=/opt/hermes-home/server/.venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000" in unit
    assert "Restart=always" in unit

    assert "python3 -m venv \"$ROOT_DIR/server/.venv\"" in install
    assert "mkdir -p \"$ROOT_DIR/obsidian-vault\"" in install
    assert "pip install --upgrade pip" in install
    assert 'pip install -e "$ROOT_DIR/server" "psycopg[binary]>=3.2"' in install
    assert "systemctl enable --now hermes-home.service" in install


def test_docs_describe_unified_http_stack_commands() -> None:
    readme = read("README.md")
    handoff = read("docs/HERMES_SERVER_INSTALL.md")

    assert "Hybrid systemd deployment" in readme
    assert "cp deploy/.env.production.example deploy/.env.production" in readme
    assert "bin/hermes-home-install-systemd" in readme
    assert "openssl passwd -apr1" in readme
    assert "docker compose --env-file deploy/.env.production -f deploy/compose.prod.yml up -d --build" in readme
    assert "127.0.0.1:3456" in readme
    assert "webapp" in readme
    assert "FastAPI app runs as a host systemd service" in readme
    assert "bin/hermes-home-restart" in readme
    assert "--expect-nginx-injection" in readme

    assert "Hybrid Systemd And Docker Deployment" in handoff
    assert "deploy/compose.prod.yml" in handoff
    assert "nginx" in handoff
    assert "webapp" in handoff
    assert "vikunja" in handoff
    assert "hermes-home.service" in handoff
    assert "host.docker.internal:8000" in handoff
    assert "Basic Auth" in handoff
    assert "HTTPS can be added later" in handoff
