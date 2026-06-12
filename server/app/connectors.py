from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.orm import Session

from .models import CalendarEvent, ChannelMessage, ConnectorSyncRun, SpendItem, utcnow


CONNECTORS = {
    "calendar": {"env": "HERMES_CALENDAR_EVENTS_JSON", "adapter": "json_file"},
    "channels": {"env": "HERMES_CHANNEL_MESSAGES_JSON", "adapter": "json_file"},
    "spend": {"env": "HERMES_SPEND_ITEMS_JSON", "adapter": "json_file"},
}


def connector_status(session: Session | None = None) -> dict[str, dict[str, Any]]:
    return {name: status_for(name, config["env"], config["adapter"], session) for name, config in CONNECTORS.items()}


def sync_all(session: Session) -> dict[str, Any]:
    return {
        "calendar": tracked_sync(session, "calendar", "HERMES_CALENDAR_EVENTS_JSON", sync_calendar),
        "channels": tracked_sync(session, "channels", "HERMES_CHANNEL_MESSAGES_JSON", sync_channels),
        "spend": tracked_sync(session, "spend", "HERMES_SPEND_ITEMS_JSON", sync_spend),
    }


def tracked_sync(session: Session, connector: str, env_name: str, sync_fn: Any) -> dict[str, Any]:
    status = status_for(connector, env_name, "json_file", session=None)
    run = ConnectorSyncRun(
        connector=connector,
        adapter=status["adapter"],
        source=status["source"],
        status="running",
    )
    session.add(run)
    session.flush()
    if not status["configured"]:
        run.status = "skipped"
        run.imported = 0
        run.error = "connector is not configured"
        run.finished_at = utcnow()
        return serialize_sync_run(run)
    if not status["available"]:
        run.status = "error"
        run.imported = 0
        run.error = "configured source is not available"
        run.finished_at = utcnow()
        return serialize_sync_run(run)
    try:
        result = sync_fn(session)
    except Exception as exc:
        run.status = "error"
        run.imported = 0
        run.error = str(exc)
        run.finished_at = utcnow()
        return serialize_sync_run(run)
    run.status = "success"
    run.imported = int(result.get("imported", 0))
    run.error = None
    run.finished_at = utcnow()
    return serialize_sync_run(run)


def sync_calendar(session: Session) -> dict[str, Any]:
    rows = load_json_rows("HERMES_CALENDAR_EVENTS_JSON")
    imported = 0
    for row in rows:
        calendar_id = str(row.get("calendar_id", "primary"))
        summary = str(row.get("summary", "untitled event"))
        starts_at = parse_dt(row.get("starts_at"))
        event = session.scalar(
            select(CalendarEvent)
            .where(CalendarEvent.calendar_id == calendar_id)
            .where(CalendarEvent.summary == summary)
            .where(nullable_match(CalendarEvent.starts_at, starts_at))
            .limit(1)
        )
        if event is None:
            event = CalendarEvent(calendar_id=calendar_id, summary=summary, starts_at=starts_at)
            session.add(event)
        event.ends_at = parse_dt(row.get("ends_at"))
        event.status = str(row.get("status", "confirmed"))
        event.updated_at = utcnow()
        imported += 1
    return {"imported": imported}


def sync_channels(session: Session) -> dict[str, Any]:
    rows = load_json_rows("HERMES_CHANNEL_MESSAGES_JSON")
    imported = 0
    for row in rows:
        channel = str(row.get("channel", "inbox"))
        sender = optional_str(row.get("sender"))
        subject = str(row.get("subject", "untitled message"))
        body = str(row.get("body", ""))
        received_at = parse_dt(row.get("received_at"))
        statement = (
            select(ChannelMessage)
            .where(ChannelMessage.channel == channel)
            .where(nullable_match(ChannelMessage.sender, sender))
            .where(ChannelMessage.subject == subject)
        )
        if received_at is None:
            statement = statement.where(ChannelMessage.body == body)
        else:
            statement = statement.where(nullable_match(ChannelMessage.received_at, received_at))
        message = session.scalar(statement.limit(1))
        if message is None:
            message = ChannelMessage(channel=channel, sender=sender, subject=subject, received_at=received_at or utcnow())
            session.add(message)
        message.body = body
        message.status = str(row.get("status", "unread"))
        if received_at is not None:
            message.received_at = received_at
        imported += 1
    return {"imported": imported}


def sync_spend(session: Session) -> dict[str, Any]:
    rows = load_json_rows("HERMES_SPEND_ITEMS_JSON")
    imported = 0
    for row in rows:
        merchant = str(row.get("merchant", "unknown merchant"))
        amount_cents = int(row.get("amount_cents", 0))
        currency = str(row.get("currency", "USD"))
        category = optional_str(row.get("category"))
        spent_at = parse_dt(row.get("spent_at"))
        statement = (
            select(SpendItem)
            .where(SpendItem.merchant == merchant)
            .where(SpendItem.amount_cents == amount_cents)
            .where(SpendItem.currency == currency)
            .where(nullable_match(SpendItem.category, category))
        )
        if spent_at is not None:
            statement = statement.where(nullable_match(SpendItem.spent_at, spent_at))
        item = session.scalar(statement.limit(1))
        if item is None:
            item = SpendItem(merchant=merchant, amount_cents=amount_cents, currency=currency, category=category, spent_at=spent_at or utcnow())
            session.add(item)
        item.category = category
        if spent_at is not None:
            item.spent_at = spent_at
        imported += 1
    return {"imported": imported}


def nullable_match(column: Any, value: Any) -> ColumnElement[bool]:
    return column.is_(None) if value is None else column == value


def status_for(connector: str, env_name: str, adapter: str, session: Session | None) -> dict[str, Any]:
    raw = os.getenv(env_name, "")
    last_sync = last_sync_for(session, connector) if session else None
    if not raw:
        return {
            "configured": False,
            "source": None,
            "available": False,
            "adapter": adapter,
            "state": "not_configured",
            "last_sync": last_sync,
        }
    path = Path(raw).expanduser()
    return {
        "configured": True,
        "source": str(path),
        "available": path.exists(),
        "adapter": adapter,
        "state": "local_adapter" if path.exists() else "source_missing",
        "last_sync": last_sync,
    }


def connector_history(session: Session, limit: int = 20) -> list[dict[str, Any]]:
    rows = session.scalars(select(ConnectorSyncRun).order_by(desc(ConnectorSyncRun.started_at)).limit(limit)).all()
    return [serialize_sync_run(row) for row in rows]


def last_sync_for(session: Session | None, connector: str) -> dict[str, Any] | None:
    if session is None:
        return None
    row = session.scalar(
        select(ConnectorSyncRun)
        .where(ConnectorSyncRun.connector == connector)
        .order_by(desc(ConnectorSyncRun.started_at))
        .limit(1)
    )
    return serialize_sync_run(row) if row else None


def serialize_sync_run(run: ConnectorSyncRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "connector": run.connector,
        "adapter": run.adapter,
        "source": run.source,
        "status": run.status,
        "imported": run.imported,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def load_json_rows(env_name: str) -> list[dict[str, Any]]:
    raw = os.getenv(env_name, "")
    if not raw:
        return []
    path = Path(raw).expanduser()
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        payload = payload.get("items") or payload.get("events") or payload.get("messages") or []
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


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


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
