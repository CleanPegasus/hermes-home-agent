from __future__ import annotations

import hashlib
import os
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .embeddings import cosine_similarity, embed_query, embed_texts, get_embedding_provider
from .models import IndexEntry, Job, Note, SavedItem, Todo, utcnow
from .vault import VaultStore


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def index_entry(
    session: Session,
    *,
    source_type: str,
    source_id: str,
    title: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> IndexEntry:
    digest = content_hash(f"{title}\n{content}")
    row = session.scalar(
        select(IndexEntry)
        .where(IndexEntry.source_type == source_type)
        .where(IndexEntry.source_id == source_id)
        .limit(1)
    )
    if row is None:
        row = IndexEntry(source_type=source_type, source_id=source_id)
        session.add(row)
    changed = row.content_hash != digest or row.embedding is None
    row.title = title[:500]
    row.content = content
    row.entry_metadata = metadata or {}
    row.indexed_at = utcnow()
    if changed:
        row.content_hash = digest
        provider = get_embedding_provider()
        if provider.configured():
            try:
                vectors = embed_texts([f"{title}\n{content}"[:8000]])
                row.embedding = vectors[0] if vectors else None
            except Exception:
                row.embedding = None
    session.flush()
    return row


def index_note(session: Session, note: dict[str, Any]) -> None:
    note_id = str(note.get("id") or "").strip()
    if not note_id:
        return
    index_entry(
        session,
        source_type="note",
        source_id=note_id,
        title=str(note.get("title") or "untitled note"),
        content=str(note.get("body_md") or ""),
        metadata={"category": note.get("category"), "tags": note.get("tags") or []},
    )


def index_job(session: Session, job: Job) -> None:
    parts = [job.command or ""]
    if job.summary:
        parts.append(job.summary)
    index_entry(
        session,
        source_type="job",
        source_id=job.id,
        title=(job.summary or job.command or "job")[:200],
        content="\n".join(p for p in parts if p),
        metadata={"status": job.status, "profile_id": job.profile_id},
    )


def index_todo(session: Session, todo: Todo) -> None:
    index_entry(
        session,
        source_type="todo",
        source_id=todo.id,
        title=todo.title,
        content="\n".join(p for p in [todo.title, todo.notes or ""] if p),
        metadata={"status": todo.status, "project": todo.project_title, "tags": todo.tags or []},
    )


def index_saved_item(session: Session, item: SavedItem) -> None:
    index_entry(
        session,
        source_type="saved_item",
        source_id=item.id,
        title=item.title or (item.url or "saved item"),
        content="\n".join(p for p in [item.title or "", item.summary or "", item.text or "", item.url or ""] if p),
        metadata={"url": item.url, "status": item.status, "tags": item.tags or []},
    )


def reindex_all(session: Session) -> dict[str, int]:
    counts = {"note": 0, "job": 0, "todo": 0, "saved_item": 0}

    vault = VaultStore(os.getenv("OBSIDIAN_VAULT_PATH"))
    if vault.configured():
        try:
            for note in vault.list_notes():
                index_note(session, note)
                counts["note"] += 1
        except Exception:
            pass

    for job in session.scalars(select(Job).where(Job.status == "done")).all():
        index_job(session, job)
        counts["job"] += 1

    for todo in session.scalars(select(Todo).where(Todo.status != "dropped")).all():
        index_todo(session, todo)
        counts["todo"] += 1

    for item in session.scalars(select(SavedItem).where(SavedItem.status != "archived")).all():
        index_saved_item(session, item)
        counts["saved_item"] += 1

    session.flush()
    return counts


def semantic_search(
    session: Session,
    query: str,
    source_types: list[str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    stmt = select(IndexEntry)
    if source_types:
        stmt = stmt.where(IndexEntry.source_type.in_(source_types))
    rows = list(session.scalars(stmt).all())
    if not rows:
        return []

    provider = get_embedding_provider()
    query_vec = embed_query(query) if provider.configured() else []

    scored: list[tuple[float, IndexEntry]] = []
    if query_vec:
        for row in rows:
            if row.embedding:
                scored.append((cosine_similarity(query_vec, row.embedding), row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        scored = [pair for pair in scored if pair[0] > 0][:limit]

    if not scored:
        # Keyword fallback (also covers entries that never got embedded).
        lowered = f"%{query.lower()}%"
        kw_stmt = select(IndexEntry).where(
            or_(IndexEntry.title.ilike(lowered), IndexEntry.content.ilike(lowered))
        )
        if source_types:
            kw_stmt = kw_stmt.where(IndexEntry.source_type.in_(source_types))
        scored = [(0.0, row) for row in session.scalars(kw_stmt.limit(limit)).all()]

    return [
        {
            "source_type": row.source_type,
            "source_id": row.source_id,
            "title": row.title,
            "snippet": (row.content or "")[:280],
            "score": round(score, 4),
            "metadata": row.entry_metadata or {},
        }
        for score, row in scored
    ]
