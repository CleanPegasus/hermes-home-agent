from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .db import init_db, make_engine, make_session_factory
from .jobs import create_job, handle_action, invoke_agent
from .models import Job, JobEvent, Note, Page, Tile, Todo


class CommandIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ActionIn(BaseModel):
    action: str = Field(min_length=1, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)


def create_app() -> FastAPI:
    engine = make_engine()
    init_db(engine)
    session_factory = make_session_factory(engine)

    app = FastAPI(title="hermes home")
    app.state.session_factory = session_factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(","),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"ok": "true"}

    @app.get("/api/tiles")
    def tiles(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        rows = session.scalars(select(Tile).order_by(Tile.sort)).all()
        return {"tiles": [serialize_tile(tile) for tile in rows]}

    @app.get("/api/todos")
    def todos(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        rows = session.scalars(select(Todo).order_by(Todo.created_at.desc())).all()
        return {"todos": [serialize_todo(todo) for todo in rows]}

    @app.get("/api/notes")
    def notes(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        rows = session.scalars(select(Note).where(Note.archived.is_(False)).order_by(Note.updated_at.desc())).all()
        return {"notes": [serialize_note(note) for note in rows]}

    @app.get("/api/jobs")
    def jobs(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        rows = session.scalars(select(Job).order_by(Job.started_at.desc().nullslast())).all()
        return {"jobs": [serialize_job(job) for job in rows]}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = session.get(Job, job_id)
        if not row:
            raise HTTPException(status_code=404, detail="job not found")
        return {"job": serialize_job(row)}

    @app.get("/api/jobs/{job_id}/events")
    def job_events(job_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> Response:
        row = session.get(Job, job_id)
        if not row:
            raise HTTPException(status_code=404, detail="job not found")
        events = session.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.ts)).all()
        body = "".join(format_sse(event) for event in events)
        return Response(content=body, media_type="text/event-stream")

    @app.get("/api/pages/{page_id}")
    def page(page_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = session.get(Page, page_id)
        if not row:
            raise HTTPException(status_code=404, detail="page not found")
        return {"page": serialize_page(row)}

    @app.post("/api/command")
    def command(payload: CommandIn, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = create_job(session, payload.text)
        invoke_agent(session, row)
        session.flush()
        return {"job_id": row.id}

    @app.post("/api/actions")
    def actions(payload: ActionIn, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        result = handle_action(session, payload.action, payload.payload)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "action failed"))
        return result

    return app


def require_auth(authorization: str | None = Header(default=None)) -> None:
    token = os.getenv("HOME_API_TOKEN", "dev-token")
    if authorization is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    prefix = "Bearer "
    if not authorization.startswith(prefix) or authorization[len(prefix):] != token:
        raise HTTPException(status_code=401, detail="invalid bearer token")


def serialize_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def serialize_tile(tile: Tile) -> dict:
    return {
        "key": tile.key,
        "size": tile.size,
        "color": tile.color,
        "sort": tile.sort,
        "front": tile.front,
        "back": tile.back,
        "updated_at": serialize_dt(tile.updated_at),
    }


def serialize_todo(todo: Todo) -> dict:
    return {
        "id": todo.id,
        "title": todo.title,
        "notes": todo.notes,
        "due_at": serialize_dt(todo.due_at),
        "scheduled_for": serialize_dt(todo.scheduled_for),
        "tags": todo.tags,
        "status": todo.status,
        "source": todo.source,
        "things_id": todo.things_id,
        "created_at": serialize_dt(todo.created_at),
        "completed_at": serialize_dt(todo.completed_at),
    }


def serialize_note(note: Note) -> dict:
    return {
        "id": note.id,
        "category_id": note.category_id,
        "title": note.title,
        "body_md": note.body_md,
        "source_job_id": note.source_job_id,
        "archived": note.archived,
        "created_at": serialize_dt(note.created_at),
        "updated_at": serialize_dt(note.updated_at),
    }


def serialize_job(job: Job) -> dict:
    return {
        "id": job.id,
        "command": job.command,
        "status": job.status,
        "page_id": job.page_id,
        "error": job.error,
        "started_at": serialize_dt(job.started_at),
        "finished_at": serialize_dt(job.finished_at),
    }


def serialize_page(page: Page) -> dict:
    return {
        "id": page.id,
        "job_id": page.job_id,
        "title": page.title,
        "html": page.html,
        "created_at": serialize_dt(page.created_at),
    }


def format_sse(event: JobEvent) -> str:
    payload = {"id": event.id, "ts": serialize_dt(event.ts), "kind": event.kind, "text": event.text}
    return f"id: {event.id}\nevent: {event.kind}\ndata: {json.dumps(payload)}\n\n"


app = create_app()
