from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import shutil
import subprocess
import tempfile
import threading
import time
import warnings
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from .connectors import connector_history, connector_status, sync_all
from .db import init_db, make_engine, make_session_factory
from .jobs import ACTION_REGISTRY, cancel_job, create_job, derive_history_meta, handle_action, invoke_agent, recover_interrupted_jobs, refresh_notes_tile, refresh_todos_tile, tail_text
from .todo_provider import list_todos
from .vault import VaultConfigurationError, VaultError, VaultNoteNotFoundError, VaultStore
from .vikunja import VikunjaConfigurationError, VikunjaError, vikunja_status
from .models import ActionRun, AgentProfile, Approval, CalendarEvent, Category, ChannelMessage, Clarification, CodexRun, ConnectorSyncRun, Job, JobEvent, Note, Page, SpendItem, Tile, Todo, utcnow

CODEX_EFFORT_LEVELS = ("low", "medium", "high", "xhigh")
CodexEffort = Literal["low", "medium", "high", "xhigh"]
_VAULT_STORE: VaultStore | None = None
_VAULT_PATH: str | None = None


class CommandIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    profile_id: str | None = Field(default=None, max_length=80)


class ClarificationAnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


class ActionIn(BaseModel):
    action: str = Field(min_length=1, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=160)


class NotePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body_md: str | None = None
    category: str | None = Field(default=None, max_length=120)
    tags: list[str] | None = None
    category_id: str | None = None
    archived: bool | None = None


class NoteMergeIn(BaseModel):
    target_note_id: str = Field(min_length=1)


class CodexRunIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    effort: CodexEffort = Field(default_factory=lambda: default_codex_effort())
    confirm_dangerous_mode: bool = False


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    emoji: str = Field(default="🤖", min_length=1, max_length=8)
    color: str = Field(default="#1BA1E2", min_length=1, max_length=40)
    persona: str = Field(default="", max_length=12000)
    is_default: bool = False


class ProfilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    emoji: str | None = Field(default=None, min_length=1, max_length=8)
    color: str | None = Field(default=None, min_length=1, max_length=40)
    persona: str | None = Field(default=None, max_length=12000)
    is_default: bool | None = None


def get_vault() -> VaultStore:
    global _VAULT_PATH, _VAULT_STORE
    path = os.getenv("OBSIDIAN_VAULT_PATH")
    if _VAULT_STORE is None or path != _VAULT_PATH:
        _VAULT_PATH = path
        _VAULT_STORE = VaultStore(path)
    return _VAULT_STORE


def vault_not_configured_warning() -> str:
    return "OBSIDIAN_VAULT_PATH is not configured. Set it to your Obsidian vault folder to use notes."


def vault_note_count() -> int:
    vault = get_vault()
    if not vault.configured():
        return 0
    try:
        return vault.count()
    except VaultError:
        return 0


def vault_http_exception(exc: VaultError) -> HTTPException:
    if isinstance(exc, VaultConfigurationError):
        return HTTPException(status_code=503, detail=vault_not_configured_warning())
    if isinstance(exc, VaultNoteNotFoundError):
        return HTTPException(status_code=404, detail="note not found")
    return HTTPException(status_code=400, detail=str(exc))


def create_app() -> FastAPI:
    engine = make_engine()
    init_db(engine)
    session_factory = make_session_factory(engine)
    with session_factory() as startup_session:
        recovered_jobs = recover_interrupted_jobs(startup_session)
        recovered_codex_runs = recover_interrupted_codex_runs(startup_session)
        startup_session.commit()
    warn_on_insecure_deployment_defaults()

    app = FastAPI(title="hermes home")
    app.state.session_factory = session_factory
    app.state.startup_recovery = {"jobs": recovered_jobs, "codex_runs": recovered_codex_runs}
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv(
            "CORS_ORIGINS",
            "http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:5175,http://localhost:5173,http://localhost:5174,http://localhost:5175",
        ).split(","),
        allow_origin_regex=os.getenv("CORS_ORIGIN_REGEX", r"http://(127\.0\.0\.1|localhost):51[0-9]{2}"),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    async def get_session() -> AsyncIterator[Session]:
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
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "agent_configured": bool(os.getenv("AGENT_CMD")),
            "database": database_kind(os.getenv("DATABASE_URL", "sqlite:///./hermes-home.db")),
        }

    @app.get("/api/session")
    async def session_info(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        running = session.scalar(select(Job).where(Job.status.in_(["queued", "running", "needs_approval", "needs_clarification"])).limit(1))
        pending_approval = session.scalar(select(Approval).where(Approval.status == "pending").limit(1))
        return {
            "ok": True,
            "agent": {
                "configured": bool(os.getenv("AGENT_CMD")),
                "state": "running" if running else "listening",
            },
            "database": database_kind(os.getenv("DATABASE_URL", "sqlite:///./hermes-home.db")),
            "mcp": {"configured": True},
            "auth": {"valid": True},
            "approvals": {"pending": pending_approval is not None},
            "connectors": connector_status(session),
            "todos": vikunja_status(),
        }

    @app.get("/api/capabilities")
    async def capabilities(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        tiles = session.scalars(select(Tile).order_by(Tile.sort)).all()
        return {
            "agent_configured": bool(os.getenv("AGENT_CMD")),
            "tiles": [tile.key for tile in tiles],
            "actions": list(ACTION_REGISTRY.values()),
            "features": {
                "approvals": True,
                "calendar_writes": "local_approval_adapter",
                "connectors": connector_status(session),
                "channels": "json_file_adapter",
                "spend": "json_file_adapter",
                "vitals": True,
                "codex_yolo": {
                    "available": codex_available(),
                    "enabled": codex_enabled(),
                    "binary_available": codex_binary_available(),
                    "workdir": str(codex_web_workdir()),
                    "mode": "dangerously-bypass-approvals-and-sandbox",
                    "effort": default_codex_effort(),
                    "effort_options": list(CODEX_EFFORT_LEVELS),
                    "requires_confirmation": True,
                },
                "job_retry": True,
                "job_cancel": True,
                "notes_search": True,
                "todos": vikunja_status(),
            },
        }

    @app.get("/api/tiles")
    async def tiles(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        if not vikunja_status()["configured"]:
            refresh_todos_tile(session)
            session.flush()
        rows = session.scalars(select(Tile).order_by(Tile.sort)).all()
        return {"tiles": [serialize_tile(tile) for tile in rows]}

    @app.get("/api/categories")
    async def categories(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        rows = session.scalars(select(Category).order_by(Category.created_at, Category.slug)).all()
        return {"categories": [serialize_category(category) for category in rows]}

    @app.get("/api/profiles")
    async def profiles(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        rows = session.scalars(select(AgentProfile).order_by(AgentProfile.is_default.desc(), AgentProfile.created_at, AgentProfile.name)).all()
        default = default_profile(session)
        return {"profiles": [serialize_profile(profile) for profile in rows], "default_id": default.id if default else None}

    @app.post("/api/profiles")
    async def create_profile(payload: ProfileIn, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        if payload.is_default:
            clear_default_profiles(session)
        profile = AgentProfile(
            slug=unique_profile_slug(session, payload.name),
            name=payload.name.strip().lower(),
            emoji=payload.emoji.strip(),
            color=payload.color.strip(),
            persona=payload.persona.strip(),
            is_default=payload.is_default,
        )
        session.add(profile)
        session.flush()
        if not session.scalar(select(AgentProfile).where(AgentProfile.is_default.is_(True)).where(AgentProfile.id != profile.id)):
            profile.is_default = True
        return {"profile": serialize_profile(profile)}

    @app.patch("/api/profiles/{profile_id}")
    async def update_profile(profile_id: str, payload: ProfilePatch, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        profile = session.get(AgentProfile, profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="profile not found")
        if payload.is_default is True:
            clear_default_profiles(session)
            profile.is_default = True
        elif payload.is_default is False and profile.is_default:
            raise HTTPException(status_code=400, detail="one profile must remain default")
        if payload.name is not None:
            profile.name = payload.name.strip().lower()
            profile.slug = unique_profile_slug(session, profile.name, exclude_id=profile.id)
        if payload.emoji is not None:
            profile.emoji = payload.emoji.strip()
        if payload.color is not None:
            profile.color = payload.color.strip()
        if payload.persona is not None:
            profile.persona = payload.persona.strip()
        profile.updated_at = utcnow()
        return {"profile": serialize_profile(profile)}

    @app.delete("/api/profiles/{profile_id}")
    async def delete_profile(profile_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        profile = session.get(AgentProfile, profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="profile not found")
        if profile.is_default:
            raise HTTPException(status_code=409, detail="cannot delete the default profile")
        session.delete(profile)
        return {"ok": True}

    @app.get("/api/todos")
    async def todos(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        status = vikunja_status()
        try:
            client = None
            from .vikunja import VikunjaClient

            client = VikunjaClient.from_env()
            rows = list_todos(session, client=client)
            projects = serialize_vikunja_projects(client.list_projects())
            labels = serialize_vikunja_labels(client.list_labels())
        except VikunjaConfigurationError as exc:
            refresh_todos_tile(session)
            return {
                "todos": [],
                "projects": [],
                "labels": [],
                "configured": False,
                "provider": "vikunja",
                "status": status,
                "warning": str(exc),
            }
        except VikunjaError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        refresh_todos_tile(session)
        return {
            "todos": [serialize_todo(todo) for todo in rows],
            "projects": projects,
            "labels": labels,
            "configured": status["configured"],
            "provider": status["provider"],
            "status": status,
            "warning": None,
        }

    @app.get("/api/notes")
    async def notes(
        _: None = Depends(require_auth),
        q: str | None = Query(default=None, max_length=300),
        category: str | None = Query(default=None, max_length=120),
    ) -> dict:
        vault = get_vault()
        if not vault.configured():
            return {"notes": [], "configured": False, "warning": vault_not_configured_warning()}
        try:
            if q and q.strip():
                rows = vault.search(q, limit=200)
                if category:
                    rows = [row for row in rows if row["category"] == category]
            else:
                rows = vault.list_notes(category=category)
        except VaultError as exc:
            raise vault_http_exception(exc) from exc
        return {"notes": [serialize_note(note) for note in rows], "configured": True, "warning": None}

    @app.get("/api/notes/{note_id}")
    async def note(note_id: str, _: None = Depends(require_auth)) -> dict:
        vault = get_vault()
        try:
            row = vault.get(note_id)
        except VaultError as exc:
            raise vault_http_exception(exc) from exc
        if not row:
            raise HTTPException(status_code=404, detail="note not found")
        return {"note": serialize_note(row)}

    @app.patch("/api/notes/{note_id}")
    async def update_note(note_id: str, payload: NotePatch, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        category = payload.category
        if category is None and payload.category_id is not None:
            category_row = session.get(Category, payload.category_id) if payload.category_id else None
            category = category_row.slug if category_row else "inbox"
        try:
            row = get_vault().update(
                note_id,
                title=payload.title,
                body_md=payload.body_md,
                category=category,
                tags=payload.tags,
                archived=payload.archived,
            )
        except VaultError as exc:
            raise vault_http_exception(exc) from exc
        refresh_notes_tile(session)
        return {"note": serialize_note(row)}

    @app.post("/api/notes/{note_id}/archive")
    async def archive_note(note_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        try:
            row = get_vault().archive(note_id)
        except VaultError as exc:
            raise vault_http_exception(exc) from exc
        refresh_notes_tile(session)
        return {"note": serialize_note(row)}

    @app.post("/api/notes/{note_id}/merge")
    async def merge_note(note_id: str, payload: NoteMergeIn, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        try:
            result = get_vault().merge(note_id, payload.target_note_id)
        except VaultError as exc:
            raise vault_http_exception(exc) from exc
        refresh_notes_tile(session)
        return {"note": serialize_note(result["note"]), "archived_note": serialize_note(result["archived_note"])}

    @app.get("/api/jobs")
    async def jobs(
        _: None = Depends(require_auth),
        session: Session = Depends(get_session),
        limit: int = Query(default=50, ge=1, le=500),
        profile_id: str | None = Query(default=None, max_length=80),
    ) -> dict:
        statement = select(Job)
        if profile_id:
            statement = statement.where(Job.profile_id == profile_id)
        rows = session.scalars(statement.order_by(Job.started_at.desc().nullslast()).limit(limit)).all()
        profiles_by_id = profile_map(session)
        return {"jobs": [serialize_job(job, profiles_by_id.get(job.profile_id or "")) for job in rows]}

    @app.get("/api/jobs/{job_id}")
    async def job(job_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = session.get(Job, job_id)
        if not row:
            raise HTTPException(status_code=404, detail="job not found")
        profile = session.get(AgentProfile, row.profile_id) if row.profile_id else None
        return {"job": serialize_job(row, profile)}

    @app.get("/api/jobs/{job_id}/timeline")
    async def job_timeline(job_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = session.get(Job, job_id)
        if not row:
            raise HTTPException(status_code=404, detail="job not found")
        events = session.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.ts, JobEvent.id)).all()
        page = session.get(Page, row.page_id) if row.page_id else None
        approvals = session.scalars(select(Approval).where(Approval.job_id == job_id)).all()
        clarifications = session.scalars(select(Clarification).where(Clarification.job_id == job_id).order_by(Clarification.created_at, Clarification.id)).all()
        return {
            "job": serialize_job(row, session.get(AgentProfile, row.profile_id) if row.profile_id else None),
            "events": [serialize_event(event) for event in events],
            "page": serialize_page(page) if page else None,
            "approvals": [serialize_approval(approval) for approval in approvals],
            "clarifications": [serialize_clarification(clarification) for clarification in clarifications],
        }

    @app.get("/api/jobs/{job_id}/diagnostics")
    async def job_diagnostics(job_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = session.get(Job, job_id)
        if not row:
            raise HTTPException(status_code=404, detail="job not found")
        events = session.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.ts, JobEvent.id)).all()
        page = session.get(Page, row.page_id) if row.page_id else None
        approvals = session.scalars(select(Approval).where(Approval.job_id == job_id)).all()
        clarifications = session.scalars(select(Clarification).where(Clarification.job_id == job_id).order_by(Clarification.created_at, Clarification.id)).all()
        return {
            "job": serialize_job(row, session.get(AgentProfile, row.profile_id) if row.profile_id else None),
            "events": [serialize_event(event) for event in events],
            "page": serialize_page_summary(page) if page else None,
            "approvals": [serialize_approval(approval) for approval in approvals],
            "clarifications": [serialize_clarification(clarification) for clarification in clarifications],
            "environment": {
                "agent_configured": bool(os.getenv("AGENT_CMD")),
                "database": database_kind(os.getenv("DATABASE_URL", "sqlite:///./hermes-home.db")),
                "todos": vikunja_status(),
            },
        }

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> Response:
        row = session.get(Job, job_id)
        if not row:
            raise HTTPException(status_code=404, detail="job not found")
        events = session.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.ts)).all()
        body = "".join(format_sse(event) for event in events)
        return Response(content=body, media_type="text/event-stream")

    @app.get("/api/jobs/{job_id}/stream")
    async def job_stream(job_id: str, _: None = Depends(require_auth)) -> StreamingResponse:
        with session_factory() as session:
            if not session.get(Job, job_id):
                raise HTTPException(status_code=404, detail="job not found")
        return StreamingResponse(stream_job_events(session_factory, job_id), media_type="text/event-stream")

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel(job_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = session.get(Job, job_id)
        if not row:
            raise HTTPException(status_code=404, detail="job not found")
        return cancel_job(session, row)

    @app.post("/api/jobs/{job_id}/retry")
    async def retry(
        job_id: str,
        _: None = Depends(require_auth),
        session: Session = Depends(get_session),
    ) -> dict:
        row = session.get(Job, job_id)
        if not row:
            raise HTTPException(status_code=404, detail="job not found")
        next_job = create_job(session, row.command, profile_id=row.profile_id)
        next_job_id = next_job.id
        session.commit()
        start_agent_job(session_factory, next_job_id)
        return {"job_id": next_job_id}

    @app.get("/api/clarifications/{clarification_id}")
    async def clarification(clarification_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = session.get(Clarification, clarification_id)
        if not row:
            raise HTTPException(status_code=404, detail="clarification not found")
        job = session.get(Job, row.job_id)
        return {
            "clarification": serialize_clarification(row),
            "job": serialize_job(job, session.get(AgentProfile, job.profile_id) if job and job.profile_id else None) if job else None,
        }

    @app.post("/api/clarifications/{clarification_id}/answer")
    async def answer_clarification(
        clarification_id: str,
        payload: ClarificationAnswerIn,
        _: None = Depends(require_auth),
        session: Session = Depends(get_session),
    ) -> dict:
        answer = payload.answer.strip()
        if not answer:
            raise HTTPException(status_code=422, detail="answer must not be blank")
        row = session.get(Clarification, clarification_id)
        if not row:
            raise HTTPException(status_code=404, detail="clarification not found")
        source_job = session.get(Job, row.job_id)
        if not source_job:
            raise HTTPException(status_code=404, detail="source job not found")
        if row.status == "answered" and row.follow_up_job_id:
            follow_up = session.get(Job, row.follow_up_job_id)
            return {
                "job_id": row.follow_up_job_id,
                "clarification": serialize_clarification(row),
                "job": serialize_job(follow_up, session.get(AgentProfile, follow_up.profile_id) if follow_up and follow_up.profile_id else None) if follow_up else None,
                "idempotent_replay": True,
            }
        follow_up = create_job(session, clarification_follow_up_command(source_job, row, answer), profile_id=source_job.profile_id)
        row.answer = answer
        row.status = "answered"
        row.answered_at = utcnow()
        row.follow_up_job_id = follow_up.id
        session.commit()
        start_agent_job(session_factory, follow_up.id)
        return {
            "job_id": follow_up.id,
            "clarification": serialize_clarification(row),
            "job": serialize_job(follow_up, session.get(AgentProfile, follow_up.profile_id) if follow_up.profile_id else None),
        }

    @app.get("/api/pages/{page_id}")
    async def page(page_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = session.get(Page, page_id)
        if not row:
            raise HTTPException(status_code=404, detail="page not found")
        return {"page": serialize_page(row)}

    @app.get("/api/pages")
    async def pages(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        rows = session.scalars(select(Page).order_by(Page.pinned_at.desc().nullslast(), Page.created_at.desc()).limit(50)).all()
        return {"pages": [serialize_page(row) for row in rows]}

    @app.post("/api/pages/{page_id}/pin")
    async def pin_page(page_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = session.get(Page, page_id)
        if not row:
            raise HTTPException(status_code=404, detail="page not found")
        row.pinned_at = utcnow()
        return {"page": serialize_page(row)}

    @app.post("/api/pages/{page_id}/unpin")
    async def unpin_page(page_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = session.get(Page, page_id)
        if not row:
            raise HTTPException(status_code=404, detail="page not found")
        row.pinned_at = None
        return {"page": serialize_page(row)}

    @app.get("/api/approvals")
    async def approvals(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        rows = session.scalars(select(Approval).order_by(Approval.status, Approval.expires_at.desc().nullslast())).all()
        return {"approvals": [serialize_approval(row) for row in rows]}

    @app.get("/api/approvals/{approval_id}")
    async def approval(approval_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = session.get(Approval, approval_id)
        if not row:
            raise HTTPException(status_code=404, detail="approval not found")
        job = session.get(Job, row.job_id) if row.job_id else None
        profile = session.get(AgentProfile, job.profile_id) if job and job.profile_id else None
        return {"approval": serialize_approval(row), "job": serialize_job(job, profile) if job else None}

    @app.post("/api/approvals/{approval_id}/approve")
    async def approve_approval(approval_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        result = handle_action(session, "approvals.approve", {"approval_id": approval_id})
        if not result.get("ok"):
            session.commit()
            raise HTTPException(status_code=400, detail=result.get("error", "approval failed"))
        return result

    @app.post("/api/approvals/{approval_id}/reject")
    async def reject_approval(approval_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        result = handle_action(session, "approvals.reject", {"approval_id": approval_id})
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "approval failed"))
        return result

    @app.post("/api/command")
    async def command(
        payload: CommandIn,
        _: None = Depends(require_auth),
        session: Session = Depends(get_session),
    ) -> dict:
        profile_id = resolve_profile_id(session, payload.profile_id)
        row = create_job(session, payload.text, profile_id=profile_id)
        job_id = row.id
        # Commit before starting the agent so the polling UI can immediately see
        # the queued job and the background session can load it independently.
        session.commit()
        start_agent_job(session_factory, job_id)
        return {"job_id": job_id}

    @app.get("/api/actions")
    async def action_registry(_: None = Depends(require_auth)) -> dict:
        return {"actions": list(ACTION_REGISTRY.values())}

    @app.get("/api/action-runs")
    async def action_runs(
        _: None = Depends(require_auth),
        session: Session = Depends(get_session),
        action: str | None = Query(default=None, max_length=120),
        status: str | None = Query(default=None, max_length=40),
        source_job_id: str | None = Query(default=None, max_length=80),
        source_page_id: str | None = Query(default=None, max_length=80),
        limit: int = Query(default=100, ge=1, le=250),
    ) -> dict:
        statement = select(ActionRun)
        if action:
            statement = statement.where(ActionRun.action == action)
        if status:
            statement = statement.where(ActionRun.status == status)
        if source_job_id:
            statement = statement.where(ActionRun.source_job_id == source_job_id)
        if source_page_id:
            statement = statement.where(ActionRun.source_page_id == source_page_id)
        rows = session.scalars(statement.order_by(ActionRun.created_at.desc()).limit(limit)).all()
        return {"action_runs": [serialize_action_run(row) for row in rows]}

    @app.get("/api/action-runs/{action_run_id}")
    async def action_run(action_run_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = session.get(ActionRun, action_run_id)
        if not row:
            raise HTTPException(status_code=404, detail="action run not found")
        return {"action_run": serialize_action_run(row)}

    @app.post("/api/actions")
    async def actions(payload: ActionIn, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        if payload.idempotency_key:
            existing = session.scalar(select(ActionRun).where(ActionRun.idempotency_key == payload.idempotency_key))
            if existing:
                if existing.status == "failed":
                    raise HTTPException(status_code=400, detail=existing.error or "action failed")
                return {**existing.result, "idempotent_replay": True}
            action_run = ActionRun(
                idempotency_key=payload.idempotency_key,
                action=payload.action,
                payload=payload.payload,
                source_job_id=optional_payload_id(payload.payload, "job_id"),
                source_page_id=optional_payload_id(payload.payload, "page_id"),
            )
            session.add(action_run)
            session.flush()
        else:
            action_run = None
        result = handle_action(session, payload.action, payload.payload)
        if action_run:
            action_run.status = "done" if result.get("ok") else "failed"
            action_run.result = result
            action_run.error = None if result.get("ok") else str(result.get("error", "action failed"))
        if not result.get("ok"):
            session.commit()
            raise HTTPException(status_code=400, detail=result.get("error", "action failed"))
        return result

    @app.get("/api/connectors")
    async def connectors(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        return {"connectors": connector_status(session), "history": connector_history(session)}

    @app.post("/api/connectors/sync")
    async def sync_connectors(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        result = sync_all(session)
        return {"ok": True, "result": result, "connectors": connector_status(session), "history": connector_history(session)}

    @app.get("/api/calendar")
    async def calendar(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        rows = session.scalars(select(CalendarEvent).order_by(CalendarEvent.starts_at.asc().nullslast(), CalendarEvent.created_at.desc()).limit(100)).all()
        connectors = connector_status(session)
        return {
            "configured": True,
            "adapter": "local.calendar_events",
            "connector": connectors["calendar"],
            "write_policy": "approval_gated",
            "events": [serialize_calendar_event(row) for row in rows],
        }

    @app.get("/api/channels")
    async def channels(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        rows = session.scalars(select(ChannelMessage).order_by(ChannelMessage.received_at.desc()).limit(100)).all()
        connectors = connector_status(session)
        return {
            "configured": connectors["channels"]["configured"],
            "connectors": [connectors["channels"]] if connectors["channels"]["configured"] else [],
            "messages": [serialize_channel_message(row) for row in rows],
        }

    @app.get("/api/spend")
    async def spend(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        rows = session.scalars(select(SpendItem).order_by(SpendItem.spent_at.desc()).limit(100)).all()
        total_cents = sum(row.amount_cents for row in rows)
        connectors = connector_status(session)
        return {
            "configured": connectors["spend"]["configured"],
            "connector": connectors["spend"],
            "currency": "USD",
            "total_cents": total_cents,
            "items": [serialize_spend_item(row) for row in rows],
        }

    @app.get("/api/codex-runs")
    async def codex_runs(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        rows = session.scalars(select(CodexRun).order_by(CodexRun.started_at.desc().nullslast(), CodexRun.id.desc()).limit(50)).all()
        return {"codex_runs": [serialize_codex_run(row) for row in rows]}

    @app.get("/api/codex")
    async def codex_state(_: None = Depends(require_auth)) -> dict:
        workdir = codex_web_workdir()
        return {
            "available": codex_available(),
            "enabled": codex_enabled(),
            "binary_available": codex_binary_available(),
            "workdir": str(workdir),
            "mode": "dangerously-bypass-approvals-and-sandbox",
            "effort": default_codex_effort(),
            "effort_options": list(CODEX_EFFORT_LEVELS),
            "requires_confirmation": True,
            "disabled_reason": None if codex_enabled() else codex_disabled_reason(),
            "dirty": bool(git_status_short(workdir)),
            "status_short": git_status_short(workdir),
            "diff_stat": git_diff_stat(workdir),
        }

    @app.get("/api/codex-runs/{run_id}")
    async def codex_run(run_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = session.get(CodexRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="codex run not found")
        return {"codex_run": serialize_codex_run(row)}

    @app.post("/api/codex-runs/{run_id}/cancel")
    async def cancel_codex_run(run_id: str, _: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        row = session.get(CodexRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="codex run not found")
        if row.status in {"done", "failed", "cancelled"}:
            return {"codex_run": serialize_codex_run(row)}
        row.cancel_requested = True
        if row.status == "queued":
            row.status = "cancelled"
            row.error = "cancelled by user"
            row.finished_at = utcnow()
        return {"codex_run": serialize_codex_run(row)}

    @app.post("/api/codex-runs")
    async def create_codex_run(
        payload: CodexRunIn,
        _: None = Depends(require_auth),
        session: Session = Depends(get_session),
    ) -> dict:
        if not codex_enabled():
            raise HTTPException(status_code=403, detail=codex_disabled_reason())
        if not payload.confirm_dangerous_mode:
            raise HTTPException(status_code=400, detail="codex dangerous mode must be explicitly confirmed")
        if not codex_binary_available():
            raise HTTPException(status_code=503, detail="codex binary is not available")
        workdir = codex_web_workdir()
        command = codex_command(payload.prompt, workdir, payload.effort)
        row = CodexRun(prompt=payload.prompt.strip(), effort=payload.effort, workdir=str(workdir), command=command, status="queued")
        session.add(row)
        session.flush()
        run_id = row.id
        session.commit()
        threading.Thread(target=execute_codex_run, args=(session_factory, run_id), daemon=True).start()
        return {"codex_run": serialize_codex_run(row)}

    @app.get("/api/deployment/self-check")
    async def deployment_self_check(
        request: Request,
        _: None = Depends(require_auth),
        session: Session = Depends(get_session),
    ) -> dict:
        return deployment_self_check_payload(request, session, app.state.startup_recovery)

    @app.get("/api/vitals")
    async def vitals(_: None = Depends(require_auth), session: Session = Depends(get_session)) -> dict:
        status_counts = {
            status: count
            for status, count in session.execute(select(Job.status, func.count()).group_by(Job.status)).all()
        }
        return {
            "session": {
                "agent_configured": bool(os.getenv("AGENT_CMD")),
                "database": database_kind(os.getenv("DATABASE_URL", "sqlite:///./hermes-home.db")),
                "connectors": connector_status(session),
                "connector_history": connector_history(session, limit=10),
            },
            "counts": {
                "jobs": session.query(Job).count(),
                "job_status_rows": status_counts,
                "todos_open": session.query(Todo).filter(Todo.provider == "vikunja", Todo.external_id.is_not(None), Todo.status == "open").count(),
                "notes": vault_note_count(),
                "approvals_pending": session.query(Approval).filter(Approval.status == "pending").count(),
                "calendar_events": session.query(CalendarEvent).count(),
                "action_runs": session.query(ActionRun).count(),
                "connector_sync_runs": session.query(ConnectorSyncRun).count(),
                "codex_runs": session.query(CodexRun).count(),
            },
        }

    return app


async def require_auth(authorization: str | None = Header(default=None)) -> None:
    token = home_api_token()
    if authorization is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    prefix = "Bearer "
    if not authorization.startswith(prefix) or authorization[len(prefix):] != token:
        raise HTTPException(status_code=401, detail="invalid bearer token")


def home_api_token() -> str:
    return os.getenv("HOME_API_TOKEN", "dev-token")


def warn_on_insecure_deployment_defaults() -> None:
    checks = deployment_static_checks()
    failures = [check for check in checks if check["status"] == "fail"]
    if failures:
        message = "; ".join(f"{check['code']}: {check['message']}" for check in failures)
        if truthy_env("HERMES_STRICT_DEPLOYMENT_CHECKS"):
            raise RuntimeError(message)
        warnings.warn(message, RuntimeWarning, stacklevel=2)


def deployment_self_check_payload(request: Request, session: Session, startup_recovery: dict[str, int] | None = None) -> dict[str, Any]:
    authorization = request.headers.get("authorization", "")
    scheme = authorization.split(" ", 1)[0].lower() if authorization else None
    checks = [
        *deployment_static_checks(request),
        check(
            "request_authorization",
            "pass" if scheme == "bearer" else "warn",
            "upstream app received a bearer Authorization header"
            if scheme == "bearer"
            else "upstream app did not receive a bearer Authorization header; verify nginx proxy_set_header Authorization injection",
        ),
        check(
            "database",
            "pass" if database_kind(os.getenv("DATABASE_URL", "sqlite:///./hermes-home.db")) in {"sqlite", "postgres"} else "warn",
            f"database kind is {database_kind(os.getenv('DATABASE_URL', 'sqlite:///./hermes-home.db'))}",
        ),
        check(
            "agent",
            "pass" if os.getenv("AGENT_CMD") else "warn",
            "AGENT_CMD is configured" if os.getenv("AGENT_CMD") else "AGENT_CMD is empty; fallback agent is active",
        ),
        check(
            "connectors",
            "pass" if any(item["configured"] for item in connector_status(session).values()) else "warn",
            "at least one local connector is configured"
            if any(item["configured"] for item in connector_status(session).values())
            else "no local connector JSON sources are configured",
        ),
    ]
    return {
        "ok": all(item["status"] != "fail" for item in checks),
        "checks": checks,
        "request": {
            "host": request.headers.get("host"),
            "authorization_scheme": scheme,
        },
        "startup_recovery": startup_recovery or {"jobs": 0, "codex_runs": 0},
    }


def deployment_static_checks(request: Request | None = None) -> list[dict[str, str]]:
    default_token = home_api_token() in {"", "dev-token", "change-me", "changeme"}
    local_context = is_local_development_context(request)
    codex_state = codex_enabled()
    return [
        check(
            "home_api_token",
            "fail" if default_token and not local_context else "warn" if default_token else "pass",
            "HOME_API_TOKEN is still a development/default value"
            if default_token
            else "HOME_API_TOKEN is set to a non-default value",
        ),
        check(
            "codex_execution",
            "warn" if deployment_environment_is_production() and codex_state else "pass",
            "Codex execution is enabled in a production environment"
            if deployment_environment_is_production() and codex_state
            else f"Codex execution is {'enabled' if codex_state else 'disabled'}",
        ),
        check(
            "vite_api_base",
            "warn" if deployment_environment_is_production() and os.getenv("VITE_API_BASE", "").strip() else "pass",
            "VITE_API_BASE is set; same-origin nginx deployments should leave it empty"
            if os.getenv("VITE_API_BASE", "").strip()
            else "VITE_API_BASE is empty for same-origin API calls",
        ),
    ]


def check(code: str, status: str, message: str) -> dict[str, str]:
    return {"code": code, "status": status, "message": message}


def deployment_environment_is_production() -> bool:
    value = (
        os.getenv("HERMES_ENV")
        or os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("ENV")
        or ""
    ).strip().lower()
    return value in {"prod", "production"}


def is_local_development_context(request: Request | None = None) -> bool:
    if deployment_environment_is_production():
        return False
    if request is not None:
        host = (request.headers.get("host") or "").split(":", 1)[0].strip("[]")
        if host and not is_loopback_host(host):
            return False
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip()
    if public_base_url and not url_has_loopback_host(public_base_url):
        return False
    server_host = os.getenv("SERVER_HOST", "").strip()
    if server_host and server_host not in {"0.0.0.0", "::"} and not is_loopback_host(server_host.strip("[]")):
        return False
    return True


def url_has_loopback_host(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return False
    return is_loopback_host(host)


def is_loopback_host(hostname: str) -> bool:
    return hostname in {"localhost", "0.0.0.0", "::1"} or hostname.startswith("127.")


def truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def falsy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"0", "false", "no", "off"}


def start_agent_job(session_factory: sessionmaker[Session], job_id: str) -> None:
    threading.Thread(target=run_agent_job, args=(session_factory, job_id), daemon=True).start()


def run_agent_job(session_factory: sessionmaker[Session], job_id: str) -> None:
    session = session_factory()
    try:
        row = session.get(Job, job_id)
        if not row:
            return
        if row.status == "cancelled":
            return
        invoke_agent(session, row)
        session.commit()
    except Exception as exc:
        session.rollback()
        row = session.get(Job, job_id)
        if row:
            row.status = "failed"
            row.error = str(exc)
            session.commit()
    finally:
        session.close()


def execute_codex_run(session_factory: sessionmaker[Session], run_id: str) -> None:
    session = session_factory()
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    try:
        row = session.get(CodexRun, run_id)
        if not row:
            return
        if row.cancel_requested or row.status == "cancelled":
            row.status = "cancelled"
            row.error = "cancelled by user"
            row.finished_at = utcnow()
            session.commit()
            return
        workdir = Path(row.workdir)
        row.status = "running"
        row.started_at = utcnow()
        row.before_status = git_status_short(workdir)
        session.commit()
        if not workdir.exists():
            row.status = "failed"
            row.error = f"workdir does not exist: {workdir}"
            row.finished_at = utcnow()
            session.commit()
            return
        timeout = int(os.getenv("CODEX_RUN_TIMEOUT_SECONDS", "1800"))
        stdout_path = Path(tempfile.gettempdir()) / f"hermes-codex-{run_id}.out"
        stderr_path = Path(tempfile.gettempdir()) / f"hermes-codex-{run_id}.err"
        with stdout_path.open("w+", encoding="utf-8") as stdout_file, stderr_path.open("w+", encoding="utf-8") as stderr_file:
            process = subprocess.Popen(
                row.command,
                cwd=str(workdir),
                env={**os.environ, "TERM": os.getenv("TERM", "dumb")},
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                start_new_session=True,
            )
            row.process_id = process.pid
            session.commit()
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                session.expire(row)
                row = session.get(CodexRun, run_id)
                if not row:
                    terminate_process(process)
                    return
                if row.cancel_requested:
                    terminate_process(process)
                    row.status = "cancelled"
                    row.error = "cancelled by user"
                    break
                if time.monotonic() >= deadline:
                    process.kill()
                    process.wait()
                    row.status = "failed"
                    row.error = f"codex timed out after {timeout} seconds"
                    break
                session.commit()
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
            stdout_file.flush()
            stderr_file.flush()

        stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path else ""
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path else ""
        if row.status not in {"cancelled", "failed"}:
            row.status = "done" if process.returncode == 0 else "failed"
            row.error = None if process.returncode == 0 else (stderr.strip() or stdout.strip() or "codex exited with an error")
        row.exit_code = process.returncode
        row.stdout_tail = tail_text(stdout)
        row.stderr_tail = tail_text(stderr)
        row.after_status = git_status_short(workdir)
        row.diff_stat = git_diff_stat(workdir)
        row.process_id = None
        row.finished_at = utcnow()
        session.commit()
    except Exception as exc:
        session.rollback()
        row = session.get(CodexRun, run_id)
        if row:
            row.status = "failed"
            row.error = str(exc)
            row.after_status = git_status_short(Path(row.workdir))
            row.diff_stat = git_diff_stat(Path(row.workdir))
            row.process_id = None
            row.finished_at = utcnow()
            session.commit()
    finally:
        for path in (stdout_path, stderr_path):
            if path:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        session.close()


def recover_interrupted_codex_runs(session: Session) -> int:
    rows = session.scalars(select(CodexRun).where(CodexRun.status.in_(["queued", "running"]))).all()
    if not rows:
        return 0
    for run in rows:
        previous = run.status
        run.status = "failed"
        run.error = f"marked failed during startup recovery from stale {previous} state"
        run.process_id = None
        run.finished_at = utcnow()
    return len(rows)


def terminate_process(process: subprocess.Popen) -> None:
    try:
        if process.pid and hasattr(os, "killpg"):
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            if process.pid and hasattr(os, "killpg"):
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            return
        process.wait()


def codex_web_workdir() -> Path:
    return Path(os.getenv("CODEX_WEB_WORKDIR", str(Path(__file__).resolve().parents[2] / "web"))).resolve()


def codex_binary() -> str:
    return os.getenv("CODEX_BIN") or shutil.which("codex") or "codex"


def codex_enabled() -> bool:
    if os.getenv("CODEX_ENABLED", "").strip():
        return truthy_env("CODEX_ENABLED") and not falsy_env("CODEX_ENABLED")
    return not deployment_environment_is_production()


def codex_disabled_reason() -> str:
    if codex_enabled():
        return ""
    return "codex execution is disabled; set CODEX_ENABLED=true only for trusted admin use"


def codex_binary_available() -> bool:
    return shutil.which(codex_binary()) is not None or Path(codex_binary()).exists()


def codex_available() -> bool:
    return codex_enabled() and codex_binary_available()



def default_codex_effort() -> CodexEffort:
    effort = os.getenv("CODEX_DEFAULT_EFFORT", "xhigh").strip().lower()
    if effort in CODEX_EFFORT_LEVELS:
        return cast(CodexEffort, effort)
    return "xhigh"


def git_status_short(workdir: Path) -> str:
    return run_git_summary(workdir, ["status", "--short"])


def git_diff_stat(workdir: Path) -> str:
    return run_git_summary(workdir, ["diff", "--stat"])


def run_git_summary(workdir: Path, args: list[str]) -> str:
    if not workdir.exists():
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(workdir), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return result.stderr.strip()
    return result.stdout.strip()


def codex_command(prompt: str, workdir: Path, effort: CodexEffort) -> list[str]:
    return [
        codex_binary(),
        "exec",
        "-c",
        f"model_reasoning_effort={json.dumps(effort)}",
        "--dangerously-bypass-approvals-and-sandbox",
        "--color",
        "never",
        "-C",
        str(workdir),
        prompt.strip(),
    ]


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


def serialize_category(category: Category) -> dict:
    return {
        "id": category.id,
        "slug": category.slug,
        "name": category.name,
        "color": category.color,
        "created_by": category.created_by,
        "created_at": serialize_dt(category.created_at),
    }


def serialize_todo(todo: Todo) -> dict:
    return {
        "id": todo.id,
        "external_id": todo.external_id,
        "provider": todo.provider,
        "title": todo.title,
        "notes": todo.notes,
        "due_at": serialize_dt(todo.due_at),
        "scheduled_for": serialize_dt(todo.scheduled_for),
        "tags": todo.tags,
        "priority": todo.priority,
        "status": todo.status,
        "source": todo.source,
        "things_id": todo.things_id,
        "project_id": todo.project_id,
        "project": todo.project_title,
        "list": todo.project_title,
        "created_at": serialize_dt(todo.created_at),
        "updated_at": serialize_dt(todo.updated_at),
        "completed_at": serialize_dt(todo.completed_at),
    }


def serialize_vikunja_projects(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": str(project.get("id")), "title": str(project.get("title") or ""), "hex_color": str(project.get("hex_color") or "")}
        for project in projects
        if project.get("id") is not None
    ]


def serialize_vikunja_labels(labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": str(label.get("id")), "title": str(label.get("title") or ""), "hex_color": str(label.get("hex_color") or "")}
        for label in labels
        if label.get("id") is not None
    ]


def serialize_note(note: Note | dict[str, Any]) -> dict:
    if isinstance(note, dict):
        return {
            "id": note["id"],
            "title": note["title"],
            "body_md": note["body_md"],
            "category": note.get("category") or "inbox",
            "tags": note.get("tags") or [],
            "source_job_id": note.get("source_job_id"),
            "archived": bool(note.get("archived")),
            "created_at": note.get("created_at"),
            "updated_at": note.get("updated_at"),
        }
    return {
        "id": note.id,
        "category": "inbox",
        "tags": [],
        "title": note.title,
        "body_md": note.body_md,
        "source_job_id": note.source_job_id,
        "archived": note.archived,
        "created_at": serialize_dt(note.created_at),
        "updated_at": serialize_dt(note.updated_at),
    }


def serialize_job(job: Job, profile: AgentProfile | None = None) -> dict:
    emoji, summary = derive_history_meta(job.command, job.status)
    return {
        "id": job.id,
        "command": job.command,
        "status": job.status,
        "page_id": job.page_id,
        "error": job.error,
        "stdout_tail": job.stdout_tail,
        "stderr_tail": job.stderr_tail,
        "exit_code": job.exit_code,
        "emoji": job.emoji or emoji,
        "summary": job.summary or summary,
        "profile_id": job.profile_id,
        "profile": serialize_profile_summary(profile) if profile else None,
        "started_at": serialize_dt(job.started_at),
        "finished_at": serialize_dt(job.finished_at),
    }


def serialize_clarification(clarification: Clarification) -> dict:
    return {
        "id": clarification.id,
        "job_id": clarification.job_id,
        "question": clarification.question,
        "choices": clarification.choices or [],
        "draft": clarification.draft or {},
        "answer": clarification.answer,
        "status": clarification.status,
        "follow_up_job_id": clarification.follow_up_job_id,
        "created_at": serialize_dt(clarification.created_at),
        "answered_at": serialize_dt(clarification.answered_at),
    }


def clarification_follow_up_command(job: Job, clarification: Clarification, answer: str) -> str:
    draft_json = json.dumps(clarification.draft or {}, sort_keys=True)
    return "\n".join(
        [
            f"Original command: {job.command}",
            f"Clarification question: {clarification.question}",
            f"Clarification answer: {answer}",
            f"Draft interpretation: {draft_json}",
        ]
    )


def serialize_profile(profile: AgentProfile) -> dict:
    return {
        "id": profile.id,
        "slug": profile.slug,
        "name": profile.name,
        "emoji": profile.emoji,
        "color": profile.color,
        "persona": profile.persona,
        "is_default": profile.is_default,
        "created_at": serialize_dt(profile.created_at),
        "updated_at": serialize_dt(profile.updated_at),
    }


def serialize_profile_summary(profile: AgentProfile) -> dict:
    return {"id": profile.id, "name": profile.name, "emoji": profile.emoji, "color": profile.color}


def default_profile(session: Session) -> AgentProfile | None:
    return session.scalar(select(AgentProfile).where(AgentProfile.is_default.is_(True)).limit(1)) or session.scalar(select(AgentProfile).order_by(AgentProfile.created_at).limit(1))


def resolve_profile_id(session: Session, profile_id: str | None) -> str | None:
    if profile_id:
        if not session.get(AgentProfile, profile_id):
            raise HTTPException(status_code=400, detail="profile not found")
        return profile_id
    profile = default_profile(session)
    return profile.id if profile else None


def clear_default_profiles(session: Session) -> None:
    for profile in session.scalars(select(AgentProfile).where(AgentProfile.is_default.is_(True))).all():
        profile.is_default = False


def unique_profile_slug(session: Session, name: str, exclude_id: str | None = None) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "profile"
    slug = base
    suffix = 2
    while True:
        existing = session.scalar(select(AgentProfile).where(AgentProfile.slug == slug).limit(1))
        if not existing or existing.id == exclude_id:
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1


def profile_map(session: Session) -> dict[str, AgentProfile]:
    return {profile.id: profile for profile in session.scalars(select(AgentProfile)).all()}


def serialize_page(page: Page) -> dict:
    return {
        "id": page.id,
        "job_id": page.job_id,
        "title": page.title,
        "html": page.html,
        "provenance": page.provenance,
        "created_at": serialize_dt(page.created_at),
        "pinned_at": serialize_dt(page.pinned_at),
    }


def serialize_page_summary(page: Page) -> dict:
    return {
        "id": page.id,
        "job_id": page.job_id,
        "title": page.title,
        "provenance": page.provenance,
        "created_at": serialize_dt(page.created_at),
        "pinned_at": serialize_dt(page.pinned_at),
        "html_bytes": len(page.html.encode("utf-8")),
    }


def serialize_approval(approval: Approval) -> dict:
    return {
        "id": approval.id,
        "job_id": approval.job_id,
        "action": approval.action,
        "scope": approval.scope,
        "status": approval.status,
        "expires_at": serialize_dt(approval.expires_at),
        "decided_at": serialize_dt(approval.decided_at),
        "result": approval.result,
        "error": approval.error,
    }


def serialize_event(event: JobEvent) -> dict:
    return {
        "id": event.id,
        "job_id": event.job_id,
        "ts": serialize_dt(event.ts),
        "kind": event.kind,
        "text": event.text,
    }


def serialize_action_run(action_run: ActionRun) -> dict:
    return {
        "id": action_run.id,
        "idempotency_key": action_run.idempotency_key,
        "action": action_run.action,
        "payload": action_run.payload,
        "source_job_id": action_run.source_job_id,
        "source_page_id": action_run.source_page_id,
        "status": action_run.status,
        "result": action_run.result,
        "error": action_run.error,
        "summary": summarize_action_run(action_run),
        "created_at": serialize_dt(action_run.created_at),
    }


def summarize_action_run(action_run: ActionRun) -> str:
    if action_run.error:
        return action_run.error
    result = action_run.result or {}
    nested = result.get("result") if isinstance(result.get("result"), dict) else {}
    if action_run.action.startswith("todos."):
        status = result.get("status")
        todo_id = result.get("todo_id")
        return f"{action_run.action} {status or action_run.status}{f' · {todo_id}' if todo_id else ''}"
    if action_run.action == "approvals.request":
        return f"requested {result.get('approval_id', 'approval')}"
    if action_run.action in {"approvals.approve", "approvals.reject"}:
        message = nested.get("message") if isinstance(nested, dict) else None
        return f"{result.get('status', action_run.status)}{f' · {message}' if message else ''}"
    if "message" in result:
        return str(result["message"])
    return action_run.status


def serialize_calendar_event(event: CalendarEvent) -> dict:
    return {
        "id": event.id,
        "calendar_id": event.calendar_id,
        "summary": event.summary,
        "starts_at": serialize_dt(event.starts_at),
        "ends_at": serialize_dt(event.ends_at),
        "status": event.status,
        "source_approval_id": event.source_approval_id,
        "created_at": serialize_dt(event.created_at),
        "updated_at": serialize_dt(event.updated_at),
    }


def serialize_channel_message(message: ChannelMessage) -> dict:
    return {
        "id": message.id,
        "channel": message.channel,
        "sender": message.sender,
        "subject": message.subject,
        "body": message.body,
        "status": message.status,
        "received_at": serialize_dt(message.received_at),
    }


def serialize_spend_item(item: SpendItem) -> dict:
    return {
        "id": item.id,
        "merchant": item.merchant,
        "amount_cents": item.amount_cents,
        "currency": item.currency,
        "category": item.category,
        "spent_at": serialize_dt(item.spent_at),
    }


def serialize_codex_run(run: CodexRun) -> dict:
    return {
        "id": run.id,
        "prompt": run.prompt,
        "effort": run.effort,
        "workdir": run.workdir,
        "command": run.command,
        "status": run.status,
        "process_id": run.process_id,
        "cancel_requested": run.cancel_requested,
        "before_status": run.before_status,
        "after_status": run.after_status,
        "diff_stat": run.diff_stat,
        "stdout_tail": run.stdout_tail,
        "stderr_tail": run.stderr_tail,
        "exit_code": run.exit_code,
        "error": run.error,
        "started_at": serialize_dt(run.started_at),
        "finished_at": serialize_dt(run.finished_at),
    }


def format_sse(event: JobEvent) -> str:
    payload = {"id": event.id, "ts": serialize_dt(event.ts), "kind": event.kind, "text": event.text}
    return f"id: {event.id}\nevent: {event.kind}\ndata: {json.dumps(payload)}\n\n"


async def stream_job_events(session_factory: sessionmaker[Session], job_id: str) -> AsyncIterator[str]:
    seen: set[str] = set()
    terminal = {"done", "failed", "needs_approval", "needs_clarification", "cancelled"}
    while True:
        with session_factory() as session:
            job = session.get(Job, job_id)
            if not job:
                return
            events = session.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.ts, JobEvent.id)).all()
            for event in events:
                if event.id in seen:
                    continue
                seen.add(event.id)
                yield format_sse(event)
            if job.status in terminal:
                return
        await asyncio.sleep(0.5)


def database_kind(url: str) -> str:
    if url.startswith("postgres"):
        return "postgres"
    if url.startswith("sqlite"):
        return "sqlite"
    return "unknown"


def optional_payload_id(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


app = create_app()
