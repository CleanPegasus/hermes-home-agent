from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from .models import AgentProfile, Base, Category, Tile, utcnow


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
    "codex": "#647687",
    "history": "#0050EF",
    "profiles": "#A20025",
    "ask": "#AA00FF",
    "foryou": "#F0A30A",
}


SEED_CATEGORIES = [
    ("inbox", "inbox", ACCENTS["jobs"]),
    ("home", "home", ACCENTS["todos"]),
    ("errands", "errands", ACCENTS["calendar"]),
    ("health", "health", ACCENTS["vitals"]),
    ("reference", "reference", ACCENTS["notes"]),
]


SEED_TILES = [
    {
        "key": "jobs",
        "size": "w",
        "color": ACCENTS["jobs"],
        "sort": 10,
        "front": {"count": 0, "emoji": "⚙️", "line": "ready", "sub": "last finished waits here"},
        "back": {"line": "last finished", "sub": "nothing yet", "glyph": ">"}
    },
    {
        "key": "todos",
        "size": "m",
        "color": ACCENTS["todos"],
        "sort": 20,
        "front": {"count": 0, "emoji": "✅", "line": "open", "sub": "nothing due"},
        "back": {"line": "last finished", "sub": "nothing yet", "glyph": "check"}
    },
    {
        "key": "calendar",
        "size": "m",
        "color": ACCENTS["calendar"],
        "sort": 30,
        "front": {"count": 0, "emoji": "📅", "line": "today", "sub": "no events synced"},
        "back": {"line": "next", "sub": "calendar read path pending", "glyph": "cal"}
    },
    {
        "key": "notes",
        "size": "m",
        "color": ACCENTS["notes"],
        "sort": 40,
        "front": {"count": 0, "emoji": "📝", "line": "filed", "sub": "nothing yet"},
        "back": {"line": "categories", "sub": "inbox home errands", "glyph": "note"}
    },
    {
        "key": "ask",
        "size": "m",
        "color": ACCENTS["ask"],
        "sort": 22,
        "front": {"count": 0, "emoji": "❓", "line": "ask", "sub": "no open questions"},
        "back": {"line": "waiting on you", "sub": "all clear", "glyph": "?"}
    },
    {
        "key": "foryou",
        "size": "m",
        "color": ACCENTS["foryou"],
        "sort": 45,
        "front": {"count": 0, "emoji": "✨", "line": "for you", "sub": "share to save"},
        "back": {"line": "saved", "sub": "all caught up", "glyph": ">"}
    },
    {
        "key": "approvals",
        "size": "s",
        "color": ACCENTS["approvals"],
        "sort": 50,
        "front": {"count": 0, "emoji": "🛡️", "line": "appr", "sub": ""},
        "back": {"line": "needs", "sub": "none", "glyph": "!"}
    },
    {
        "key": "spend",
        "size": "s",
        "color": ACCENTS["spend"],
        "sort": 60,
        "front": {"count": 0, "emoji": "💸", "line": "spend", "sub": ""},
        "back": {"line": "quiet", "sub": "no tools", "glyph": "$"}
    },
    {
        "key": "channels",
        "size": "s",
        "color": ACCENTS["channels"],
        "sort": 70,
        "front": {"count": 0, "emoji": "📨", "line": "inbox", "sub": ""},
        "back": {"line": "quiet", "sub": "no connectors", "glyph": "@"}
    },
    {
        "key": "vitals",
        "size": "s",
        "color": ACCENTS["vitals"],
        "sort": 80,
        "front": {"count": 0, "emoji": "💓", "line": "ok", "sub": ""},
        "back": {"line": "system", "sub": "local", "glyph": "pulse"}
    },
    {
        "key": "codex",
        "size": "s",
        "color": ACCENTS["codex"],
        "sort": 90,
        "front": {"emoji": "🛠️", "glyph": "gear", "line": "codex", "sub": "yolo"},
        "back": {"line": "web dir", "sub": "feature work", "glyph": ">"}
    },
    {
        "key": "history",
        "size": "w",
        "color": ACCENTS["history"],
        "sort": 95,
        "front": {"emoji": "🕘", "line": "history", "sub": "recent chats"},
        "back": {"line": "timeline", "sub": "summaries", "glyph": ">"}
    },
    {
        "key": "profiles",
        "size": "w",
        "color": ACCENTS["profiles"],
        "sort": 85,
        "front": {"emoji": "🎭", "line": "profiles", "sub": "agent modes"},
        "back": {"line": "personas", "sub": "choose a voice", "glyph": ">"}
    },
]


ROUTER_PERSONA = (
    "You are Hermes' router. Read the incoming command and decide the cheapest correct action, "
    "then stop.\n"
    "- If it is a thing to do or remember to act on (a task, reminder, errand, 'buy', 'call', 'remind me'), "
    "call the todos_create tool, then job_set_summary, and finish.\n"
    "- If it is a fact, idea, or snippet to remember (a note, 'note that', 'remember that', 'write down', "
    "'file this'), call notes_create, then job_set_summary, and finish.\n"
    "- If it needs real work — research, coding, multi-step planning, drafting, analysis — call the "
    "jobs_handoff tool with the best profile_slug (research-agent, coding-agent, financial-helper, or "
    "personal-assistant) and the original command, then stop. The chosen agent takes over from there.\n"
    "- If you are unsure which path applies, use clarifications_request to ask before acting.\n"
    "Never do the downstream work yourself; route it. Keep summaries to one short line."
)


SEED_PROFILES = [
    {
        "slug": "router",
        "name": "router",
        "emoji": "🧭",
        "color": "#0050EF",
        "persona": ROUTER_PERSONA,
        "is_default": True,
    },
    {
        "slug": "personal-assistant",
        "name": "personal assistant",
        "emoji": "🪄",
        "color": "#1BA1E2",
        "persona": "You are a calm personal assistant for home operations. Prefer concise plans, clear next actions, and safe defaults.",
        "is_default": False,
    },
    {
        "slug": "research-agent",
        "name": "research agent",
        "emoji": "🧠",
        "color": "#0050EF",
        "persona": "You are a careful research agent. Gather context, cite sources when available, and summarize findings plainly.",
        "is_default": False,
    },
    {
        "slug": "coding-agent",
        "name": "coding agent",
        "emoji": "💻",
        "color": "#647687",
        "persona": "You are a coding agent. Read the repo first, write tests for behavior changes, and keep diffs focused.",
        "is_default": False,
    },
    {
        "slug": "financial-helper",
        "name": "financial helper",
        "emoji": "💰",
        "color": "#D80073",
        "persona": "You are a financial helper. Be conservative, separate facts from assumptions, and flag anything that needs review.",
        "is_default": False,
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
    apply_lightweight_migrations(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        seed_database(session)


def apply_lightweight_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    dialect = engine.dialect.name
    with engine.begin() as connection:
        if "pages" in table_names:
            columns = {column["name"] for column in inspector.get_columns("pages")}
            if "pinned_at" not in columns:
                connection.execute(text(f"ALTER TABLE pages ADD COLUMN pinned_at {timestamp_type(dialect)}"))
            if "provenance" not in columns:
                connection.execute(text(f"ALTER TABLE pages ADD COLUMN provenance {json_type(dialect)} DEFAULT {empty_json_default(dialect)}"))
        if "jobs" in table_names:
            columns = {column["name"] for column in inspector.get_columns("jobs")}
            if dialect.startswith("postgres"):
                connection.execute(text("ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check"))
                connection.execute(
                    text(
                        """
                        ALTER TABLE jobs
                        ADD CONSTRAINT jobs_status_check
                        CHECK (status IN ('queued', 'running', 'done', 'failed', 'needs_approval', 'needs_clarification', 'cancelled'))
                        """
                    )
                )
            if "stdout_tail" not in columns:
                connection.execute(text("ALTER TABLE jobs ADD COLUMN stdout_tail TEXT"))
            if "stderr_tail" not in columns:
                connection.execute(text("ALTER TABLE jobs ADD COLUMN stderr_tail TEXT"))
            if "exit_code" not in columns:
                connection.execute(text("ALTER TABLE jobs ADD COLUMN exit_code INTEGER"))
            if "emoji" not in columns:
                connection.execute(text("ALTER TABLE jobs ADD COLUMN emoji TEXT"))
            if "summary" not in columns:
                connection.execute(text("ALTER TABLE jobs ADD COLUMN summary TEXT"))
            if "profile_id" not in columns:
                connection.execute(text("ALTER TABLE jobs ADD COLUMN profile_id TEXT"))
            if "parent_job_id" not in columns:
                connection.execute(text("ALTER TABLE jobs ADD COLUMN parent_job_id TEXT"))
        if "clarifications" in table_names:
            columns = {column["name"] for column in inspector.get_columns("clarifications")}
            if "follow_up_job_id" not in columns:
                connection.execute(text("ALTER TABLE clarifications ADD COLUMN follow_up_job_id TEXT"))
            if "answered_at" not in columns:
                connection.execute(text(f"ALTER TABLE clarifications ADD COLUMN answered_at {timestamp_type(dialect)}"))
        if "todos" in table_names:
            columns = {column["name"] for column in inspector.get_columns("todos")}
            if "external_id" not in columns:
                connection.execute(text("ALTER TABLE todos ADD COLUMN external_id TEXT"))
            if "provider" not in columns:
                connection.execute(text("ALTER TABLE todos ADD COLUMN provider TEXT NOT NULL DEFAULT 'todoist'"))
            if "project_id" not in columns:
                connection.execute(text("ALTER TABLE todos ADD COLUMN project_id TEXT"))
            if "project_title" not in columns:
                connection.execute(text("ALTER TABLE todos ADD COLUMN project_title TEXT"))
            if "priority" not in columns:
                connection.execute(text("ALTER TABLE todos ADD COLUMN priority INTEGER"))
            if "updated_at" not in columns:
                if dialect.startswith("sqlite"):
                    # SQLite cannot add a column with a non-constant default such as
                    # CURRENT_TIMESTAMP. Add it nullable, then backfill existing rows;
                    # SQLAlchemy still supplies utcnow() for new Todo instances.
                    connection.execute(text(f"ALTER TABLE todos ADD COLUMN updated_at {timestamp_type(dialect)}"))
                    connection.execute(text("UPDATE todos SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"))
                else:
                    connection.execute(text(f"ALTER TABLE todos ADD COLUMN updated_at {timestamp_type(dialect)} NOT NULL DEFAULT CURRENT_TIMESTAMP"))
        if "approvals" in table_names:
            columns = {column["name"] for column in inspector.get_columns("approvals")}
            if "decided_at" not in columns:
                connection.execute(text(f"ALTER TABLE approvals ADD COLUMN decided_at {timestamp_type(dialect)}"))
            if "result" not in columns:
                connection.execute(text(f"ALTER TABLE approvals ADD COLUMN result {json_type(dialect)} DEFAULT {empty_json_default(dialect)}"))
            if "error" not in columns:
                connection.execute(text("ALTER TABLE approvals ADD COLUMN error TEXT"))
        if "action_runs" in table_names:
            columns = {column["name"] for column in inspector.get_columns("action_runs")}
            if "source_job_id" not in columns:
                connection.execute(text("ALTER TABLE action_runs ADD COLUMN source_job_id TEXT"))
            if "source_page_id" not in columns:
                connection.execute(text("ALTER TABLE action_runs ADD COLUMN source_page_id TEXT"))
        if "codex_runs" in table_names:
            columns = {column["name"] for column in inspector.get_columns("codex_runs")}
            if "effort" not in columns:
                connection.execute(text("ALTER TABLE codex_runs ADD COLUMN effort TEXT NOT NULL DEFAULT 'xhigh'"))
            if "process_id" not in columns:
                connection.execute(text("ALTER TABLE codex_runs ADD COLUMN process_id INTEGER"))
            if "cancel_requested" not in columns:
                connection.execute(text(boolean_column_default(dialect, "cancel_requested", False)))
            if "before_status" not in columns:
                connection.execute(text("ALTER TABLE codex_runs ADD COLUMN before_status TEXT"))
            if "after_status" not in columns:
                connection.execute(text("ALTER TABLE codex_runs ADD COLUMN after_status TEXT"))
            if "diff_stat" not in columns:
                connection.execute(text("ALTER TABLE codex_runs ADD COLUMN diff_stat TEXT"))


def timestamp_type(dialect: str) -> str:
    return "TIMESTAMPTZ" if dialect.startswith("postgres") else "DATETIME"


def json_type(dialect: str) -> str:
    return "JSONB" if dialect.startswith("postgres") else "JSON"


def empty_json_default(dialect: str) -> str:
    return "'{}'::jsonb" if dialect.startswith("postgres") else "'{}'"


def boolean_column_default(dialect: str, name: str, default: bool) -> str:
    value = "FALSE" if dialect.startswith("postgres") and not default else "TRUE" if dialect.startswith("postgres") else "0" if not default else "1"
    column_type = "BOOLEAN" if dialect.startswith("postgres") else "BOOLEAN"
    return f"ALTER TABLE codex_runs ADD COLUMN {name} {column_type} NOT NULL DEFAULT {value}"


def seed_database(session: Session) -> None:
    for slug, name, color in SEED_CATEGORIES:
        exists = session.scalar(select(Category).where(Category.slug == slug))
        if not exists:
            session.add(Category(slug=slug, name=name, color=color, created_by="seed"))

    for tile_data in SEED_TILES:
        tile = session.get(Tile, tile_data["key"])
        if not tile:
            session.add(Tile(updated_at=utcnow(), **tile_data))

    added_router = False
    for profile_data in SEED_PROFILES:
        exists = session.scalar(select(AgentProfile).where(AgentProfile.slug == profile_data["slug"]))
        if not exists:
            session.add(AgentProfile(**profile_data))
            if profile_data["slug"] == "router":
                added_router = True
    session.flush()

    # When the router profile is first introduced it becomes the single default so
    # incoming commands are routed automatically. Existing custom defaults are
    # respected on subsequent boots (we only reconcile when router is newly added).
    if added_router:
        router = session.scalar(select(AgentProfile).where(AgentProfile.slug == "router"))
        if router:
            for profile in session.scalars(select(AgentProfile)).all():
                profile.is_default = profile.id == router.id
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
