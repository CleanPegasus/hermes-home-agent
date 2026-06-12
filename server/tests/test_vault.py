from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import init_db
from app.migrate_notes import migrate_notes
from app.models import Category, Note
from app.vault import VaultStore


def test_vault_note_lifecycle_and_index_safety(tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")

    first = vault.create("Hallway Filter", "size is 20x25x1", category="home", tags=["hvac"])
    duplicate = vault.create("Hallway Filter", "replace quarterly", category="home")

    first_path = vault.path_for(first["id"])
    duplicate_path = vault.path_for(duplicate["id"])
    assert first_path is not None
    assert duplicate_path is not None
    assert first_path != duplicate_path
    assert first_path.parent.name == "home"
    assert first["title"] == "hallway filter"
    assert first["category"] == "home"
    assert first["tags"] == ["hvac"]

    updated = vault.update(first["id"], title="Hallway HVAC Filter", body_md="merv 13", category="health", tags=["hvac", "home"])
    assert updated["id"] == first["id"]
    assert updated["title"] == "hallway hvac filter"
    assert updated["body_md"] == "merv 13"
    assert updated["category"] == "health"
    assert vault.path_for(first["id"]) is not None
    assert vault.path_for(first["id"]).parent.name == "health"  # type: ignore[union-attr]

    appended = vault.append(first["id"], "buy two spares")
    assert appended["tags"] == ["hvac", "home"]
    assert "merv 13\n\nbuy two spares" in appended["body_md"]

    merged = vault.merge(duplicate["id"], first["id"])
    assert "## merged: hallway filter" in merged["note"]["body_md"]
    assert merged["archived_note"]["archived"] is True
    assert vault.path_for(duplicate["id"]) is not None
    assert ".archive" in vault.path_for(duplicate["id"]).parts  # type: ignore[union-attr]

    archived = vault.archive(first["id"])
    assert archived["archived"] is True
    assert ".archive" in vault.path_for(first["id"]).parts  # type: ignore[union-attr]

    (tmp_path / "vault" / "home" / "bad.sync-conflict-20260612.md").write_text("---\nid: nope\n---\nconflict\n")
    (tmp_path / "vault" / "home" / "idless.md").write_text("---\ntitle: no id\n---\nbody\n")
    visible = vault.list_notes(include_archived=True)
    assert {note["id"] for note in visible} == {first["id"], duplicate["id"]}


def test_vault_search_and_migration_idempotency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "notes.db"
    engine = create_engine(f"sqlite:///{database_path}")
    init_db(engine)
    Session = sessionmaker(engine)
    with Session() as session:
        category = session.query(Category).filter(Category.slug == "home").one()
        note = Note(title="Water Shutoff", body_md="Valve lives behind the dryer", category_id=category.id)
        session.add(note)
        session.commit()
        note_id = note.id

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path / "vault"))

    first = migrate_notes()
    second = migrate_notes()

    assert first["migrated"] == 1
    assert first["skipped"] == 0
    assert second["migrated"] == 0
    assert second["skipped"] == 1

    vault = VaultStore(tmp_path / "vault")
    migrated = vault.get(note_id)
    assert migrated is not None
    assert migrated["category"] == "home"
    assert vault.search("DRYER")[0]["id"] == note_id
