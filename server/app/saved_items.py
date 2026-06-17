from __future__ import annotations

import logging
import re
import threading

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .embeddings import cosine_similarity, get_embedding_provider
from .indexer import index_saved_item
from .models import IndexEntry, SavedItem, utcnow

logger = logging.getLogger("hermes.saved_items")

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def fetch_url(url: str, timeout: float = 12.0) -> tuple[str | None, str | None]:
    """Return (title, text) extracted from a URL, or (None, None) on failure."""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"user-agent": "HermesHome/1.0"}) as client:
            response = client.get(url)
        if response.status_code >= 400:
            return None, None
        html = response.text
    except httpx.HTTPError:
        return None, None
    title_match = _TITLE_RE.search(html)
    title = strip_html(title_match.group(1)) if title_match else None
    return title, strip_html(html)[:4000]


def enrich_saved_item(session: Session, item: SavedItem) -> None:
    if item.url:
        title, text = fetch_url(item.url)
        if title and (not item.title or item.title == "saved item"):
            item.title = title[:600]
        if text:
            item.text = text
    body = item.text or item.title or ""
    item.summary = (body[:280] + "…") if len(body) > 280 else body
    item.status = "enriched"
    item.enriched_at = utcnow()
    item.updated_at = utcnow()
    index_saved_item(session, item)
    session.flush()


def enrich_pending_saved_items(session: Session) -> None:
    rows = session.scalars(select(SavedItem).where(SavedItem.status == "new")).all()
    for item in rows:
        try:
            enrich_saved_item(session, item)
        except Exception:
            logger.exception("failed to enrich saved item %s", item.id)
    if rows:
        _refresh_tile(session)


def start_saved_item_enrichment(session_factory: sessionmaker[Session], item_id: str) -> None:
    threading.Thread(target=_enrich_one, args=(session_factory, item_id), daemon=True).start()


def _enrich_one(session_factory: sessionmaker[Session], item_id: str) -> None:
    session = session_factory()
    try:
        item = session.get(SavedItem, item_id)
        if item and item.status == "new":
            enrich_saved_item(session, item)
            _refresh_tile(session)
            session.commit()
    except Exception:
        session.rollback()
        logger.exception("background enrichment failed for %s", item_id)
    finally:
        session.close()


def interest_centroid(session: Session) -> list[float]:
    """Average of recent note/job embeddings, used to rank saved items by relevance."""
    rows = session.scalars(
        select(IndexEntry)
        .where(IndexEntry.source_type.in_(["note", "job"]))
        .order_by(IndexEntry.indexed_at.desc())
        .limit(50)
    ).all()
    vectors = [row.embedding for row in rows if row.embedding]
    if not vectors:
        return []
    dim = len(vectors[0])
    centroid = [0.0] * dim
    for vec in vectors:
        if len(vec) != dim:
            continue
        for i, value in enumerate(vec):
            centroid[i] += value
    return [value / len(vectors) for value in centroid]


def refresh_for_you_job(session: Session) -> None:
    """Score enriched saved items against the user's recent interests, surface the top few."""
    provider = get_embedding_provider()
    centroid = interest_centroid(session) if provider.configured() else []
    items = session.scalars(
        select(SavedItem).where(SavedItem.status.in_(["enriched", "surfaced"]))
    ).all()
    for item in items:
        score = 0.0
        if centroid:
            entry = session.scalar(
                select(IndexEntry)
                .where(IndexEntry.source_type == "saved_item")
                .where(IndexEntry.source_id == item.id)
                .limit(1)
            )
            if entry and entry.embedding:
                score = cosine_similarity(centroid, entry.embedding)
        item.score = score
    ranked = sorted(items, key=lambda it: (it.score or 0.0), reverse=True)
    for item in ranked[:6]:
        if item.status == "enriched":
            item.status = "surfaced"
            item.surfaced_at = utcnow()
    _refresh_tile(session)


def _refresh_tile(session: Session) -> None:
    # Imported lazily to avoid a circular import with jobs.py.
    from .jobs import refresh_for_you_tile

    refresh_for_you_tile(session)
