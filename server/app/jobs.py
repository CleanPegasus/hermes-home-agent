from __future__ import annotations

import json
import os
import shlex
import subprocess
from datetime import timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .models import Approval, Job, JobEvent, Page, Tile, Todo, utcnow
from .sanitize import page_document


def log_event(session: Session, job_id: str, text: str, kind: str = "step") -> JobEvent:
    event = JobEvent(job_id=job_id, text=text, kind=kind)
    session.add(event)
    session.flush()
    return event


def create_job(session: Session, command: str) -> Job:
    job = Job(command=command.strip(), status="queued")
    session.add(job)
    session.flush()
    refresh_jobs_tile(session)
    return job


def invoke_agent(session: Session, job: Job) -> None:
    agent_cmd = os.getenv("AGENT_CMD")
    if agent_cmd:
        invoke_external_agent(session, job, agent_cmd)
    else:
        invoke_fallback_agent(session, job)


def invoke_external_agent(session: Session, job: Job, agent_cmd: str) -> None:
    job.status = "running"
    job.started_at = utcnow()
    log_event(session, job.id, "handing command to hermes")
    session.commit()

    env = os.environ.copy()
    env["HERMES_HOME_JOB_ID"] = job.id
    env["HERMES_HOME_COMMAND"] = job.command
    command = [part.format(job_id=job.id) for part in shlex.split(agent_cmd)]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=600, check=False)

    session.refresh(job)
    if job.page_id:
        return

    job.status = "failed"
    job.error = result.stderr.strip() or result.stdout.strip() or "agent exited without publishing a page"
    job.finished_at = utcnow()
    log_event(session, job.id, "agent exited without publishing a page", "warn")
    refresh_jobs_tile(session)


def invoke_fallback_agent(session: Session, job: Job) -> None:
    job.status = "running"
    job.started_at = utcnow()
    refresh_jobs_tile(session)
    log_event(session, job.id, "reading command")
    log_event(session, job.id, "matching local fallback skill")

    title = extract_todo_title(job.command)
    todo = Todo(title=title, source="agent")
    session.add(todo)
    session.flush()
    log_event(session, job.id, f"created todo · {title}")
    refresh_todos_tile(session)

    html = page_document(
        title,
        f"""
        <p class="lede">i converted the command into a todo and prepared one action.</p>
        <section class="verdict">todo added · {title}</section>
        <table>
          <tbody>
            <tr><th>state</th><td>open</td></tr>
            <tr><th>source</th><td>hermes home fallback</td></tr>
          </tbody>
        </table>
        <button onclick="alert('blocked')" data-action="todos.complete" data-payload='{json.dumps({"todo_id": todo.id})}'>mark done</button>
        <script>window.evil = true</script>
        """,
    )
    publish_page(session, job, title, html)


def extract_todo_title(command: str) -> str:
    text = command.strip().lower()
    for prefix in ("add ", "todo ", "remember to "):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    for suffix in (" to my todos", " to todos", " to my todo list", " to the list"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return " ".join(text.split()) or "untitled task"


def publish_page(session: Session, job: Job, title: str, html: str) -> Page:
    log_event(session, job.id, "publishing page")
    page = Page(job_id=job.id, title=title.lower(), html=html)
    session.add(page)
    session.flush()
    job.status = "done"
    job.page_id = page.id
    job.finished_at = utcnow()
    refresh_jobs_tile(session)
    return page


def handle_action(session: Session, action: str, payload: dict) -> dict:
    if action == "todos.complete":
        todo_id = str(payload.get("todo_id", ""))
        todo = session.get(Todo, todo_id)
        if not todo:
            return {"ok": False, "error": "todo not found"}
        todo.status = "done"
        todo.completed_at = utcnow()
        refresh_todos_tile(session)
        return {"ok": True, "tile": "todos"}

    if action == "approvals.request":
        job_id = str(payload.get("job_id", ""))
        approval = Approval(
            job_id=job_id,
            action=str(payload.get("action_name", "unknown")),
            scope=payload.get("scope", {}),
            expires_at=utcnow() + timedelta(hours=4),
        )
        session.add(approval)
        refresh_approvals_tile(session)
        return {"ok": True, "tile": "approvals"}

    return {"ok": False, "error": "unknown action"}


def refresh_jobs_tile(session: Session) -> None:
    session.flush()
    running = session.scalar(
        select(func.count()).select_from(Job).where(Job.status.in_(["queued", "running", "needs_approval"]))
    ) or 0
    last = session.scalar(select(Job).where(Job.status == "done").order_by(desc(Job.finished_at)).limit(1))
    update_tile(
        session,
        "jobs",
        front={"count": int(running), "line": "running" if running else "ready", "sub": "live ledger"},
        back={
            "line": "last finished",
            "sub": last.command[:48] if last else "nothing yet",
            "glyph": ">",
        },
    )


def refresh_todos_tile(session: Session) -> None:
    session.flush()
    open_count = session.scalar(select(func.count()).select_from(Todo).where(Todo.status == "open")) or 0
    next_todo = session.scalar(select(Todo).where(Todo.status == "open").order_by(Todo.created_at).limit(1))
    last_done = session.scalar(select(Todo).where(Todo.status == "done").order_by(desc(Todo.completed_at)).limit(1))
    update_tile(
        session,
        "todos",
        front={
            "count": int(open_count),
            "line": "open",
            "sub": next_todo.title if next_todo else "nothing due",
        },
        back={
            "line": "last finished",
            "sub": last_done.title if last_done else "nothing yet",
            "glyph": "check",
        },
    )


def refresh_approvals_tile(session: Session) -> None:
    session.flush()
    pending = session.scalar(select(func.count()).select_from(Approval).where(Approval.status == "pending")) or 0
    update_tile(
        session,
        "approvals",
        front={"count": int(pending), "line": "appr", "sub": ""},
        back={"line": "needs", "sub": "review" if pending else "none", "glyph": "!"},
    )


def update_tile(session: Session, key: str, front: dict, back: dict | None = None) -> None:
    tile = session.get(Tile, key)
    if not tile:
        return
    tile.front = front
    if back is not None:
        tile.back = back
    tile.updated_at = utcnow()
