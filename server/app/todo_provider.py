from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Todo, utcnow
from .todoist import (
    NormalizedTodoistTask,
    TodoistClient,
    normalize_completed_task,
    normalize_task,
)

PROVIDER = "todoist"


def list_todos(session: Session, client: TodoistClient | None = None) -> list[Todo]:
    refresh_todoist_cache(session, client=client)
    return cached_todos(session)


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
    client: TodoistClient | None = None,
) -> Todo:
    todoist = client or TodoistClient.from_env()
    task = todoist.create_task(
        title=title.strip().lower(),
        description=notes,
        due_date=due_at,
        start_date=scheduled_for,
        project_id=project_id,
        label_titles=label_titles,
        priority=priority,
    )
    normalized = normalize_task(task, project_title_map(todoist))
    upsert_todoist_task(session, normalized, source=source)
    row = cached_todo_by_external_id(session, normalized.external_id)
    if row is None:
        raise RuntimeError("Todoist task was created but was not cached")
    return row


def update_todo(session: Session, todo_id: str, changes: dict[str, Any], client: TodoistClient | None = None) -> Todo:
    todoist = client or TodoistClient.from_env()
    external_id = resolve_external_id(session, todo_id)
    if changes.get("status") == "done":
        return complete_todo(session, todo_id, client=todoist)
    if changes.get("status") == "open":
        return reopen_todo(session, todo_id, client=todoist)
    payload: dict[str, Any] = {}
    if "title" in changes and changes["title"] is not None:
        payload["content"] = str(changes["title"]).strip().lower()
    if "notes" in changes:
        payload["description"] = changes["notes"]
    if "due_at" in changes:
        value = changes["due_at"]
        if isinstance(value, datetime):
            payload["due_datetime"] = value.isoformat()
        elif value:
            payload["due_string"] = str(value)
        else:
            payload["due_string"] = "no date"
    if "priority" in changes and changes["priority"] is not None:
        payload["priority"] = int(changes["priority"])
    if "labels" in changes and isinstance(changes["labels"], list):
        payload["labels"] = [str(label).strip() for label in changes["labels"] if str(label).strip()]
    if "project_id" in changes and changes["project_id"]:
        payload["project_id"] = str(changes["project_id"])
    if not payload:
        raise ValueError("no supported todo changes provided")
    task = todoist.update_task(external_id, payload)
    normalized = normalize_task(task, project_title_map(todoist))
    upsert_todoist_task(session, normalized)
    row = cached_todo_by_external_id(session, normalized.external_id)
    if row is None:
        raise RuntimeError("Todoist task was updated but was not cached")
    return row


def complete_todo(session: Session, todo_id: str, client: TodoistClient | None = None) -> Todo:
    todoist = client or TodoistClient.from_env()
    row = resolve_cached_todo(session, todo_id)
    if not row.external_id:
        raise ValueError("todo is missing a Todoist external id")
    todoist.complete_task(row.external_id)
    row.status = "done"
    row.completed_at = utcnow()
    row.updated_at = utcnow()
    session.flush()
    return row


def reopen_todo(session: Session, todo_id: str, client: TodoistClient | None = None) -> Todo:
    todoist = client or TodoistClient.from_env()
    row = resolve_cached_todo(session, todo_id)
    if not row.external_id:
        raise ValueError("todo is missing a Todoist external id")
    todoist.reopen_task(row.external_id)
    row.status = "open"
    row.completed_at = None
    row.updated_at = utcnow()
    session.flush()
    return row


def drop_todo(session: Session, todo_id: str, client: TodoistClient | None = None) -> dict[str, Any]:
    todoist = client or TodoistClient.from_env()
    row = resolve_cached_todo(session, todo_id)
    external_id = row.external_id
    if external_id is None:
        raise ValueError("todo is missing a Todoist external id")
    todoist.delete_task(external_id)
    row.status = "dropped"
    row.completed_at = utcnow()
    row.updated_at = utcnow()
    session.flush()
    return {
        "ok": True,
        "tile": "todos",
        "todo_id": row.id,
        "external_id": external_id,
        "status": "dropped",
    }


def refresh_todoist_cache(session: Session, client: TodoistClient | None = None) -> list[Todo]:
    todoist = client or TodoistClient.from_env()
    project_titles = project_title_map(todoist)
    active = todoist.list_tasks()
    seen_active: set[str] = set()
    for task in active:
        normalized = normalize_task(task, project_titles)
        seen_active.add(normalized.external_id)
        upsert_todoist_task(session, normalized)

    seen_done: set[str] = set()
    try:
        completed = todoist.list_completed_tasks()
    except Exception:
        completed = []
    for item in completed:
        normalized = normalize_completed_task(item, project_titles)
        if normalized.external_id in seen_active:
            continue
        seen_done.add(normalized.external_id)
        upsert_todoist_task(session, normalized)

    # An open cached task that is no longer active and not in the completed feed
    # has been deleted in Todoist; mark it dropped.
    for row in session.scalars(
        select(Todo)
        .where(Todo.provider == PROVIDER)
        .where(Todo.external_id.is_not(None))
        .where(Todo.status == "open")
    ).all():
        if row.external_id not in seen_active and row.external_id not in seen_done:
            row.status = "dropped"
            row.completed_at = row.completed_at or utcnow()
            row.updated_at = utcnow()
    session.flush()
    return cached_todos(session)


def project_title_map(client: TodoistClient) -> dict[str, str]:
    try:
        return {str(project.get("id")): str(project.get("name") or "") for project in client.list_projects()}
    except Exception:
        return {}


def cached_todos(session: Session) -> list[Todo]:
    return list(
        session.scalars(
            select(Todo)
            .where(Todo.provider == PROVIDER)
            .where(Todo.external_id.is_not(None))
            .where(Todo.status != "dropped")
            .order_by(Todo.created_at.desc())
        ).all()
    )


def cached_open_todos(session: Session) -> list[Todo]:
    return list(
        session.scalars(
            select(Todo)
            .where(Todo.provider == PROVIDER)
            .where(Todo.external_id.is_not(None))
            .where(Todo.status == "open")
            .order_by(Todo.created_at.asc())
        ).all()
    )


def cached_done_todos(session: Session) -> list[Todo]:
    return list(
        session.scalars(
            select(Todo)
            .where(Todo.provider == PROVIDER)
            .where(Todo.external_id.is_not(None))
            .where(Todo.status == "done")
            .order_by(Todo.completed_at.desc().nullslast(), Todo.updated_at.desc())
        ).all()
    )


def cached_todo_by_external_id(session: Session, external_id: str) -> Todo | None:
    return session.scalar(
        select(Todo)
        .where(Todo.provider == PROVIDER)
        .where(Todo.external_id == external_id)
        .limit(1)
    )


def resolve_cached_todo(session: Session, todo_id: str) -> Todo:
    row = session.get(Todo, todo_id)
    if row and row.provider == PROVIDER and row.external_id:
        return row
    external_row = cached_todo_by_external_id(session, todo_id)
    if external_row:
        return external_row
    raise ValueError("todo not found")


def resolve_external_id(session: Session, todo_id: str) -> str:
    row = resolve_cached_todo(session, todo_id)
    if not row.external_id:
        raise ValueError("todo is missing a Todoist external id")
    return row.external_id


def upsert_todoist_task(session: Session, task: NormalizedTodoistTask, source: str | None = None) -> Todo:
    row = cached_todo_by_external_id(session, task.external_id)
    if row is None:
        row = Todo(
            external_id=task.external_id,
            provider=task.provider,
            source=source if source in {"user", "agent", "channel"} else "user",
        )
        session.add(row)
    row.title = task.title
    if task.notes is not None or row.notes is None:
        row.notes = task.notes
    if task.due_at is not None:
        row.due_at = task.due_at
    row.scheduled_for = task.scheduled_for
    if task.tags:
        row.tags = task.tags
    elif row.tags is None:
        row.tags = []
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
