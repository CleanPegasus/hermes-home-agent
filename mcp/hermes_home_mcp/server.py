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
JSON_COLUMNS = {"front", "back", "scope", "tags", "embedding", "payload", "result", "provenance", "choices", "draft", "entry_metadata"}
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
      provider TEXT NOT NULL DEFAULT 'todoist',
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
      parent_job_id TEXT,
      started_at TEXT,
      finished_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS clarifications (
      id TEXT PRIMARY KEY,
      job_id TEXT NOT NULL,
      question TEXT NOT NULL,
      choices TEXT NOT NULL DEFAULT '[]',
      draft TEXT NOT NULL DEFAULT '{}',
      answer TEXT,
      status TEXT NOT NULL DEFAULT 'pending',
      follow_up_job_id TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      answered_at TEXT
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
    """
    CREATE TABLE IF NOT EXISTS index_entries (
      id TEXT PRIMARY KEY,
      source_type TEXT NOT NULL,
      source_id TEXT NOT NULL,
      title TEXT NOT NULL DEFAULT '',
      content TEXT NOT NULL DEFAULT '',
      content_hash TEXT,
      embedding TEXT,
      entry_metadata TEXT NOT NULL DEFAULT '{}',
      indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS saved_items (
      id TEXT PRIMARY KEY,
      url TEXT,
      title TEXT NOT NULL DEFAULT 'saved item',
      text TEXT,
      summary TEXT,
      tags TEXT NOT NULL DEFAULT '[]',
      source TEXT NOT NULL DEFAULT 'shortcut',
      status TEXT NOT NULL DEFAULT 'new',
      score REAL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      enriched_at TEXT,
      surfaced_at TEXT
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


class TodoistMCPError(RuntimeError):
    pass


TODOIST_REST_BASE = "https://api.todoist.com/rest/v2"
TODOIST_SYNC_BASE = "https://api.todoist.com/sync/v9"


def vault_store() -> VaultStore:
    store = VaultStore(os.getenv("OBSIDIAN_VAULT_PATH"))
    if not store.configured():
        raise TodoistMCPError("OBSIDIAN_VAULT_PATH is not configured. Set it to your Obsidian vault folder to use notes.")
    return store


def vault_error(exc: Exception) -> TodoistMCPError:
    if isinstance(exc, VaultConfigurationError):
        return TodoistMCPError("OBSIDIAN_VAULT_PATH is not configured. Set it to your Obsidian vault folder to use notes.")
    if isinstance(exc, VaultNoteNotFoundError):
        return TodoistMCPError("note not found")
    return TodoistMCPError(str(exc))


def todoist_config() -> dict[str, Any]:
    token = todoist_token_from_env()
    if not token:
        raise TodoistMCPError(
            "Todoist todo integration is not configured. Set TODOIST_TOKEN or TODOIST_TOKEN_FILE to use todos."
        )
    default_project_id = os.getenv("TODOIST_DEFAULT_PROJECT_ID", "").strip() or None
    return {
        "token": token,
        "default_project_id": default_project_id,
        "timeout": float(os.getenv("TODOIST_TIMEOUT_SECONDS", "10")),
    }


def todoist_token_from_env() -> str:
    token = os.getenv("TODOIST_TOKEN", "").strip()
    if token:
        return token
    token_file = os.getenv("TODOIST_TOKEN_FILE", "").strip()
    if not token_file:
        return ""
    path = Path(token_file).expanduser()
    try:
        file_token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise TodoistMCPError(f"Could not read TODOIST_TOKEN_FILE {path}: {exc.strerror}") from exc
    if not file_token:
        raise TodoistMCPError(f"TODOIST_TOKEN_FILE {path} is empty")
    return file_token


def todoist_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    base: str | None = None,
) -> Any:
    config = todoist_config()
    headers = {"accept": "application/json", "authorization": f"Bearer {config['token']}"}
    if body is not None:
        headers["content-type"] = "application/json"
    try:
        with httpx.Client(timeout=config["timeout"]) as client:
            response = client.request(
                method,
                f"{base or TODOIST_REST_BASE}{path}",
                headers=headers,
                json=body,
                params=params,
            )
    except httpx.TimeoutException as exc:
        raise TodoistMCPError(f"Todoist request timed out: {method} {path}") from exc
    except httpx.RequestError as exc:
        raise TodoistMCPError(f"Todoist request failed: {exc}") from exc
    if response.status_code >= 400:
        raise TodoistMCPError(f"Todoist request failed ({response.status_code}): {todoist_error_text(response)}")
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise TodoistMCPError("Todoist returned invalid JSON") from exc


def todoist_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:500] or response.reason_phrase
    if isinstance(payload, dict):
        for key in ("error", "message", "detail"):
            if payload.get(key):
                return str(payload[key])
    return str(payload)[:500]


def clamp_priority(value: Any) -> int:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(4, priority))


def normalize_todoist_task(task: dict[str, Any]) -> dict[str, Any]:
    external_id = str(task.get("id") or "").strip()
    if not external_id:
        raise TodoistMCPError("Todoist task is missing an id")
    project_id = optional_text(task.get("project_id"))
    labels = task.get("labels")
    if not isinstance(labels, list):
        labels = []
    due = task.get("due")
    due_at = None
    if isinstance(due, dict):
        due_at = clean_todoist_datetime(due.get("datetime") or due.get("date"))
    created_at = clean_todoist_datetime(task.get("created_at"))
    return {
        "external_id": external_id,
        "provider": "todoist",
        "title": str(task.get("content") or "untitled task").strip() or "untitled task",
        "notes": optional_text(task.get("description")),
        "due_at": due_at,
        "scheduled_for": None,
        "tags": [str(label).strip() for label in labels if str(label).strip()],
        "priority": optional_int(task.get("priority")),
        "status": "done" if bool(task.get("is_completed")) else "open",
        "project_id": project_id,
        "project_title": f"project {project_id}" if project_id else None,
        "created_at": created_at,
        "updated_at": created_at,
        "completed_at": None,
    }


def normalize_todoist_completed_task(item: dict[str, Any]) -> dict[str, Any]:
    external_id = str(item.get("task_id") or item.get("id") or "").strip()
    if not external_id:
        raise TodoistMCPError("Todoist completed item is missing a task id")
    project_id = optional_text(item.get("project_id"))
    completed_at = clean_todoist_datetime(item.get("completed_at"))
    return {
        "external_id": external_id,
        "provider": "todoist",
        "title": str(item.get("content") or "untitled task").strip() or "untitled task",
        "notes": None,
        "due_at": None,
        "scheduled_for": None,
        "tags": [],
        "priority": None,
        "status": "done",
        "project_id": project_id,
        "project_title": f"project {project_id}" if project_id else None,
        "created_at": None,
        "updated_at": completed_at,
        "completed_at": completed_at,
    }


def clean_todoist_datetime(value: Any) -> str | None:
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


def todoist_projects() -> list[dict[str, Any]]:
    payload = todoist_request("GET", "/projects")
    if not isinstance(payload, list):
        raise TodoistMCPError("Todoist returned an unexpected projects payload")
    return [project for project in payload if isinstance(project, dict)]


def todoist_labels() -> list[dict[str, Any]]:
    payload = todoist_request("GET", "/labels")
    if not isinstance(payload, list):
        raise TodoistMCPError("Todoist returned an unexpected labels payload")
    return [label for label in payload if isinstance(label, dict)]


def ensure_todoist_label(name: str) -> dict[str, Any]:
    normalized = name.strip()
    if not normalized:
        raise TodoistMCPError("label name is required")
    for label in todoist_labels():
        if str(label.get("name", "")).strip().lower() == normalized.lower():
            return label
    payload = todoist_request("POST", "/labels", body={"name": normalized})
    if not isinstance(payload, dict):
        raise TodoistMCPError("Todoist returned an unexpected label payload")
    return payload


def set_todoist_task_labels(task_id: str, label_names: list[str]) -> dict[str, Any]:
    # Todoist v2 stores labels as plain names directly on the task.
    return todoist_request("POST", f"/tasks/{task_id}", body={"labels": label_names})


def refresh_todoist_todo_cache() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    active = todoist_request("GET", "/tasks")
    if not isinstance(active, list):
        raise TodoistMCPError("Todoist returned an unexpected tasks payload")
    for item in active:
        if isinstance(item, dict):
            row = upsert_todoist_todo_cache(normalize_todoist_task(item))
            rows.append(row)
            seen.add(str(row["external_id"]))
    completed = todoist_request(
        "GET",
        "/completed/get_all",
        params={"limit": 200},
        base=TODOIST_SYNC_BASE,
    )
    items = completed.get("items") if isinstance(completed, dict) else None
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                row = upsert_todoist_todo_cache(normalize_todoist_completed_task(item))
                rows.append(row)
                seen.add(str(row["external_id"]))
    for row in fetch_all("SELECT * FROM todos WHERE provider = 'todoist' AND external_id IS NOT NULL"):
        if row["external_id"] not in seen and row["status"] == "open":
            execute(
                "UPDATE todos SET status = 'dropped', completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
                {"id": row["id"]},
            )
    return rows


def upsert_todoist_todo_cache(task: dict[str, Any], source: str | None = None) -> dict[str, Any]:
    existing = fetch_one(
        "SELECT * FROM todos WHERE provider = 'todoist' AND external_id = :external_id",
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
          :id, :external_id, 'todoist', :title, :notes, :due_at, :scheduled_for, :tags_value,
          :priority, :status, :source, :project_id, :project_title,
          COALESCE(:created_at, CURRENT_TIMESTAMP), COALESCE(:updated_at, CURRENT_TIMESTAMP), :completed_at
        )
        RETURNING *
        """,
        params,
    )


def resolve_todoist_todo(todo_id: str) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT * FROM todos
        WHERE provider = 'todoist'
          AND external_id IS NOT NULL
          AND (id = :todo_id OR external_id = :todo_id)
        """,
        {"todo_id": todo_id},
    )
    if row is None:
        raise TodoistMCPError("todo not found")
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
    ensure_sqlite_column(connection, "jobs", "parent_job_id", "TEXT")
    ensure_sqlite_column(connection, "clarifications", "follow_up_job_id", "TEXT")
    ensure_sqlite_column(connection, "clarifications", "answered_at", "TEXT")
    ensure_sqlite_column(connection, "action_runs", "source_job_id", "TEXT")
    ensure_sqlite_column(connection, "action_runs", "source_page_id", "TEXT")
    ensure_sqlite_column(connection, "codex_runs", "effort", "TEXT NOT NULL DEFAULT 'xhigh'")
    ensure_sqlite_column(connection, "todos", "external_id", "TEXT")
    ensure_sqlite_column(connection, "todos", "provider", "TEXT NOT NULL DEFAULT 'todoist'")
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
    refresh_todoist_todo_cache()
    params: dict[str, Any] = {"limit": max(1, min(limit, 200))}
    where = "WHERE provider = 'todoist' AND external_id IS NOT NULL AND status != 'dropped'"
    if status:
        where += " AND status = :status"
        params["status"] = status
    rows = fetch_all(f"SELECT * FROM todos {where} ORDER BY created_at DESC LIMIT :limit", params)
    await safe_log(f"todos_query returned {len(rows)} todos")
    return {"todos": rows}


async def todos_projects_list() -> dict[str, Any]:
    projects = [
        {"id": str(project.get("id")), "title": str(project.get("name") or ""), "hex_color": str(project.get("color") or "")}
        for project in todoist_projects()
        if project.get("id") is not None
    ]
    await safe_log(f"todos_projects_list returned {len(projects)} projects")
    return {"projects": projects}


async def todos_labels_list() -> dict[str, Any]:
    labels = [
        {"id": str(label.get("id")), "title": str(label.get("name") or ""), "hex_color": str(label.get("color") or "")}
        for label in todoist_labels()
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
    config = todoist_config()
    target_project_id = project_id or config.get("default_project_id")
    payload: dict[str, Any] = {"content": title.strip().lower()}
    if target_project_id:
        payload["project_id"] = target_project_id
    if notes:
        payload["description"] = notes
    if due_at:
        payload["due_datetime"] = due_at
    if priority is not None:
        payload["priority"] = clamp_priority(priority)
    label_titles = labels if labels is not None else tags
    if label_titles:
        ensured = [ensure_todoist_label(str(label)) for label in label_titles]
        payload["labels"] = [str(label.get("name")) for label in ensured if label.get("name")]
    task = todoist_request("POST", "/tasks", body=payload)
    if not isinstance(task, dict):
        raise TodoistMCPError("Todoist returned an unexpected create payload")
    normalized = normalize_todoist_task(task)
    row = upsert_todoist_todo_cache(normalized, source=source)
    refresh_todoist_todo_cache()
    await refresh_todos_tile()
    await safe_log(f"todos_create created Todoist task {row['external_id']}")
    return {"todo": row}


async def todos_update(todo_id: str, **changes: Any) -> dict[str, Any]:
    row = resolve_todoist_todo(todo_id)
    payload: dict[str, Any] = {}
    if changes.get("title") is not None:
        payload["content"] = str(changes["title"]).strip().lower()
    if "notes" in changes:
        payload["description"] = changes["notes"]
    if "due_at" in changes:
        if changes["due_at"]:
            payload["due_datetime"] = changes["due_at"]
        else:
            payload["due_string"] = "no date"
    if "priority" in changes and changes["priority"] is not None:
        payload["priority"] = clamp_priority(changes["priority"])
    labels = changes.get("labels")
    if isinstance(labels, list):
        ensured = [ensure_todoist_label(str(label)) for label in labels]
        payload["labels"] = [str(label.get("name")) for label in ensured if label.get("name")]
    status_change = changes.get("status")
    if not payload and status_change not in {"done", "open"}:
        raise ValueError("no supported todo changes provided")
    if payload:
        task = todoist_request("POST", f"/tasks/{row['external_id']}", body=payload)
        if task is not None and not isinstance(task, dict):
            raise TodoistMCPError("Todoist returned an unexpected update payload")
    if status_change == "done":
        todoist_request("POST", f"/tasks/{row['external_id']}/close")
        execute(
            "UPDATE todos SET status = 'done', completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
            {"id": row["id"]},
        )
    elif status_change == "open":
        todoist_request("POST", f"/tasks/{row['external_id']}/reopen")
        execute(
            "UPDATE todos SET status = 'open', completed_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
            {"id": row["id"]},
        )
    refresh_todoist_todo_cache()
    await refresh_todos_tile()
    await safe_log(f"todos_update updated {todo_id}")
    updated = fetch_one("SELECT * FROM todos WHERE id = :id", {"id": row["id"]}) or row
    return {"todo": updated}


async def todos_complete(todo_id: str) -> dict[str, Any]:
    row = resolve_todoist_todo(todo_id)
    todoist_request("POST", f"/tasks/{row['external_id']}/close")
    execute(
        "UPDATE todos SET status = 'done', completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
        {"id": row["id"]},
    )
    refresh_todoist_todo_cache()
    await refresh_todos_tile()
    await safe_log(f"todos_complete completed Todoist task {row['external_id']}")
    updated = fetch_one("SELECT * FROM todos WHERE id = :id", {"id": row["id"]}) or row
    return {"todo": updated}


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
    refresh_todoist_todo_cache()
    count = int((
        fetch_one(
            """
            SELECT COUNT(*) AS count FROM todos
            WHERE provider = 'todoist' AND external_id IS NOT NULL AND status = 'open'
            """
        ) or {"count": 0}
    )["count"])
    next_todo = fetch_one(
        """
        SELECT title FROM todos
        WHERE provider = 'todoist' AND external_id IS NOT NULL AND status = 'open'
        ORDER BY created_at
        LIMIT 1
        """
    )
    last_done = fetch_one(
        """
        SELECT title FROM todos
        WHERE provider = 'todoist' AND external_id IS NOT NULL AND status = 'done'
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


async def clarifications_request(
    question: str,
    choices: list[str] | None = None,
    draft: dict[str, Any] | None = None,
    source_job_id: str | None = None,
) -> dict[str, Any]:
    job_id = source_job_id or current_job_id()
    if not job_id:
        raise TodoistMCPError("clarifications_request requires source_job_id or HERMES_HOME_JOB_ID")
    clean_question = " ".join(question.strip().split())
    if not clean_question:
        raise TodoistMCPError("clarification question must not be blank")
    clean_choices: list[str] = []
    for choice in choices or []:
        value = " ".join(str(choice).strip().split())
        if value and value not in clean_choices:
            clean_choices.append(value[:120])
    row = one_required(
        f"""
        INSERT INTO clarifications (
          id, job_id, question, choices, draft, status, created_at
        )
        VALUES (
          :id, :job_id, :question, {json_expr('choices_json')}, {json_expr('draft_json')}, 'pending', CURRENT_TIMESTAMP
        )
        RETURNING *
        """,
        {
            "id": new_id(),
            "job_id": job_id,
            "question": clean_question,
            "choices_json": dumps_json(clean_choices),
            "draft_json": dumps_json(draft or {}),
        },
    )
    execute("UPDATE jobs SET status = 'needs_clarification' WHERE id = :job_id", {"job_id": job_id})
    await log_job_event(f"clarifications_request asked: {clean_question}", "tool", job_id)
    return {"clarification": row, "needs_clarification": True}


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
        raise TodoistMCPError("job_set_summary requires job_id or HERMES_HOME_JOB_ID")
    clean_emoji = emoji.strip()
    if not clean_emoji or len(clean_emoji) > 8:
        raise TodoistMCPError("emoji must be a single short emoji")
    clean_summary = " ".join(summary.strip().split())[:140]
    execute(
        """
        UPDATE jobs
        SET
          emoji = :emoji,
          summary = :summary,
          status = CASE WHEN status IN ('queued', 'running') THEN 'done' ELSE status END,
          finished_at = CASE WHEN status IN ('queued', 'running') THEN CURRENT_TIMESTAMP ELSE finished_at END
        WHERE id = :job_id
        """,
        {"emoji": clean_emoji, "summary": clean_summary, "job_id": target_job_id},
    )
    await safe_log(f"job_set_summary updated {target_job_id}")
    return {"ok": True, "job_id": target_job_id}


async def health() -> dict[str, Any]:
    token = ""
    configuration_error = None
    try:
        token = todoist_token_from_env()
    except TodoistMCPError as exc:
        configuration_error = str(exc)
    todos_status = {
        "provider": "todoist",
        "configured": bool(token),
        "url": TODOIST_REST_BASE,
        "default_project_configured": bool(os.getenv("TODOIST_DEFAULT_PROJECT_ID", "").strip()),
        "token_file_configured": bool(os.getenv("TODOIST_TOKEN_FILE", "").strip()),
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


def home_api_base() -> str:
    return os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/") or "http://127.0.0.1:8000"


def home_api_request(method: str, path: str, body: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> Any:
    token = os.getenv("HOME_API_TOKEN", "dev-token")
    headers = {"accept": "application/json", "authorization": f"Bearer {token}"}
    if body is not None:
        headers["content-type"] = "application/json"
    try:
        with httpx.Client(timeout=float(os.getenv("HOME_API_TIMEOUT_SECONDS", "20"))) as client:
            response = client.request(method, f"{home_api_base()}{path}", headers=headers, json=body, params=params)
    except httpx.RequestError as exc:
        raise TodoistMCPError(f"home API request failed: {exc}") from exc
    if response.status_code >= 400:
        raise TodoistMCPError(f"home API request failed ({response.status_code}): {response.text[:300]}")
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


async def jobs_handoff(profile_slug: str, command: str) -> dict[str, Any]:
    """Route the current command to another agent profile (research-agent, coding-agent, etc.).

    Spawns a fresh job under the chosen profile and returns its job_id. Use this from the
    router when a command needs real downstream work rather than a todo or note.
    """
    payload = home_api_request(
        "POST",
        "/api/jobs/handoff",
        body={"profile_slug": profile_slug, "command": command, "source_job_id": current_job_id()},
    )
    await safe_log(f"jobs_handoff routed to {profile_slug}")
    return payload or {}


async def memory_search(query: str, source_types: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Semantic search across indexed notes, past jobs/conversations, todos, and saved items.

    source_types is an optional comma-separated filter (e.g. "note,job"). Returns ranked results.
    """
    params: dict[str, Any] = {"q": query, "limit": limit}
    if source_types:
        params["types"] = source_types
    payload = home_api_request("GET", "/api/search", params=params)
    return payload or {"results": []}


TOOLS = [
    health,
    jobs_handoff,
    memory_search,
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
    clarifications_request,
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
