from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .models import AgentProfile, Approval, CalendarEvent, Job, JobEvent, Page, Tile, utcnow
from .sanitize import page_document
from .todo_provider import cached_done_todos, cached_open_todos, complete_todo, create_todo, drop_todo, reopen_todo
from .vault import VaultStore
from .vikunja import VikunjaError, vikunja_status


ACTION_REGISTRY = {
    "todos.complete": {
        "name": "todos.complete",
        "label": "mark done",
        "danger": "low",
        "requires_confirmation": False,
        "required_payload": ["todo_id"],
        "refresh": ["todos", "tiles"],
    },
    "todos.reopen": {
        "name": "todos.reopen",
        "label": "reopen",
        "danger": "low",
        "requires_confirmation": False,
        "required_payload": ["todo_id"],
        "refresh": ["todos", "tiles"],
    },
    "todos.drop": {
        "name": "todos.drop",
        "label": "drop",
        "danger": "medium",
        "requires_confirmation": True,
        "required_payload": ["todo_id"],
        "refresh": ["todos", "tiles"],
    },
    "approvals.request": {
        "name": "approvals.request",
        "label": "request approval",
        "danger": "medium",
        "requires_confirmation": False,
        "required_payload": ["action_name", "scope"],
        "refresh": ["approvals", "tiles"],
    },
    "approvals.approve": {
        "name": "approvals.approve",
        "label": "approve",
        "danger": "high",
        "requires_confirmation": True,
        "required_payload": ["approval_id"],
        "refresh": ["approvals", "tiles"],
    },
    "approvals.reject": {
        "name": "approvals.reject",
        "label": "reject",
        "danger": "medium",
        "requires_confirmation": True,
        "required_payload": ["approval_id"],
        "refresh": ["approvals", "tiles"],
    },
}

HISTORY_EMOJI_RULES = [
    (("todo", "buy", "remind", "task"), "✅"),
    (("summarize", "summary", "research", "find", "look up"), "🔎"),
    (("note", "file", "remember", "write down"), "📝"),
    (("calendar", "schedule", "meeting", "event"), "📅"),
    (("spend", "budget", "money", "cost"), "💸"),
]


def log_event(session: Session, job_id: str, text: str, kind: str = "step") -> JobEvent:
    event = JobEvent(job_id=job_id, text=text, kind=kind)
    session.add(event)
    session.flush()
    return event


def create_job(session: Session, command: str, profile_id: str | None = None) -> Job:
    job = Job(command=command.strip(), status="queued", profile_id=profile_id)
    session.add(job)
    session.flush()
    refresh_jobs_tile(session)
    return job


def derive_history_meta(command: str, status: str) -> tuple[str, str]:
    normalized = " ".join(command.strip().split())
    summary = normalized or status
    if len(summary) > 60:
        summary = f"{summary[:57].rstrip()}..."
    if status == "failed":
        return "⚠️", summary
    if status == "cancelled":
        return "🛑", summary
    lowered = normalized.lower()
    for keywords, emoji in HISTORY_EMOJI_RULES:
        if any(keyword in lowered for keyword in keywords):
            return emoji, summary
    return "💬", summary


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

    profile = session.get(AgentProfile, job.profile_id) if job.profile_id else None
    env = agent_environment(job, profile)
    command = [part.format(job_id=job.id) for part in shlex.split(agent_cmd)]
    process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout = ""
    stderr = ""
    timed_out = False
    for _ in range(1200):
        try:
            stdout, stderr = process.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            session.refresh(job)
            if job.status == "cancelled":
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                log_event(session, job.id, "terminated hermes process after cancellation", "warn")
                refresh_jobs_tile(session)
                session.commit()
                return
    else:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate()

    session.refresh(job)
    job.exit_code = process.returncode
    job.stdout_tail = tail_text(stdout)
    job.stderr_tail = tail_text(stderr)
    if job.status == "cancelled":
        refresh_jobs_tile(session)
        session.commit()
        return

    if job.page_id:
        refresh_jobs_tile(session)
        session.commit()
        return

    job.status = "failed"
    if timed_out:
        job.error = "agent timed out after 10 minutes"
    else:
        job.error = stderr.strip() or stdout.strip() or "agent exited without publishing a page"
    job.finished_at = utcnow()
    log_event(session, job.id, job.error, "warn")
    refresh_jobs_tile(session)


def agent_environment(job: Job, profile: AgentProfile | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["HERMES_HOME_JOB_ID"] = job.id
    env["HERMES_HOME_COMMAND"] = job.command
    if os.getenv("OBSIDIAN_VAULT_PATH"):
        env["OBSIDIAN_VAULT_PATH"] = os.getenv("OBSIDIAN_VAULT_PATH", "")
    if profile:
        env["HERMES_HOME_PROFILE_ID"] = profile.id
        env["HERMES_HOME_PROFILE_NAME"] = profile.name
        env["HERMES_HOME_PROFILE_PERSONA"] = profile.persona
    return env


def invoke_fallback_agent(session: Session, job: Job) -> None:
    job.status = "running"
    job.started_at = utcnow()
    refresh_jobs_tile(session)
    log_event(session, job.id, "reading command")
    log_event(session, job.id, "matching Vikunja todo capture")

    parsed = parse_todo_command(job.command)
    try:
        todo = create_todo(session, title=parsed.title, due_at=parsed.due_at, source="agent")
        refresh_todos_tile(session)
    except VikunjaError as exc:
        job.status = "failed"
        job.error = str(exc)
        job.finished_at = utcnow()
        log_event(session, job.id, str(exc), "warn")
        refresh_jobs_tile(session)
        return
    log_event(session, job.id, f"created Vikunja todo · {parsed.title}")
    job.emoji = "✅"
    job.summary = f"added '{parsed.title}' to todos"[:140]

    html = page_document(
        parsed.title,
        f"""
        <p class="lede">i converted the command into a Vikunja todo and prepared one action.</p>
        <section class="verdict">todo added · {parsed.title}</section>
        <table>
          <tbody>
            <tr><th>state</th><td>open</td></tr>
            <tr><th>source</th><td>vikunja</td></tr>
          </tbody>
        </table>
        <button onclick="alert('blocked')" data-action="todos.complete" data-payload='{json.dumps({"todo_id": todo.id})}'>mark done</button>
        <script>window.evil = true</script>
        """,
    )
    publish_page(
        session,
        job,
        parsed.title,
        html,
        provenance={
            "reads": [{"type": "command", "label": "user command", "value": job.command}],
            "writes": [
                {
                    "type": "todo",
                    "id": todo.id,
                    "external_id": todo.external_id,
                    "provider": todo.provider,
                    "title": todo.title,
                    "status": todo.status,
                },
                {"type": "tile", "key": "todos", "reason": "todo count changed"},
            ],
            "skipped": [{"type": "external_agent", "reason": "AGENT_CMD is not configured"}],
            "inaccessible": [],
        },
    )


@dataclass(frozen=True)
class ParsedTodoCommand:
    title: str
    due_at: datetime | None = None


def parse_todo_command(command: str, now: datetime | None = None) -> ParsedTodoCommand:
    text = command.strip().lower()
    for prefix in ("add ", "todo ", "remember to "):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    for suffix in (" to my todos", " to todos", " to my todo list", " to the list"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    due_at: datetime | None = None
    reference = now or utcnow()
    date_phrases = {
        " tomorrow": 1,
        " today": 0,
        " tonight": 0,
    }
    for phrase, days in date_phrases.items():
        if text.endswith(phrase):
            text = text[: -len(phrase)]
            due_date = reference.astimezone(timezone.utc).date() + timedelta(days=days)
            due_at = datetime.combine(due_date, dt_time(23, 59), tzinfo=timezone.utc)
            break
    return ParsedTodoCommand(title=" ".join(text.split()) or "untitled task", due_at=due_at)


def extract_todo_title(command: str) -> str:
    return parse_todo_command(command).title


def publish_page(session: Session, job: Job, title: str, html: str, provenance: dict | None = None) -> Page:
    log_event(session, job.id, "publishing page")
    page_provenance = {
        "source_job_id": job.id,
        "source_command": job.command,
        "agent": "external" if os.getenv("AGENT_CMD") else "fallback",
        "reads": [{"type": "command", "label": "user command", "value": job.command}],
        "writes": [],
        "skipped": [],
        "inaccessible": [],
    }
    if provenance:
        for key in ("reads", "writes", "skipped", "inaccessible"):
            page_provenance[key] = provenance.get(key, page_provenance[key])
    page = Page(
        job_id=job.id,
        title=title.lower(),
        html=html,
        provenance=page_provenance,
    )
    session.add(page)
    session.flush()
    page.provenance = {
        **page.provenance,
        "writes": [
            *page.provenance.get("writes", []),
            {"type": "page", "id": page.id, "title": page.title},
        ],
    }
    job.status = "done"
    job.page_id = page.id
    job.finished_at = utcnow()
    refresh_jobs_tile(session)
    return page


def tail_text(value: str, limit: int = 12000) -> str | None:
    if not value:
        return None
    return value[-limit:]


def handle_action(session: Session, action: str, payload: dict) -> dict:
    if action == "todos.complete":
        todo_id = str(payload.get("todo_id", ""))
        try:
            todo = complete_todo(session, todo_id)
        except (ValueError, VikunjaError) as exc:
            return {"ok": False, "error": str(exc)}
        refresh_todos_tile(session)
        return {
            "ok": True,
            "tile": "todos",
            "todo_id": todo.id,
            "external_id": todo.external_id,
            "status": todo.status,
        }

    if action == "todos.reopen":
        todo_id = str(payload.get("todo_id", ""))
        try:
            todo = reopen_todo(session, todo_id)
        except (ValueError, VikunjaError) as exc:
            return {"ok": False, "error": str(exc)}
        refresh_todos_tile(session)
        return {
            "ok": True,
            "tile": "todos",
            "todo_id": todo.id,
            "external_id": todo.external_id,
            "status": todo.status,
        }

    if action == "todos.drop":
        todo_id = str(payload.get("todo_id", ""))
        try:
            result = drop_todo(session, todo_id)
        except (ValueError, VikunjaError) as exc:
            return {"ok": False, "error": str(exc)}
        refresh_todos_tile(session)
        return result

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
        return {"ok": True, "tile": "approvals", "approval_id": approval.id}

    if action == "approvals.approve":
        approval_id = str(payload.get("approval_id", ""))
        approval = session.get(Approval, approval_id)
        if not approval:
            return {"ok": False, "error": "approval not found"}
        if approval.status == "approved":
            refresh_approvals_tile(session)
            return {"ok": True, "tile": "approvals", "approval_id": approval.id, "status": approval.status, "result": approval.result}
        if approval.status == "expired":
            refresh_approvals_tile(session)
            return {"ok": False, "error": "approval expired", "approval_id": approval.id, "status": approval.status}
        if approval_has_expired(approval):
            expire_approval(session, approval)
            if approval.job_id and session.get(Job, approval.job_id):
                log_event(session, approval.job_id, f"expired {approval.action}", "warn")
            refresh_approvals_tile(session)
            return {"ok": False, "error": "approval expired", "approval_id": approval.id, "status": approval.status}
        approval.status = "approved"
        approval.decided_at = utcnow()
        approval.result = execute_approval(session, approval)
        approval.error = None
        if approval.job_id and session.get(Job, approval.job_id):
            log_event(session, approval.job_id, f"approved {approval.action}", "tool")
        refresh_approvals_tile(session)
        return {"ok": True, "tile": "approvals", "approval_id": approval.id, "status": approval.status, "result": approval.result}

    if action == "approvals.reject":
        approval_id = str(payload.get("approval_id", ""))
        approval = session.get(Approval, approval_id)
        if not approval:
            return {"ok": False, "error": "approval not found"}
        if approval.status == "rejected":
            refresh_approvals_tile(session)
            return {"ok": True, "tile": "approvals", "approval_id": approval.id, "status": approval.status, "result": approval.result}
        approval.status = "rejected"
        approval.decided_at = utcnow()
        approval.result = {"executed": False, "message": "approval rejected"}
        approval.error = None
        if approval.job_id and session.get(Job, approval.job_id):
            log_event(session, approval.job_id, f"rejected {approval.action}", "warn")
        refresh_approvals_tile(session)
        return {"ok": True, "tile": "approvals", "approval_id": approval.id, "status": approval.status, "result": approval.result}

    return {"ok": False, "error": "unknown action"}


def approval_has_expired(approval: Approval, now: datetime | None = None) -> bool:
    if approval.expires_at is None:
        return False
    expires_at = approval.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    current = now or utcnow()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return expires_at <= current


def expire_approval(session: Session, approval: Approval) -> None:
    approval.status = "expired"
    approval.decided_at = utcnow()
    approval.result = {"executed": False, "message": "approval expired before execution"}
    approval.error = "approval expired"
    session.flush()


def execute_approval(session: Session, approval: Approval) -> dict:
    if approval.action == "calendar.create_event":
        event = CalendarEvent(
            calendar_id=str(approval.scope.get("calendar_id", "primary")),
            summary=str(approval.scope.get("summary", "untitled event")),
            starts_at=parse_dt(approval.scope.get("starts_at")),
            ends_at=parse_dt(approval.scope.get("ends_at")),
            source_approval_id=approval.id,
        )
        session.add(event)
        session.flush()
        refresh_calendar_tile(session)
        return {
            "executed": True,
            "adapter": "local.calendar_events",
            "message": "calendar event created in local hermes calendar",
            "event_id": event.id,
        }
    if approval.action == "calendar.update_event":
        event_id = str(approval.scope.get("event_id", ""))
        event = session.get(CalendarEvent, event_id)
        if not event:
            return {
                "executed": False,
                "adapter": "local.calendar_events",
                "message": "calendar event was not found",
                "event_id": event_id,
            }
        changes = approval.scope.get("changes", {})
        if isinstance(changes, dict):
            if "summary" in changes:
                event.summary = str(changes["summary"])
            if "starts_at" in changes:
                event.starts_at = parse_dt(changes["starts_at"])
            if "ends_at" in changes:
                event.ends_at = parse_dt(changes["ends_at"])
            if "status" in changes:
                event.status = str(changes["status"])
        event.updated_at = utcnow()
        refresh_calendar_tile(session)
        return {
            "executed": True,
            "adapter": "local.calendar_events",
            "message": "calendar event updated in local hermes calendar",
            "event_id": event.id,
        }
    return {
        "executed": False,
        "message": "no execution adapter is configured for this approval action",
        "scope": approval.scope,
    }


def parse_dt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def cancel_job(session: Session, job: Job) -> dict:
    if job.status in {"done", "failed", "cancelled"}:
        return {"ok": True, "job_id": job.id, "status": job.status}
    job.status = "cancelled"
    job.error = "cancelled by user"
    job.finished_at = utcnow()
    log_event(session, job.id, "cancelled by user", "warn")
    refresh_jobs_tile(session)
    return {"ok": True, "job_id": job.id, "status": job.status}


def refresh_jobs_tile(session: Session) -> None:
    session.flush()
    running = session.scalar(
        select(func.count()).select_from(Job).where(Job.status.in_(["queued", "running", "needs_approval"]))
    ) or 0
    last = session.scalar(select(Job).where(Job.status == "done").order_by(desc(Job.finished_at)).limit(1))
    update_tile(
        session,
        "jobs",
        front={"count": int(running), "emoji": "⚙️", "line": "running" if running else "ready", "sub": "live ledger"},
        back={
            "line": "last finished",
            "sub": last.command[:48] if last else "nothing yet",
            "glyph": ">",
        },
    )


def recover_interrupted_jobs(session: Session) -> int:
    rows = session.scalars(select(Job).where(Job.status.in_(["queued", "running"]))).all()
    if not rows:
        return 0
    for job in rows:
        previous = job.status
        job.status = "failed"
        job.error = f"marked failed during startup recovery from stale {previous} state"
        job.finished_at = utcnow()
        log_event(session, job.id, job.error, "warn")
    refresh_jobs_tile(session)
    return len(rows)


def refresh_todos_tile(session: Session) -> None:
    if not vikunja_status()["configured"]:
        update_tile(
            session,
            "todos",
            front={"count": 0, "emoji": "✅", "line": "setup", "sub": "connect Vikunja"},
            back={"line": "not configured", "sub": "set url and token", "glyph": "check"},
        )
        return
    try:
        open_todos = cached_open_todos(session)
        done_todos = cached_done_todos(session)
    except Exception:
        open_todos = []
        done_todos = []
    next_todo = open_todos[0] if open_todos else None
    last_done = done_todos[0] if done_todos else None
    update_tile(
        session,
        "todos",
        front={
            "count": len(open_todos),
            "emoji": "✅",
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
        front={"count": int(pending), "emoji": "🛡️", "line": "appr", "sub": ""},
        back={"line": "needs", "sub": "review" if pending else "none", "glyph": "!"},
    )


def refresh_calendar_tile(session: Session) -> None:
    session.flush()
    count = session.scalar(select(func.count()).select_from(CalendarEvent).where(CalendarEvent.status == "confirmed")) or 0
    next_event = session.scalar(
        select(CalendarEvent)
        .where(CalendarEvent.status == "confirmed")
        .where(CalendarEvent.starts_at.is_not(None))
        .order_by(CalendarEvent.starts_at)
        .limit(1)
    )
    update_tile(
        session,
        "calendar",
        front={"count": int(count), "emoji": "📅", "line": "events", "sub": next_event.summary if next_event else "local calendar"},
        back={"line": "adapter", "sub": "approval gated", "glyph": "cal"},
    )


def refresh_notes_tile(session: Session) -> None:
    session.flush()
    vault = VaultStore(os.getenv("OBSIDIAN_VAULT_PATH"))
    notes = vault.list_notes() if vault.configured() else []
    latest = notes[0] if notes else None
    update_tile(
        session,
        "notes",
        front={"count": len(notes), "emoji": "📝", "line": "filed", "sub": latest["title"] if latest else "nothing yet"},
        back={"line": "categories", "sub": "inbox home errands", "glyph": "note"},
    )


def update_tile(session: Session, key: str, front: dict, back: dict | None = None) -> None:
    tile = session.get(Tile, key)
    if not tile:
        return
    tile.front = front
    if back is not None:
        tile.back = back
    tile.updated_at = utcnow()
