from __future__ import annotations

import json
import os
import re
import sqlite3
import importlib.util
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID, uuid4

import httpx

try:
    from .vault import VaultConfigurationError, VaultNoteNotFoundError, VaultStore
except ImportError:  # pragma: no cover - direct file import in tests
    _vault_spec = importlib.util.spec_from_file_location("hermes_home_mcp_vault", Path(__file__).with_name("vault.py"))
    if _vault_spec is None or _vault_spec.loader is None:
        raise
    _vault_module = importlib.util.module_from_spec(_vault_spec)
    _vault_spec.loader.exec_module(_vault_module)
    VaultConfigurationError = _vault_module.VaultConfigurationError
    VaultNoteNotFoundError = _vault_module.VaultNoteNotFoundError
    VaultStore = _vault_module.VaultStore

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
except Exception:  # pragma: no cover
    create_engine = None
    text = None
    Engine = Any  # type: ignore[misc,assignment]

try:
    from fastmcp import FastMCP
except Exception:  # pragma: no cover
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:  # pragma: no cover
        FastMCP = None  # type: ignore[assignment]

try:
    import nh3
except Exception:  # pragma: no cover
    nh3 = None  # type: ignore[assignment]


DEFAULT_DATABASE_URL = "sqlite:///./hermes-home.db"
JSON_COLUMNS = {"front", "back", "scope", "tags", "embedding", "payload", "result", "provenance"}
_ENGINE: Engine | None = None
_ENGINE_URL: str | None = None

ALLOWED_PAGE_TAGS = {
    "a",
    "article",
    "blockquote",
    "body",
    "br",
    "button",
    "caption",
    "code",
    "div",
    "em",
    "footer",
    "head",
    "h1",
    "h2",
    "h3",
    "header",
    "html",
    "li",
    "main",
    "meta",
    "ol",
    "p",
    "pre",
    "section",
    "span",
    "strong",
    "style",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "time",
    "title",
    "tr",
    "ul",
}

ALLOWED_PAGE_ATTRIBUTES = {
    "*": {"aria-label", "class", "data-action", "data-payload", "data-role"},
    "a": {"rel", "title"},
    "button": {"type", "data-action", "data-payload", "aria-label", "class"},
    "html": {"lang"},
    "meta": {"charset", "name", "content"},
}


SQLITE_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS categories (
      id TEXT PRIMARY KEY,
      slug TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      color TEXT NOT NULL,
      created_by TEXT NOT NULL DEFAULT 'seed',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notes (
      id TEXT PRIMARY KEY,
      category_id TEXT,
      title TEXT NOT NULL,
      body_md TEXT NOT NULL DEFAULT '',
      embedding TEXT,
      source_job_id TEXT,
      archived INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS todos (
      id TEXT PRIMARY KEY,
      external_id TEXT,
      provider TEXT NOT NULL DEFAULT 'vikunja',
      title TEXT NOT NULL,
      notes TEXT,
      due_at TEXT,
      scheduled_for TEXT,
      tags TEXT NOT NULL DEFAULT '[]',
      priority INTEGER,
      status TEXT NOT NULL DEFAULT 'open',
      source TEXT NOT NULL DEFAULT 'user',
      things_id TEXT,
      project_id TEXT,
      project_title TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      completed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY,
      command TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'queued',
      page_id TEXT,
      error TEXT,
      stdout_tail TEXT,
      stderr_tail TEXT,
      exit_code INTEGER,
      emoji TEXT,
      summary TEXT,
      profile_id TEXT,
      started_at TEXT,
      finished_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_profiles (
      id TEXT PRIMARY KEY,
      slug TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      emoji TEXT NOT NULL DEFAULT '🤖',
      color TEXT NOT NULL DEFAULT '#1BA1E2',
      persona TEXT NOT NULL DEFAULT '',
      is_default INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pages (
      id TEXT PRIMARY KEY,
      job_id TEXT,
      title TEXT NOT NULL,
      html TEXT NOT NULL,
      provenance TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      pinned_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_events (
      id TEXT PRIMARY KEY,
      job_id TEXT NOT NULL,
      ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      kind TEXT NOT NULL DEFAULT 'step',
      text TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tiles (
      key TEXT PRIMARY KEY,
      size TEXT NOT NULL,
      color TEXT NOT NULL,
      sort INTEGER NOT NULL,
      front TEXT NOT NULL DEFAULT '{}',
      back TEXT NOT NULL DEFAULT '{}',
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS approvals (
      id TEXT PRIMARY KEY,
      job_id TEXT,
      action TEXT NOT NULL,
      scope TEXT NOT NULL DEFAULT '{}',
      status TEXT NOT NULL DEFAULT 'pending',
      expires_at TEXT,
      decided_at TEXT,
      result TEXT NOT NULL DEFAULT '{}',
      error TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_runs (
      id TEXT PRIMARY KEY,
      idempotency_key TEXT NOT NULL UNIQUE,
      action TEXT NOT NULL,
      payload TEXT NOT NULL DEFAULT '{}',
      source_job_id TEXT,
      source_page_id TEXT,
      status TEXT NOT NULL DEFAULT 'running',
      result TEXT NOT NULL DEFAULT '{}',
      error TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS calendar_events (
      id TEXT PRIMARY KEY,
      calendar_id TEXT NOT NULL DEFAULT 'primary',
      summary TEXT NOT NULL,
      starts_at TEXT,
      ends_at TEXT,
      status TEXT NOT NULL DEFAULT 'confirmed',
      source_approval_id TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS channel_messages (
      id TEXT PRIMARY KEY,
      channel TEXT NOT NULL,
      sender TEXT,
      subject TEXT NOT NULL,
      body TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'unread',
      received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spend_items (
      id TEXT PRIMARY KEY,
      merchant TEXT NOT NULL,
      amount_cents INTEGER NOT NULL,
      currency TEXT NOT NULL DEFAULT 'USD',
      category TEXT,
      spent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS connector_sync_runs (
      id TEXT PRIMARY KEY,
      connector TEXT NOT NULL,
      adapter TEXT NOT NULL DEFAULT 'json_file',
      source TEXT,
      status TEXT NOT NULL DEFAULT 'running',
      imported INTEGER NOT NULL DEFAULT 0,
      error TEXT,
      started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      finished_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS codex_runs (
      id TEXT PRIMARY KEY,
      prompt TEXT NOT NULL,
      effort TEXT NOT NULL DEFAULT 'xhigh',
      workdir TEXT NOT NULL,
      command TEXT NOT NULL DEFAULT '[]',
      status TEXT NOT NULL DEFAULT 'queued',
      process_id INTEGER,
      cancel_requested INTEGER NOT NULL DEFAULT 0,
      before_status TEXT,
      after_status TEXT,
      diff_stat TEXT,
      stdout_tail TEXT,
      stderr_tail TEXT,
      exit_code INTEGER,
      error TEXT,
      started_at TEXT,
      finished_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS calendar_sync (
      calendar_id TEXT PRIMARY KEY,
      sync_token TEXT,
      last_polled_at TEXT
    )
    """,
]

SEED_CATEGORIES = [
    ("inbox", "inbox", "#0050EF"),
    ("home", "home", "#1BA1E2"),
    ("errands", "errands", "#FA6800"),
    ("health", "health", "#A4C400"),
    ("reference", "reference", "#008A00"),
]


def database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def is_sqlite_url(url: str | None = None) -> bool:
    return (url or database_url()).startswith("sqlite:")


def is_postgres_url(url: str | None = None) -> bool:
    value = url or database_url()
    return value.startswith("postgresql:") or value.startswith("postgres:")


def sqlite_path(url: str | None = None) -> str:
    value = url or database_url()
    if value == "sqlite:///:memory:":
        return ":memory:"
    prefix = "sqlite:///"
    if not value.startswith(prefix):
        raise RuntimeError(f"sqlite fallback only supports sqlite URLs, got {value!r}")
    return value[len(prefix):] or "hermes-home.db"


def current_job_id() -> str | None:
    value = os.getenv("HERMES_HOME_JOB_ID", "").strip()
    if not value:
        return None
    return sqlite_uuid_storage_value(value) if is_sqlite_url() else value


def new_id() -> str:
    value = uuid4()
    return value.hex if is_sqlite_url() else str(value)


def sqlite_uuid_storage_value(value: str) -> str:
    try:
        return UUID(str(value)).hex
    except ValueError:
        return value


def dumps_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, separators=(",", ":"), sort_keys=True)


def loads_json(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    for key in JSON_COLUMNS:
        if key in normalized:
            normalized[key] = loads_json(normalized[key])
    return normalized


def json_expr(name: str) -> str:
    if is_postgres_url():
        return f"CAST(:{name} AS jsonb)"
    return f":{name}"


class VikunjaMCPError(RuntimeError):
    pass


def vault_store() -> VaultStore:
    store = VaultStore(os.getenv("OBSIDIAN_VAULT_PATH"))
    if not store.configured():
        raise VikunjaMCPError("OBSIDIAN_VAULT_PATH is not configured. Set it to your Obsidian vault folder to use notes.")
    return store


def vault_error(exc: Exception) -> VikunjaMCPError:
    if isinstance(exc, VaultConfigurationError):
        return VikunjaMCPError("OBSIDIAN_VAULT_PATH is not configured. Set it to your Obsidian vault folder to use notes.")
    if isinstance(exc, VaultNoteNotFoundError):
        return VikunjaMCPError("note not found")
    return VikunjaMCPError(str(exc))


def vikunja_config() -> dict[str, Any]:
    raw_url = os.getenv("VIKUNJA_URL", "").strip()
    token = vikunja_token_from_env()
    missing = []
    if not raw_url:
        missing.append("VIKUNJA_URL")
    if not token:
        missing.append("VIKUNJA_TOKEN or VIKUNJA_TOKEN_FILE")
    if missing:
        raise VikunjaMCPError(
            f"Vikunja todo integration is not configured. Set {', '.join(missing)} to use todos."
        )
    default_project_id = (
        os.getenv("VIKUNJA_DEFAULT_PROJECT_ID", "").strip()
        or os.getenv("VIKUNJA_PROJECT_ID", "").strip()
        or None
    )
    return {
        "api_url": normalize_vikunja_api_url(raw_url),
        "token": token,
        "default_project_id": default_project_id,
        "timeout": float(os.getenv("VIKUNJA_TIMEOUT_SECONDS", "10")),
    }


def vikunja_token_from_env() -> str:
    token = os.getenv("VIKUNJA_TOKEN", "").strip()
    if token:
        return token
    token_file = os.getenv("VIKUNJA_TOKEN_FILE", "").strip()
    if not token_file:
        return ""
    path = Path(token_file).expanduser()
    try:
        file_token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise VikunjaMCPError(f"Could not read VIKUNJA_TOKEN_FILE {path}: {exc.strerror}") from exc
    if not file_token:
        raise VikunjaMCPError(f"VIKUNJA_TOKEN_FILE {path} is empty")
    return file_token


def normalize_vikunja_api_url(raw_url: str) -> str:
    value = raw_url.strip().rstrip("/")
    if value.endswith("/api/v1"):
        return value
    if value.endswith("/api"):
        return f"{value}/v1"
    return f"{value}/api/v1"


def vikunja_request(method: str, path: str, body: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> Any:
    config = vikunja_config()
    headers = {"accept": "application/json", "authorization": f"Bearer {config['token']}"}
    if body is not None:
        headers["content-type"] = "application/json"
    try:
        with httpx.Client(timeout=config["timeout"]) as client:
            response = client.request(
                method,
                f"{config['api_url']}{path}",
                headers=headers,
                json=body,
                params=params,
            )
    except httpx.TimeoutException as exc:
        raise VikunjaMCPError(f"Vikunja request timed out: {method} {path}") from exc
    except httpx.RequestError as exc:
        raise VikunjaMCPError(f"Vikunja request failed: {exc}") from exc
    if response.status_code >= 400:
        raise VikunjaMCPError(f"Vikunja request failed ({response.status_code}): {vikunja_error_text(response)}")
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise VikunjaMCPError("Vikunja returned invalid JSON") from exc


def vikunja_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:500] or response.reason_phrase
    if isinstance(payload, dict):
        for key in ("message", "detail", "error"):
            if payload.get(key):
                return str(payload[key])
    return str(payload)[:500]


def normalize_vikunja_task(task: dict[str, Any]) -> dict[str, Any]:
    external_id = str(task.get("id") or "").strip()
    if not external_id:
        raise VikunjaMCPError("Vikunja task is missing an id")
    project_id = optional_text(task.get("project_id"))
    labels = task.get("labels")
    if not isinstance(labels, list):
        labels = []
    return {
        "external_id": external_id,
        "provider": "vikunja",
        "title": str(task.get("title") or "untitled task").strip() or "untitled task",
        "notes": optional_text(task.get("description")),
        "due_at": clean_vikunja_datetime(task.get("due_date")),
        "scheduled_for": clean_vikunja_datetime(task.get("start_date")),
        "tags": [label["title"] for label in labels if isinstance(label, dict) and label.get("title")],
        "priority": optional_int(task.get("priority")),
        "status": "done" if bool(task.get("done")) else "open",
        "project_id": project_id,
        "project_title": f"project {project_id}" if project_id else None,
        "created_at": clean_vikunja_datetime(task.get("created")),
        "updated_at": clean_vikunja_datetime(task.get("updated")),
        "completed_at": clean_vikunja_datetime(task.get("done_at")),
    }


def clean_vikunja_datetime(value: Any) -> str | None:
    text_value = optional_text(value)
    if not text_value or text_value.startswith("0001-01-01"):
        return None
    return text_value


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def vikunja_projects() -> list[dict[str, Any]]:
    payload = vikunja_request("GET", "/projects")
    if not isinstance(payload, list):
        raise VikunjaMCPError("Vikunja returned an unexpected projects payload")
    return [project for project in payload if isinstance(project, dict)]


def vikunja_labels() -> list[dict[str, Any]]:
    payload = vikunja_request("GET", "/labels")
    if not isinstance(payload, list):
        raise VikunjaMCPError("Vikunja returned an unexpected labels payload")
    return [label for label in payload if isinstance(label, dict)]


def ensure_vikunja_label(title: str) -> dict[str, Any]:
    normalized = title.strip().lower()
    for label in vikunja_labels():
        if str(label.get("title", "")).strip().lower() == normalized:
            return label
    payload = vikunja_request("PUT", "/labels", body={"title": normalized})
    if not isinstance(payload, dict):
        raise VikunjaMCPError("Vikunja returned an unexpected label payload")
    return payload


def set_vikunja_task_labels(task_id: str, label_ids: list[str]) -> None:
    for label_id in label_ids:
        try:
            vikunja_request("PUT", f"/tasks/{task_id}/labels", body={"label_id": label_id})
        except VikunjaMCPError:
            continue


def refresh_vikunja_todo_cache() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in range(1, 6):
        payload = vikunja_request(
            "GET",
            "/tasks",
            params={"page": page, "per_page": 200, "sort_by": "updated", "order_by": "desc"},
        )
        if not isinstance(payload, list):
            raise VikunjaMCPError("Vikunja returned an unexpected tasks payload")
        for item in payload:
            if isinstance(item, dict):
                row = upsert_vikunja_todo_cache(normalize_vikunja_task(item))
                rows.append(row)
                seen.add(str(row["external_id"]))
        if len(payload) < 200:
            break
    for row in fetch_all("SELECT * FROM todos WHERE provider = 'vikunja' AND external_id IS NOT NULL"):
        if row["external_id"] not in seen and row["status"] != "dropped":
            execute(
                "UPDATE todos SET status = 'dropped', completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
                {"id": row["id"]},
            )
    return rows


def upsert_vikunja_todo_cache(task: dict[str, Any], source: str | None = None) -> dict[str, Any]:
    existing = fetch_one(
        "SELECT * FROM todos WHERE provider = 'vikunja' AND external_id = :external_id",
        {"external_id": task["external_id"]},
    )
    params = {
        **task,
        "id": existing["id"] if existing else new_id(),
        "tags_value": task.get("tags") or [] if is_postgres_url() else dumps_json(task.get("tags") or []),
        "source": source if source in {"user", "agent", "channel"} else (existing or {}).get("source", "user"),
    }
    if existing:
        return one_required(
            f"""
            UPDATE todos
            SET title = :title,
                notes = :notes,
                due_at = :due_at,
                scheduled_for = :scheduled_for,
                tags = :tags_value,
                priority = :priority,
                status = :status,
                source = :source,
                project_id = :project_id,
                project_title = :project_title,
                updated_at = COALESCE(:updated_at, CURRENT_TIMESTAMP),
                completed_at = :completed_at
            WHERE id = :id
            RETURNING *
            """,
            params,
        )
    return one_required(
        f"""
        INSERT INTO todos (
          id, external_id, provider, title, notes, due_at, scheduled_for, tags,
          priority, status, source, project_id, project_title, created_at, updated_at, completed_at
        )
        VALUES (
          :id, :external_id, 'vikunja', :title, :notes, :due_at, :scheduled_for, :tags_value,
          :priority, :status, :source, :project_id, :project_title,
          COALESCE(:created_at, CURRENT_TIMESTAMP), COALESCE(:updated_at, CURRENT_TIMESTAMP), :completed_at
        )
        RETURNING *
        """,
        params,
    )


def resolve_vikunja_todo(todo_id: str) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT * FROM todos
        WHERE provider = 'vikunja'
          AND external_id IS NOT NULL
          AND (id = :todo_id OR external_id = :todo_id)
        """,
        {"todo_id": todo_id},
    )
    if row is None:
        raise VikunjaMCPError("todo not found")
    return row


def ensure_sqlite_schema(connection: Any) -> None:
    for statement in SQLITE_SCHEMA:
        if hasattr(connection, "exec_driver_sql"):
            connection.exec_driver_sql(statement)
        else:
            connection.execute(statement)
    ensure_sqlite_column(connection, "pages", "pinned_at", "TEXT")
    ensure_sqlite_column(connection, "pages", "provenance", "TEXT NOT NULL DEFAULT '{}'")
    ensure_sqlite_column(connection, "approvals", "decided_at", "TEXT")
    ensure_sqlite_column(connection, "approvals", "result", "TEXT NOT NULL DEFAULT '{}'")
    ensure_sqlite_column(connection, "approvals", "error", "TEXT")
    ensure_sqlite_column(connection, "jobs", "stdout_tail", "TEXT")
    ensure_sqlite_column(connection, "jobs", "stderr_tail", "TEXT")
    ensure_sqlite_column(connection, "jobs", "exit_code", "INTEGER")
    ensure_sqlite_column(connection, "jobs", "emoji", "TEXT")
    ensure_sqlite_column(connection, "jobs", "summary", "TEXT")
    ensure_sqlite_column(connection, "jobs", "profile_id", "TEXT")
    ensure_sqlite_column(connection, "action_runs", "source_job_id", "TEXT")
    ensure_sqlite_column(connection, "action_runs", "source_page_id", "TEXT")
    ensure_sqlite_column(connection, "codex_runs", "effort", "TEXT NOT NULL DEFAULT 'xhigh'")
    ensure_sqlite_column(connection, "todos", "external_id", "TEXT")
    ensure_sqlite_column(connection, "todos", "provider", "TEXT NOT NULL DEFAULT 'vikunja'")
    ensure_sqlite_column(connection, "todos", "project_id", "TEXT")
    ensure_sqlite_column(connection, "todos", "project_title", "TEXT")
    ensure_sqlite_column(connection, "todos", "priority", "INTEGER")
    ensure_sqlite_column(connection, "todos", "updated_at", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
    for slug, name, color in SEED_CATEGORIES:
        params = {"id": new_id(), "slug": slug, "name": name, "color": color}
        statement = """
        INSERT OR IGNORE INTO categories (id, slug, name, color, created_by)
        VALUES (:id, :slug, :name, :color, 'seed')
        """
        if hasattr(connection, "exec_driver_sql"):
            connection.execute(text(statement), params)
        else:
            connection.execute(statement, params)


def ensure_sqlite_column(connection: Any, table: str, column: str, ddl: str) -> None:
    if hasattr(connection, "exec_driver_sql"):
        rows = connection.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
        columns = {row[1] for row in rows}
        if column not in columns:
            connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        return
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    columns = {row[1] for row in rows}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def get_engine() -> Engine:
    global _ENGINE, _ENGINE_URL
    if create_engine is None:
        raise RuntimeError("SQLAlchemy is required for this database URL")
    url = database_url()
    if _ENGINE is None or _ENGINE_URL != url:
        connect_args = {"check_same_thread": False} if is_sqlite_url(url) else {}
        _ENGINE = create_engine(url, connect_args=connect_args, future=True)
        _ENGINE_URL = url
    return _ENGINE


@contextmanager
def sqlite_connection() -> Iterable[sqlite3.Connection]:
    path = sqlite_path()
    if path != ":memory:":
        Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        ensure_sqlite_schema(connection)
        yield connection
        connection.commit()
    finally:
        connection.close()


def fetch_all(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    params = params or {}
    if create_engine is not None:
        with get_engine().begin() as connection:
            if is_sqlite_url():
                ensure_sqlite_schema(connection)
            result = connection.execute(text(sql), params)
            return [normalize_row(dict(row)) for row in result.mappings().all()]
    if not is_sqlite_url():
        raise RuntimeError("Postgres URLs require SQLAlchemy and a driver")
    with sqlite_connection() as connection:
        cursor = connection.execute(sql, params)
        return [normalize_row(dict(row)) for row in cursor.fetchall()]


def fetch_one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: dict[str, Any] | None = None) -> None:
    params = params or {}
    if create_engine is not None:
        with get_engine().begin() as connection:
            if is_sqlite_url():
                ensure_sqlite_schema(connection)
            connection.execute(text(sql), params)
        return
    if not is_sqlite_url():
        raise RuntimeError("Postgres URLs require SQLAlchemy and a driver")
    with sqlite_connection() as connection:
        connection.execute(sql, params)


def one_required(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    row = fetch_one(sql, params)
    if row is None:
        raise RuntimeError("database operation did not return a row")
    return row


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "note"


def sanitize_page_html(html: str) -> str:
    if nh3 is not None:
        cleaned = nh3.clean(
            html,
            tags=ALLOWED_PAGE_TAGS,
            clean_content_tags=set(),
            attributes=ALLOWED_PAGE_ATTRIBUTES,
            url_schemes=set(),
            link_rel=None,
            strip_comments=True,
        )
    else:
        cleaned = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"\s+on[a-z]+\s*=\s*(['\"]).*?\1", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"\s+(src|href)\s*=\s*(['\"]).*?\2", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"@import\s+[^;]+;", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"url\(\s*(['\"])?[^)]*?\1\s*\)", "none", cleaned, flags=re.IGNORECASE)
    return cleaned


async def log_job_event(text_value: str, kind: str = "tool", job_id: str | None = None) -> dict[str, Any]:
    target_job_id = job_id or current_job_id()
    if target_job_id is None:
        return {"logged": False, "reason": "HERMES_HOME_JOB_ID is not set"}
    row = one_required(
        """
        INSERT INTO job_events (id, job_id, ts, kind, text)
        VALUES (:id, :job_id, CURRENT_TIMESTAMP, :kind, :text)
        RETURNING *
        """,
        {"id": new_id(), "job_id": target_job_id, "kind": kind, "text": text_value.strip()},
    )
    return {"logged": True, "event": row}


async def safe_log(text_value: str, kind: str = "tool") -> None:
    try:
        await log_job_event(text_value=text_value, kind=kind)
    except Exception:
        return


async def categories_list() -> dict[str, Any]:
    rows = fetch_all("SELECT * FROM categories ORDER BY created_at, slug")
    await safe_log(f"categories_list returned {len(rows)} categories")
    return {"categories": rows}


async def categories_create(name: str, color: str = "#6A00FF", slug: str | None = None) -> dict[str, Any]:
    resolved_slug = slugify(slug or name)
    count = int((fetch_one("SELECT COUNT(*) AS count FROM categories") or {"count": 0})["count"])
    existing = fetch_one("SELECT * FROM categories WHERE slug = :slug", {"slug": resolved_slug})
    if existing:
        return {"category": existing, "created": False}
    if count >= 12:
        raise ValueError("category cap reached")
    row = one_required(
        """
        INSERT INTO categories (id, slug, name, color, created_by, created_at)
        VALUES (:id, :slug, :name, :color, 'agent', CURRENT_TIMESTAMP)
        RETURNING *
        """,
        {"id": new_id(), "slug": resolved_slug, "name": name.strip().lower(), "color": color},
    )
    await safe_log(f"categories_create created {resolved_slug}")
    return {"category": row, "created": True}


async def todos_query(status: str | None = None, limit: int = 50) -> dict[str, Any]:
    refresh_vikunja_todo_cache()
    params: dict[str, Any] = {"limit": max(1, min(limit, 200))}
    where = "WHERE provider = 'vikunja' AND external_id IS NOT NULL AND status != 'dropped'"
    if status:
        where += " AND status = :status"
        params["status"] = status
    rows = fetch_all(f"SELECT * FROM todos {where} ORDER BY created_at DESC LIMIT :limit", params)
    await safe_log(f"todos_query returned {len(rows)} todos")
    return {"todos": rows}


async def todos_projects_list() -> dict[str, Any]:
    projects = [
        {"id": str(project.get("id")), "title": str(project.get("title") or ""), "hex_color": str(project.get("hex_color") or "")}
        for project in vikunja_projects()
        if project.get("id") is not None
    ]
    await safe_log(f"todos_projects_list returned {len(projects)} projects")
    return {"projects": projects}


async def todos_labels_list() -> dict[str, Any]:
    labels = [
        {"id": str(label.get("id")), "title": str(label.get("title") or ""), "hex_color": str(label.get("hex_color") or "")}
        for label in vikunja_labels()
        if label.get("id") is not None
    ]
    await safe_log(f"todos_labels_list returned {len(labels)} labels")
    return {"labels": labels}


async def todos_create(
    title: str,
    notes: str | None = None,
    due_at: str | None = None,
    scheduled_for: str | None = None,
    tags: list[str] | None = None,
    project_id: str | None = None,
    labels: list[str] | None = None,
    priority: int | None = None,
    source: str = "agent",
) -> dict[str, Any]:
    config = vikunja_config()
    target_project_id = project_id or config.get("default_project_id")
    if not target_project_id:
        raise VikunjaMCPError("Vikunja todo creation requires VIKUNJA_DEFAULT_PROJECT_ID or VIKUNJA_PROJECT_ID.")
    payload: dict[str, Any] = {"title": title.strip().lower()}
    if notes:
        payload["description"] = notes
    if due_at:
        payload["due_date"] = due_at
    if scheduled_for:
        payload["start_date"] = scheduled_for
    if priority is not None:
        payload["priority"] = priority
    task = vikunja_request("PUT", f"/projects/{target_project_id}/tasks", body=payload)
    if not isinstance(task, dict):
        raise VikunjaMCPError("Vikunja returned an unexpected create payload")
    label_titles = labels if labels is not None else tags
    if label_titles:
        ensured_labels = [ensure_vikunja_label(str(label)) for label in label_titles]
        set_vikunja_task_labels(str(task.get("id")), [str(label.get("id")) for label in ensured_labels if label.get("id") is not None])
        task["labels"] = ensured_labels
    normalized = normalize_vikunja_task(task)
    row = upsert_vikunja_todo_cache(normalized, source=source)
    refresh_vikunja_todo_cache()
    await refresh_todos_tile()
    await safe_log(f"todos_create created Vikunja task {row['external_id']}")
    return {"todo": row}


async def todos_update(todo_id: str, **changes: Any) -> dict[str, Any]:
    row = resolve_vikunja_todo(todo_id)
    payload: dict[str, Any] = {}
    if changes.get("title") is not None:
        payload["title"] = str(changes["title"]).strip().lower()
    if "notes" in changes:
        payload["description"] = changes["notes"]
    if "due_at" in changes:
        payload["due_date"] = changes["due_at"]
    if "scheduled_for" in changes:
        payload["start_date"] = changes["scheduled_for"]
    if "priority" in changes:
        payload["priority"] = changes["priority"]
    if "project_id" in changes:
        payload["project_id"] = changes["project_id"]
    if changes.get("status") == "done":
        payload["done"] = True
    if changes.get("status") == "open":
        payload["done"] = False
        payload["done_at"] = None
    if not payload:
        raise ValueError("no supported todo changes provided")
    existing = vikunja_request("GET", f"/tasks/{row['external_id']}")
    if not isinstance(existing, dict):
        raise VikunjaMCPError("Vikunja returned an unexpected task payload")
    task = vikunja_request("POST", f"/tasks/{row['external_id']}", body={**existing, **payload})
    if not isinstance(task, dict):
        raise VikunjaMCPError("Vikunja returned an unexpected update payload")
    labels = changes.get("labels")
    if isinstance(labels, list):
        ensured_labels = [ensure_vikunja_label(str(label)) for label in labels]
        set_vikunja_task_labels(str(row["external_id"]), [str(label.get("id")) for label in ensured_labels if label.get("id") is not None])
        task["labels"] = ensured_labels
    row = upsert_vikunja_todo_cache(normalize_vikunja_task(task))
    refresh_vikunja_todo_cache()
    await refresh_todos_tile()
    await safe_log(f"todos_update updated {todo_id}")
    return {"todo": row}


async def todos_complete(todo_id: str) -> dict[str, Any]:
    row = resolve_vikunja_todo(todo_id)
    existing = vikunja_request("GET", f"/tasks/{row['external_id']}")
    if not isinstance(existing, dict):
        raise VikunjaMCPError("Vikunja returned an unexpected task payload")
    task = vikunja_request("POST", f"/tasks/{row['external_id']}", body={**existing, "done": True})
    if not isinstance(task, dict):
        raise VikunjaMCPError("Vikunja returned an unexpected update payload")
    row = upsert_vikunja_todo_cache(normalize_vikunja_task(task))
    refresh_vikunja_todo_cache()
    await refresh_todos_tile()
    await safe_log(f"todos_complete completed Vikunja task {row['external_id']}")
    return {"todo": row}


async def notes_list(category_slug: str | None = None, limit: int = 50) -> dict[str, Any]:
    try:
        rows = vault_store().list_notes(category=category_slug, limit=limit)
    except Exception as exc:
        raise vault_error(exc) from exc
    await safe_log(f"notes_list returned {len(rows)} notes")
    return {"notes": rows}


async def notes_create(
    title: str,
    body_md: str,
    category_slug: str = "inbox",
    source_job_id: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    if fetch_one("SELECT * FROM categories WHERE slug = :slug", {"slug": category_slug}) is None:
        await categories_create(category_slug, slug=category_slug)
    try:
        row = vault_store().create(title, body_md, category=category_slug, tags=tags, source_job_id=source_job_id or current_job_id())
    except Exception as exc:
        raise vault_error(exc) from exc
    await refresh_notes_tile()
    await safe_log(f"notes_create created {row['id']}")
    return {"note": row}


async def notes_append(note_id: str, body_md: str) -> dict[str, Any]:
    try:
        row = vault_store().append(note_id, body_md)
    except Exception as exc:
        raise vault_error(exc) from exc
    await safe_log(f"notes_append updated {note_id}")
    return {"note": row}


async def notes_move(note_id: str, category_slug: str) -> dict[str, Any]:
    if fetch_one("SELECT * FROM categories WHERE slug = :slug", {"slug": category_slug}) is None:
        await categories_create(category_slug, slug=category_slug)
    try:
        row = vault_store().move(note_id, category_slug)
    except Exception as exc:
        raise vault_error(exc) from exc
    await safe_log(f"notes_move moved {note_id}")
    return {"note": row}


async def notes_search(query: str, limit: int = 20) -> dict[str, Any]:
    try:
        rows = vault_store().search(query, limit=limit)
    except Exception as exc:
        raise vault_error(exc) from exc
    await safe_log(f"notes_search returned {len(rows)} notes")
    return {"notes": rows}


async def tiles_update(
    key: str,
    front: dict[str, Any],
    back: dict[str, Any] | None = None,
    size: str = "s",
    color: str = "#6A00FF",
    sort: int = 100,
) -> dict[str, Any]:
    row = one_required(
        f"""
        INSERT INTO tiles (key, size, color, sort, front, back, updated_at)
        VALUES (:key, :size, :color, :sort, {json_expr('front_json')}, {json_expr('back_json')}, CURRENT_TIMESTAMP)
        ON CONFLICT (key) DO UPDATE SET
          size = excluded.size,
          color = excluded.color,
          sort = excluded.sort,
          front = excluded.front,
          back = excluded.back,
          updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        {
            "key": key,
            "size": size,
            "color": color,
            "sort": sort,
            "front_json": dumps_json(front),
            "back_json": dumps_json(back or {}),
        },
    )
    await safe_log(f"tiles_update updated {key}")
    return {"tile": row}


async def refresh_todos_tile() -> dict[str, Any]:
    refresh_vikunja_todo_cache()
    count = int((
        fetch_one(
            """
            SELECT COUNT(*) AS count FROM todos
            WHERE provider = 'vikunja' AND external_id IS NOT NULL AND status = 'open'
            """
        ) or {"count": 0}
    )["count"])
    next_todo = fetch_one(
        """
        SELECT title FROM todos
        WHERE provider = 'vikunja' AND external_id IS NOT NULL AND status = 'open'
        ORDER BY created_at
        LIMIT 1
        """
    )
    last_done = fetch_one(
        """
        SELECT title FROM todos
        WHERE provider = 'vikunja' AND external_id IS NOT NULL AND status = 'done'
        ORDER BY completed_at DESC, updated_at DESC
        LIMIT 1
        """
    )
    return await tiles_update(
        "todos",
        {"count": count, "emoji": "✅", "line": "open", "sub": next_todo["title"] if next_todo else "nothing due"},
        {"line": "last finished", "sub": last_done["title"] if last_done else "nothing yet", "glyph": "check"},
        size="m",
        color="#1BA1E2",
        sort=20,
    )


async def refresh_notes_tile() -> dict[str, Any]:
    store = VaultStore(os.getenv("OBSIDIAN_VAULT_PATH"))
    count = store.count() if store.configured() else 0
    return await tiles_update(
        "notes",
        {"count": count, "emoji": "📝", "line": "filed", "sub": "notes stored"},
        {"line": "categories", "sub": "inbox home errands", "glyph": "note"},
        size="m",
        color="#008A00",
        sort=40,
    )


async def pages_publish(title: str, html: str, provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    job_id = current_job_id()
    cleaned = sanitize_page_html(html)
    page_id = new_id()
    command = os.getenv("HERMES_HOME_COMMAND", "").strip()
    page_provenance: dict[str, Any] = {
        "source_job_id": job_id,
        "source_command": command or None,
        "agent": "external",
        "reads": [{"type": "command", "label": "user command", "value": command}] if command else [],
        "writes": [{"type": "page", "id": page_id, "title": title.strip().lower()}],
        "skipped": [],
        "inaccessible": [],
    }
    if provenance:
        for key in ("reads", "writes", "skipped", "inaccessible"):
            if key in provenance and isinstance(provenance[key], list):
                page_provenance[key] = provenance[key]
        for key, value in provenance.items():
            if key not in page_provenance:
                page_provenance[key] = value
        if not any(isinstance(item, dict) and item.get("type") == "page" for item in page_provenance["writes"]):
            page_provenance["writes"].append({"type": "page", "id": page_id, "title": title.strip().lower()})
    row = one_required(
        f"""
        INSERT INTO pages (id, job_id, title, html, provenance, created_at)
        VALUES (:id, :job_id, :title, :html, {json_expr('provenance_json')}, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        {"id": page_id, "job_id": job_id, "title": title.strip().lower(), "html": cleaned, "provenance_json": dumps_json(page_provenance)},
    )
    if job_id:
        execute(
            "UPDATE jobs SET status = 'done', page_id = :page_id, finished_at = CURRENT_TIMESTAMP WHERE id = :job_id",
            {"page_id": row["id"], "job_id": job_id},
        )
        await log_job_event("pages_publish stored generated page", "tool", job_id)
    return {"page": row}


async def approvals_request(action: str, scope: dict[str, Any]) -> dict[str, Any]:
    job_id = current_job_id()
    row = one_required(
        f"""
        INSERT INTO approvals (id, job_id, action, scope, status)
        VALUES (:id, :job_id, :action, {json_expr('scope_json')}, 'pending')
        RETURNING *
        """,
        {"id": new_id(), "job_id": job_id, "action": action, "scope_json": dumps_json(scope)},
    )
    if job_id:
        execute("UPDATE jobs SET status = 'needs_approval' WHERE id = :job_id", {"job_id": job_id})
    await safe_log(f"approvals_request parked {action}")
    return {"approval": row, "needs_approval": True}


async def calendar_list_events(calendar_id: str = "primary", limit: int = 20) -> dict[str, Any]:
    await safe_log(f"calendar_list_events read {calendar_id}")
    rows = fetch_all(
        """
        SELECT * FROM calendar_events
        WHERE calendar_id = :calendar_id
        ORDER BY starts_at, created_at DESC
        LIMIT :limit
        """,
        {"calendar_id": calendar_id, "limit": max(1, min(limit, 100))},
    )
    return {"calendar_id": calendar_id, "events": rows, "limit": limit, "source": "local.calendar_events"}


async def calendar_create_event(summary: str, starts_at: str, ends_at: str, calendar_id: str = "primary") -> dict[str, Any]:
    return await approvals_request(
        "calendar.create_event",
        {"calendar_id": calendar_id, "summary": summary, "starts_at": starts_at, "ends_at": ends_at},
    )


async def calendar_update_event(event_id: str, changes: dict[str, Any], calendar_id: str = "primary") -> dict[str, Any]:
    return await approvals_request(
        "calendar.update_event",
        {"calendar_id": calendar_id, "event_id": event_id, "changes": changes},
    )


async def job_set_summary(emoji: str, summary: str, job_id: str | None = None) -> dict[str, Any]:
    target_job_id = job_id or current_job_id()
    if not target_job_id:
        raise VikunjaMCPError("job_set_summary requires job_id or HERMES_HOME_JOB_ID")
    clean_emoji = emoji.strip()
    if not clean_emoji or len(clean_emoji) > 8:
        raise VikunjaMCPError("emoji must be a single short emoji")
    clean_summary = " ".join(summary.strip().split())[:140]
    execute(
        "UPDATE jobs SET emoji = :emoji, summary = :summary WHERE id = :job_id",
        {"emoji": clean_emoji, "summary": clean_summary, "job_id": target_job_id},
    )
    await safe_log(f"job_set_summary updated {target_job_id}")
    return {"ok": True, "job_id": target_job_id}


async def health() -> dict[str, Any]:
    raw_url = os.getenv("VIKUNJA_URL", "").strip()
    token = ""
    configuration_error = None
    try:
        token = vikunja_token_from_env()
    except VikunjaMCPError as exc:
        configuration_error = str(exc)
    todos_status = {
        "provider": "vikunja",
        "configured": bool(raw_url and token),
        "url": normalize_vikunja_api_url(raw_url) if raw_url else None,
        "default_project_configured": bool(
            os.getenv("VIKUNJA_DEFAULT_PROJECT_ID", "").strip()
            or os.getenv("VIKUNJA_PROJECT_ID", "").strip()
        ),
        "token_file_configured": bool(os.getenv("VIKUNJA_TOKEN_FILE", "").strip()),
    }
    if configuration_error:
        todos_status["configuration_error"] = configuration_error
    return {
        "ok": True,
        "database_url": database_url(),
        "job_id": current_job_id(),
        "fastmcp": FastMCP is not None,
        "sqlalchemy": create_engine is not None,
        "todos": todos_status,
    }


TOOLS = [
    health,
    categories_list,
    categories_create,
    todos_create,
    todos_projects_list,
    todos_labels_list,
    todos_update,
    todos_complete,
    todos_query,
    notes_create,
    notes_append,
    notes_move,
    notes_search,
    notes_list,
    calendar_list_events,
    calendar_create_event,
    calendar_update_event,
    tiles_update,
    pages_publish,
    job_set_summary,
    approvals_request,
    log_job_event,
]


def build_mcp() -> Any:
    if FastMCP is None:
        return None
    server = FastMCP("hermes-home-mcp")
    for tool in TOOLS:
        server.tool()(tool)
    return server


mcp = build_mcp()


def main() -> None:
    if mcp is None:
        print("FastMCP is not installed; import this module and call tool functions directly.")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
