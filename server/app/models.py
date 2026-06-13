from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uuid_type() -> Uuid:
    return Uuid(as_uuid=False)


class Base(DeclarativeBase):
    pass


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(uuid_type(), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    color: Mapped[str] = mapped_column(String)
    created_by: Mapped[str] = mapped_column(String, default="seed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(uuid_type(), primary_key=True, default=new_id)
    category_id: Mapped[str | None] = mapped_column(uuid_type(), nullable=True)
    title: Mapped[str] = mapped_column(String)
    body_md: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    source_job_id: Mapped[str | None] = mapped_column(uuid_type(), nullable=True)
    archived: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[str] = mapped_column(uuid_type(), primary_key=True, default=new_id)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String, default="vikunja")
    title: Mapped[str] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")
    source: Mapped[str] = mapped_column(String, default="user")
    things_id: Mapped[str | None] = mapped_column(String, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True)
    project_title: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(uuid_type(), primary_key=True, default=new_id)
    command: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="queued")
    page_id: Mapped[str | None] = mapped_column(uuid_type(), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stdout_tail: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_tail: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    emoji: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_id: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    id: Mapped[str] = mapped_column(uuid_type(), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    emoji: Mapped[str] = mapped_column(String, default="🤖")
    color: Mapped[str] = mapped_column(String, default="#1BA1E2")
    persona: Mapped[str] = mapped_column(Text, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[str] = mapped_column(uuid_type(), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(uuid_type(), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String, default="step")
    text: Mapped[str] = mapped_column(Text)


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(uuid_type(), primary_key=True, default=new_id)
    job_id: Mapped[str | None] = mapped_column(uuid_type(), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String)
    html: Mapped[str] = mapped_column(Text)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Tile(Base):
    __tablename__ = "tiles"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    size: Mapped[str] = mapped_column(String)
    color: Mapped[str] = mapped_column(String)
    sort: Mapped[int] = mapped_column(Integer)
    front: Mapped[dict] = mapped_column(JSON, default=dict)
    back: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(uuid_type(), primary_key=True, default=new_id)
    job_id: Mapped[str | None] = mapped_column(uuid_type(), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String)
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="pending")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ActionRun(Base):
    __tablename__ = "action_runs"

    id: Mapped[str] = mapped_column(uuid_type(), primary_key=True, default=new_id)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    action: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    source_job_id: Mapped[str | None] = mapped_column(uuid_type(), nullable=True)
    source_page_id: Mapped[str | None] = mapped_column(uuid_type(), nullable=True)
    status: Mapped[str] = mapped_column(String, default="running")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[str] = mapped_column(uuid_type(), primary_key=True, default=new_id)
    calendar_id: Mapped[str] = mapped_column(String, default="primary")
    summary: Mapped[str] = mapped_column(String)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, default="confirmed")
    source_approval_id: Mapped[str | None] = mapped_column(uuid_type(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChannelMessage(Base):
    __tablename__ = "channel_messages"

    id: Mapped[str] = mapped_column(uuid_type(), primary_key=True, default=new_id)
    channel: Mapped[str] = mapped_column(String)
    sender: Mapped[str | None] = mapped_column(String, nullable=True)
    subject: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="unread")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SpendItem(Base):
    __tablename__ = "spend_items"

    id: Mapped[str] = mapped_column(uuid_type(), primary_key=True, default=new_id)
    merchant: Mapped[str] = mapped_column(String)
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String, default="USD")
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    spent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConnectorSyncRun(Base):
    __tablename__ = "connector_sync_runs"

    id: Mapped[str] = mapped_column(uuid_type(), primary_key=True, default=new_id)
    connector: Mapped[str] = mapped_column(String, index=True)
    adapter: Mapped[str] = mapped_column(String, default="json_file")
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="running")
    imported: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CodexRun(Base):
    __tablename__ = "codex_runs"

    id: Mapped[str] = mapped_column(uuid_type(), primary_key=True, default=new_id)
    prompt: Mapped[str] = mapped_column(Text)
    effort: Mapped[str] = mapped_column(String, default="xhigh")
    workdir: Mapped[str] = mapped_column(Text)
    command: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="queued")
    process_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    before_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_stat: Mapped[str | None] = mapped_column(Text, nullable=True)
    stdout_tail: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_tail: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CalendarSync(Base):
    __tablename__ = "calendar_sync"

    calendar_id: Mapped[str] = mapped_column(String, primary_key=True)
    sync_token: Mapped[str | None] = mapped_column(String, nullable=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
