from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_production_compose_wires_http_nginx_app_webapp_and_postgres() -> None:
    text = read("deploy/compose.prod.yml")

    assert "postgres:" in text
    assert "pgvector/pgvector:pg16" in text
    assert "app:" in text
    assert "build:" in text
    assert "context: .." in text
    assert "dockerfile: server/Dockerfile" in text
    assert "DATABASE_URL: postgresql+psycopg://" in text
    assert "TODOIST_TOKEN: ${TODOIST_TOKEN:-}" in text
    assert "TODOIST_TOKEN_FILE: ${TODOIST_TOKEN_FILE:-}" in text
    assert "TODOIST_DEFAULT_PROJECT_ID: ${TODOIST_DEFAULT_PROJECT_ID:-}" in text
    assert "TODOIST_TIMEOUT_SECONDS: ${TODOIST_TIMEOUT_SECONDS:-}" in text
    assert "webapp:" in text
    assert "dockerfile: web/Dockerfile" in text
    webapp_block = text.split("  webapp:", 1)[1].split("\n  nginx:", 1)[0]
    assert "ports:" not in webapp_block
    assert "HOME_API_TOKEN" not in webapp_block
    assert "nginx:" in text
    assert "dockerfile: deploy/nginx/Dockerfile" in text
    assert "${HTTP_PORT:-80}:80" in text
    assert "app:" in text and "condition: service_healthy" in text
    assert "webapp:" in text and "condition: service_healthy" in text
    assert "postgres-data:" in text
    assert "${OBSIDIAN_VAULT_HOST_PATH:-./data/obsidian-vault}:/data/obsidian-vault" in text
    assert "${NGINX_HTPASSWD_HOST_PATH:-./nginx/.htpasswd}:/etc/nginx/auth/.htpasswd:ro" in text
    assert "HOME_API_TOKEN: ${HOME_API_TOKEN:?HOME_API_TOKEN is required}" in text
    assert "NGINX_BASIC_AUTH_REALM: ${NGINX_BASIC_AUTH_REALM:-Hermes Home}" in text


def test_nginx_proxies_webapp_and_api_while_enforcing_basic_auth() -> None:
    text = read("deploy/nginx/default.conf.template")

    assert "listen 80" in text
    assert 'auth_basic "${NGINX_BASIC_AUTH_REALM}"' in text
    assert "auth_basic_user_file /etc/nginx/auth/.htpasswd" in text
    assert "location /api/" in text
    assert "proxy_pass http://app:8000" in text
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

    assert "HOME_API_TOKEN=change-me" in env
    assert "POSTGRES_PASSWORD=change-me" in env
    assert "HTTP_PORT=80" in env
    assert "VITE_API_BASE=" in env
    assert "OBSIDIAN_VAULT_HOST_PATH=./data/obsidian-vault" in env
    assert "NGINX_HTPASSWD_HOST_PATH=./nginx/.htpasswd" in env
    assert "NGINX_BASIC_AUTH_REALM=Hermes Home" in env
    assert "AGENT_CMD=" in env
    assert "TODOIST_TOKEN=" in env
    assert "TODOIST_TOKEN_FILE=" in env
    assert "TODOIST_DEFAULT_PROJECT_ID=" in env
    assert "TODOIST_TIMEOUT_SECONDS=10" in env

    assert "docker compose" in restart
    assert 'ENV_FILE="${HERMES_HOME_PROD_ENV_FILE:-deploy/.env.production}"' in restart
    assert 'COMPOSE_FILE="${HERMES_HOME_PROD_COMPOSE_FILE:-deploy/compose.prod.yml}"' in restart
    assert '--env-file "$ENV_FILE"' in restart
    assert '-f "$COMPOSE_FILE"' in restart
    assert "up -d --build --force-recreate app webapp nginx" in restart
    assert "logs --tail=80 app webapp nginx" in restart


def test_docs_describe_unified_http_stack_commands() -> None:
    readme = read("README.md")
    handoff = read("docs/HERMES_SERVER_INSTALL.md")

    assert "Unified HTTP deployment" in readme
    assert "cp deploy/.env.production.example deploy/.env.production" in readme
    assert "openssl passwd -apr1" in readme
    assert "docker compose --env-file deploy/.env.production -f deploy/compose.prod.yml up -d --build" in readme
    assert "webapp" in readme
    assert "bin/hermes-home-restart" in readme
    assert "--expect-nginx-injection" in readme

    assert "Unified HTTP Docker Compose Deployment" in handoff
    assert "deploy/compose.prod.yml" in handoff
    assert "nginx" in handoff
    assert "webapp" in handoff
    assert "Basic Auth" in handoff
    assert "HTTPS can be added later" in handoff
