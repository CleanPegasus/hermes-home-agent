from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, Category, Tile, utcnow


ACCENTS = {
    "jobs": "#0050EF",
    "todos": "#1BA1E2",
    "calendar": "#FA6800",
    "notes": "#008A00",
    "memory": "#6A00FF",
    "spend": "#D80073",
    "approvals": "#E51400",
    "channels": "#00ABA9",
    "vitals": "#A4C400",
}


SEED_CATEGORIES = [
    ("work", "work", ACCENTS["jobs"]),
    ("ideas", "ideas", ACCENTS["memory"]),
    ("home", "home", ACCENTS["todos"]),
    ("personal", "personal", ACCENTS["notes"]),
    ("health", "health", ACCENTS["vitals"]),
]


SEED_TILES = [
    {
        "key": "jobs",
        "size": "w",
        "color": ACCENTS["jobs"],
        "sort": 10,
        "front": {"count": 0, "line": "ready", "sub": "last finished waits here"},
        "back": {"line": "last finished", "sub": "nothing yet", "glyph": ">"}
    },
    {
        "key": "todos",
        "size": "m",
        "color": ACCENTS["todos"],
        "sort": 20,
        "front": {"count": 0, "line": "open", "sub": "nothing due"},
        "back": {"line": "last finished", "sub": "nothing yet", "glyph": "check"}
    },
    {
        "key": "calendar",
        "size": "m",
        "color": ACCENTS["calendar"],
        "sort": 30,
        "front": {"count": 0, "line": "today", "sub": "no events synced"},
        "back": {"line": "next", "sub": "calendar read path pending", "glyph": "cal"}
    },
    {
        "key": "notes",
        "size": "m",
        "color": ACCENTS["notes"],
        "sort": 40,
        "front": {"count": 0, "line": "filed", "sub": "nothing yet"},
        "back": {"line": "categories", "sub": "work ideas home", "glyph": "note"}
    },
    {
        "key": "approvals",
        "size": "s",
        "color": ACCENTS["approvals"],
        "sort": 50,
        "front": {"count": 0, "line": "appr", "sub": ""},
        "back": {"line": "needs", "sub": "none", "glyph": "!"}
    },
    {
        "key": "spend",
        "size": "s",
        "color": ACCENTS["spend"],
        "sort": 60,
        "front": {"count": 0, "line": "spend", "sub": ""},
        "back": {"line": "quiet", "sub": "no tools", "glyph": "$"}
    },
]


def database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./hermes-home.db")


def make_engine(url: str | None = None) -> Engine:
    resolved = url or database_url()
    connect_args = {"check_same_thread": False} if resolved.startswith("sqlite") else {}
    return create_engine(resolved, connect_args=connect_args)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        seed_database(session)


def seed_database(session: Session) -> None:
    for slug, name, color in SEED_CATEGORIES:
        exists = session.scalar(select(Category).where(Category.slug == slug))
        if not exists:
            session.add(Category(slug=slug, name=name, color=color, created_by="seed"))

    for tile_data in SEED_TILES:
        tile = session.get(Tile, tile_data["key"])
        if not tile:
            session.add(Tile(updated_at=utcnow(), **tile_data))
    session.commit()


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
