from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Todo, utcnow
from .vikunja import NormalizedVikunjaTask, VikunjaClient, normalize_task


def list_todos(session: Session, client: VikunjaClient | None = None) -> list[Todo]:
    refresh_vikunja_cache(session, client=client)
    return cached_vikunja_todos(session)


def create_todo(
    session: Session,
    *,
    title: str,
    notes: str | None = None,
    due_at: datetime | None = None,
    scheduled_for: datetime | None = None,
    project_id: str | None = None,
    label_titles: list[str] | None = None,
    priority: int | None = None,
    source: str = "agent",
    client: VikunjaClient | None = None,
) -> Todo:
    vikunja = client or VikunjaClient.from_env()
    task = vikunja.create_task(
        title=title.strip().lower(),
        description=notes,
        due_date=due_at,
        start_date=scheduled_for,
        project_id=project_id,
        label_titles=label_titles,
        priority=priority,
    )
    project_titles = project_title_map(vikunja)
    normalized = normalize_task(task, project_titles)
    upsert_vikunja_task(session, normalized, source=source)
    refresh_vikunja_cache(session, client=vikunja)
    row = cached_todo_by_external_id(session, normalized.external_id)
    if row is None:
        raise RuntimeError("Vikunja task was created but was not cached")
    return row


def update_todo(session: Session, todo_id: str, changes: dict[str, Any], client: VikunjaClient | None = None) -> Todo:
    vikunja = client or VikunjaClient.from_env()
    external_id = resolve_external_id(session, todo_id)
    payload: dict[str, Any] = {}
    if "title" in changes and changes["title"] is not None:
        payload["title"] = str(changes["title"]).strip().lower()
    if "notes" in changes:
        payload["description"] = changes["notes"]
    if "due_at" in changes:
        payload["due_date"] = changes["due_at"].isoformat() if isinstance(changes["due_at"], datetime) else changes["due_at"]
    if "scheduled_for" in changes:
        payload["start_date"] = changes["scheduled_for"].isoformat() if isinstance(changes["scheduled_for"], datetime) else changes["scheduled_for"]
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
    task = vikunja.update_task(external_id, payload)
    if "labels" in changes and isinstance(changes["labels"], list):
        labels = [vikunja.ensure_label(str(label)) for label in changes["labels"]]
        vikunja.set_task_labels(external_id, [str(label.get("id")) for label in labels if label.get("id") is not None])
        task["labels"] = labels
    normalized = normalize_task(task, project_title_map(vikunja))
    upsert_vikunja_task(session, normalized)
    refresh_vikunja_cache(session, client=vikunja)
    row = cached_todo_by_external_id(session, normalized.external_id)
    if row is None:
        raise RuntimeError("Vikunja task was updated but was not cached")
    return row


def complete_todo(session: Session, todo_id: str, client: VikunjaClient | None = None) -> Todo:
    vikunja = client or VikunjaClient.from_env()
    external_id = resolve_external_id(session, todo_id)
    task = vikunja.complete_task(external_id)
    normalized = normalize_task(task, project_title_map(vikunja))
    upsert_vikunja_task(session, normalized)
    refresh_vikunja_cache(session, client=vikunja)
    row = cached_todo_by_external_id(session, normalized.external_id)
    if row is None:
        raise RuntimeError("Vikunja task was completed but was not cached")
    return row


def reopen_todo(session: Session, todo_id: str, client: VikunjaClient | None = None) -> Todo:
    vikunja = client or VikunjaClient.from_env()
    external_id = resolve_external_id(session, todo_id)
    task = vikunja.reopen_task(external_id)
    normalized = normalize_task(task, project_title_map(vikunja))
    upsert_vikunja_task(session, normalized)
    refresh_vikunja_cache(session, client=vikunja)
    row = cached_todo_by_external_id(session, normalized.external_id)
    if row is None:
        raise RuntimeError("Vikunja task was reopened but was not cached")
    return row


def drop_todo(session: Session, todo_id: str, client: VikunjaClient | None = None) -> dict[str, Any]:
    vikunja = client or VikunjaClient.from_env()
    row = resolve_cached_todo(session, todo_id)
    external_id = row.external_id
    if external_id is None:
        raise ValueError("todo is missing a Vikunja external id")
    vikunja.delete_task(external_id)
    row.status = "dropped"
    row.completed_at = utcnow()
    row.updated_at = utcnow()
    refresh_vikunja_cache(session, client=vikunja)
    return {
        "ok": True,
        "tile": "todos",
        "todo_id": row.id,
        "external_id": external_id,
        "status": "dropped",
    }


def refresh_vikunja_cache(session: Session, client: VikunjaClient | None = None) -> list[Todo]:
    vikunja = client or VikunjaClient.from_env()
    tasks = vikunja.list_tasks()
    project_titles = project_title_map(vikunja)
    seen_external_ids: set[str] = set()
    for task in tasks:
        normalized = normalize_task(task, project_titles)
        seen_external_ids.add(normalized.external_id)
        upsert_vikunja_task(session, normalized)
    for row in session.scalars(
        select(Todo).where(Todo.provider == "vikunja").where(Todo.external_id.is_not(None))
    ).all():
        if row.external_id not in seen_external_ids and row.status != "dropped":
            row.status = "dropped"
            row.completed_at = row.completed_at or utcnow()
            row.updated_at = utcnow()
    session.flush()
    return cached_vikunja_todos(session)


def project_title_map(client: VikunjaClient) -> dict[str, str]:
    try:
        return {str(project.get("id")): str(project.get("title") or "") for project in client.list_projects()}
    except Exception:
        return {}


def cached_vikunja_todos(session: Session) -> list[Todo]:
    return session.scalars(
        select(Todo)
        .where(Todo.provider == "vikunja")
        .where(Todo.external_id.is_not(None))
        .where(Todo.status != "dropped")
        .order_by(Todo.created_at.desc())
    ).all()


def cached_open_todos(session: Session) -> list[Todo]:
    return session.scalars(
        select(Todo)
        .where(Todo.provider == "vikunja")
        .where(Todo.external_id.is_not(None))
        .where(Todo.status == "open")
        .order_by(Todo.created_at.asc())
    ).all()


def cached_done_todos(session: Session) -> list[Todo]:
    return session.scalars(
        select(Todo)
        .where(Todo.provider == "vikunja")
        .where(Todo.external_id.is_not(None))
        .where(Todo.status == "done")
        .order_by(Todo.completed_at.desc().nullslast(), Todo.updated_at.desc())
    ).all()


def cached_todo_by_external_id(session: Session, external_id: str) -> Todo | None:
    return session.scalar(
        select(Todo)
        .where(Todo.provider == "vikunja")
        .where(Todo.external_id == external_id)
        .limit(1)
    )


def resolve_cached_todo(session: Session, todo_id: str) -> Todo:
    row = session.get(Todo, todo_id)
    if row and row.provider == "vikunja" and row.external_id:
        return row
    external_row = cached_todo_by_external_id(session, todo_id)
    if external_row:
        return external_row
    raise ValueError("todo not found")


def resolve_external_id(session: Session, todo_id: str) -> str:
    row = resolve_cached_todo(session, todo_id)
    if not row.external_id:
        raise ValueError("todo is missing a Vikunja external id")
    return row.external_id


def upsert_vikunja_task(session: Session, task: NormalizedVikunjaTask, source: str | None = None) -> Todo:
    row = cached_todo_by_external_id(session, task.external_id)
    if row is None:
        row = Todo(
            external_id=task.external_id,
            provider=task.provider,
            source=source if source in {"user", "agent", "channel"} else "user",
        )
        session.add(row)
    row.title = task.title
    row.notes = task.notes
    row.due_at = task.due_at
    row.scheduled_for = task.scheduled_for
    row.tags = task.tags
    row.priority = task.priority
    row.status = task.status
    row.project_id = task.project_id
    row.project_title = task.project_title
    if task.created_at:
        row.created_at = task.created_at
    row.updated_at = task.updated_at or utcnow()
    row.completed_at = task.completed_at if task.status == "done" else None
    if source in {"user", "agent", "channel"}:
        row.source = source
    session.flush()
    return row
