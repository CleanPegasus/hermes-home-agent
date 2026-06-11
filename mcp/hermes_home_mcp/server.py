from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

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


DEFAULT_DATABASE_URL = "sqlite:///./hermes-home.db"
JSON_COLUMNS = {"front", "back", "scope", "tags", "embedding"}
_ENGINE: Engine | None = None
_ENGINE_URL: str | None = None


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
      title TEXT NOT NULL,
      notes TEXT,
      due_at TEXT,
      scheduled_for TEXT,
      tags TEXT NOT NULL DEFAULT '[]',
      status TEXT NOT NULL DEFAULT 'open',
      source TEXT NOT NULL DEFAULT 'user',
      things_id TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
      started_at TEXT,
      finished_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pages (
      id TEXT PRIMARY KEY,
      job_id TEXT,
      title TEXT NOT NULL,
      html TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
      expires_at TEXT
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
    ("work", "work", "#0050EF"),
    ("ideas", "ideas", "#6A00FF"),
    ("home", "home", "#1BA1E2"),
    ("personal", "personal", "#008A00"),
    ("health", "health", "#A4C400"),
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
    return value or None


def new_id() -> str:
    return str(uuid4())


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


def ensure_sqlite_schema(connection: Any) -> None:
    for statement in SQLITE_SCHEMA:
        if hasattr(connection, "exec_driver_sql"):
            connection.exec_driver_sql(statement)
        else:
            connection.execute(statement)
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
    cleaned = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"\s+on[a-z]+\s*=\s*(['\"]).*?\1", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"\s+(src|href)\s*=\s*(['\"])\s*(?!https://).*?\2", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"@import\s+[^;]+;", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"url\(\s*(['\"])?\s*(?!https://).*?\)", "none", cleaned, flags=re.IGNORECASE)
    return cleaned


async def log_job_event(text_value: str, kind: str = "tool", job_id: str | None = None) -> dict[str, Any]:
    target_job_id = job_id or current_job_id()
    if target_job_id is None:
        return {"logged": False, "reason": "HERMES_HOME_JOB_ID is not set"}
    row = one_required(
        """
        INSERT INTO job_events (id, job_id, kind, text)
        VALUES (:id, :job_id, :kind, :text)
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
        INSERT INTO categories (id, slug, name, color, created_by)
        VALUES (:id, :slug, :name, :color, 'agent')
        RETURNING *
        """,
        {"id": new_id(), "slug": resolved_slug, "name": name.strip().lower(), "color": color},
    )
    await safe_log(f"categories_create created {resolved_slug}")
    return {"category": row, "created": True}


async def todos_query(status: str | None = None, limit: int = 50) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": max(1, min(limit, 200))}
    where = ""
    if status:
        where = "WHERE status = :status"
        params["status"] = status
    rows = fetch_all(f"SELECT * FROM todos {where} ORDER BY created_at DESC LIMIT :limit", params)
    await safe_log(f"todos_query returned {len(rows)} todos")
    return {"todos": rows}


async def todos_create(
    title: str,
    notes: str | None = None,
    due_at: str | None = None,
    scheduled_for: str | None = None,
    tags: list[str] | None = None,
    source: str = "agent",
) -> dict[str, Any]:
    row = one_required(
        f"""
        INSERT INTO todos (id, title, notes, due_at, scheduled_for, tags, source)
        VALUES (:id, :title, :notes, :due_at, :scheduled_for, {json_expr('tags_json')}, :source)
        RETURNING *
        """,
        {
            "id": new_id(),
            "title": title.strip().lower(),
            "notes": notes,
            "due_at": due_at,
            "scheduled_for": scheduled_for,
            "tags_json": dumps_json(tags or []),
            "source": source,
        },
    )
    await refresh_todos_tile()
    await safe_log(f"todos_create created {row['id']}")
    return {"todo": row}


async def todos_update(todo_id: str, **changes: Any) -> dict[str, Any]:
    allowed = {"title", "notes", "due_at", "scheduled_for", "status", "things_id"}
    assignments = []
    params: dict[str, Any] = {"todo_id": todo_id}
    for key, value in changes.items():
        if key in allowed and value is not None:
            assignments.append(f"{key} = :{key}")
            params[key] = value
    if not assignments:
        raise ValueError("no supported todo changes provided")
    row = one_required(
        f"UPDATE todos SET {', '.join(assignments)} WHERE id = :todo_id RETURNING *",
        params,
    )
    await refresh_todos_tile()
    await safe_log(f"todos_update updated {todo_id}")
    return {"todo": row}


async def todos_complete(todo_id: str) -> dict[str, Any]:
    row = one_required(
        """
        UPDATE todos
        SET status = 'done', completed_at = CURRENT_TIMESTAMP
        WHERE id = :todo_id
        RETURNING *
        """,
        {"todo_id": todo_id},
    )
    await refresh_todos_tile()
    await safe_log(f"todos_complete completed {todo_id}")
    return {"todo": row}


async def notes_list(category_slug: str | None = None, limit: int = 50) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": max(1, min(limit, 200))}
    join = "LEFT JOIN categories c ON c.id = n.category_id"
    where = "WHERE n.archived = 0" if is_sqlite_url() else "WHERE n.archived = false"
    if category_slug:
        where += " AND c.slug = :category_slug"
        params["category_slug"] = category_slug
    rows = fetch_all(
        f"""
        SELECT n.*, c.slug AS category_slug, c.color AS category_color
        FROM notes n {join}
        {where}
        ORDER BY n.updated_at DESC
        LIMIT :limit
        """,
        params,
    )
    await safe_log(f"notes_list returned {len(rows)} notes")
    return {"notes": rows}


async def notes_create(title: str, body_md: str, category_slug: str = "ideas") -> dict[str, Any]:
    category = fetch_one("SELECT * FROM categories WHERE slug = :slug", {"slug": category_slug})
    if category is None:
        category = (await categories_create(category_slug, slug=category_slug))["category"]
    row = one_required(
        """
        INSERT INTO notes (id, category_id, title, body_md, source_job_id)
        VALUES (:id, :category_id, :title, :body_md, :source_job_id)
        RETURNING *
        """,
        {
            "id": new_id(),
            "category_id": category["id"],
            "title": title.strip().lower(),
            "body_md": body_md.strip(),
            "source_job_id": current_job_id(),
        },
    )
    await refresh_notes_tile()
    await safe_log(f"notes_create created {row['id']}")
    return {"note": row}


async def notes_append(note_id: str, body_md: str) -> dict[str, Any]:
    row = one_required(
        """
        UPDATE notes
        SET body_md = body_md || :body_md, updated_at = CURRENT_TIMESTAMP
        WHERE id = :note_id
        RETURNING *
        """,
        {"note_id": note_id, "body_md": "\n\n" + body_md.strip()},
    )
    await safe_log(f"notes_append updated {note_id}")
    return {"note": row}


async def notes_move(note_id: str, category_slug: str) -> dict[str, Any]:
    category = fetch_one("SELECT * FROM categories WHERE slug = :slug", {"slug": category_slug})
    if category is None:
        category = (await categories_create(category_slug, slug=category_slug))["category"]
    row = one_required(
        """
        UPDATE notes
        SET category_id = :category_id, updated_at = CURRENT_TIMESTAMP
        WHERE id = :note_id
        RETURNING *
        """,
        {"note_id": note_id, "category_id": category["id"]},
    )
    await safe_log(f"notes_move moved {note_id}")
    return {"note": row}


async def notes_search(query: str, limit: int = 20) -> dict[str, Any]:
    needle = f"%{query.strip().lower()}%"
    rows = fetch_all(
        """
        SELECT * FROM notes
        WHERE archived = 0 AND (lower(title) LIKE :needle OR lower(body_md) LIKE :needle)
        ORDER BY updated_at DESC
        LIMIT :limit
        """,
        {"needle": needle, "limit": max(1, min(limit, 100))},
    )
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
    count = int((fetch_one("SELECT COUNT(*) AS count FROM todos WHERE status = 'open'") or {"count": 0})["count"])
    next_todo = fetch_one("SELECT title FROM todos WHERE status = 'open' ORDER BY created_at LIMIT 1")
    return await tiles_update(
        "todos",
        {"count": count, "line": "open", "sub": next_todo["title"] if next_todo else "nothing due"},
        {"line": "last finished", "sub": "updated by hermes", "glyph": "check"},
        size="m",
        color="#1BA1E2",
        sort=20,
    )


async def refresh_notes_tile() -> dict[str, Any]:
    count = int((fetch_one("SELECT COUNT(*) AS count FROM notes WHERE archived = 0") or {"count": 0})["count"])
    return await tiles_update(
        "notes",
        {"count": count, "line": "filed", "sub": "notes stored"},
        {"line": "categories", "sub": "work ideas home", "glyph": "note"},
        size="m",
        color="#008A00",
        sort=40,
    )


async def pages_publish(title: str, html: str) -> dict[str, Any]:
    job_id = current_job_id()
    cleaned = sanitize_page_html(html)
    row = one_required(
        """
        INSERT INTO pages (id, job_id, title, html)
        VALUES (:id, :job_id, :title, :html)
        RETURNING *
        """,
        {"id": new_id(), "job_id": job_id, "title": title.strip().lower(), "html": cleaned},
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
    return {"calendar_id": calendar_id, "events": [], "limit": limit, "source": "not configured"}


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


async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "database_url": database_url(),
        "job_id": current_job_id(),
        "fastmcp": FastMCP is not None,
        "sqlalchemy": create_engine is not None,
    }


TOOLS = [
    health,
    categories_list,
    categories_create,
    todos_create,
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
