from __future__ import annotations

import os
from typing import Any

from sqlalchemy import select

from .db import init_db, make_engine, make_session_factory
from .models import Category, Note
from .vault import VaultConfigurationError, VaultStore


def migrate_notes() -> dict[str, Any]:
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if not vault_path:
        raise VaultConfigurationError("OBSIDIAN_VAULT_PATH is required to migrate notes")

    engine = make_engine()
    init_db(engine)
    session_factory = make_session_factory(engine)
    vault = VaultStore(vault_path)
    report: dict[str, Any] = {"migrated": 0, "skipped": 0, "errors": []}

    with session_factory() as session:
        categories = {row.id: row.slug for row in session.scalars(select(Category)).all()}
        rows = session.scalars(select(Note).where(Note.archived.is_(False)).order_by(Note.created_at)).all()
        for note in rows:
            try:
                if vault.get(note.id):
                    report["skipped"] += 1
                    continue
                vault.create(
                    note.title,
                    note.body_md,
                    category=categories.get(note.category_id or "", "inbox"),
                    source_job_id=note.source_job_id,
                    note_id=note.id,
                    created_at=note.created_at,
                    updated_at=note.updated_at,
                )
                report["migrated"] += 1
            except Exception as exc:
                report["errors"].append({"id": note.id, "error": str(exc)})

    return report


def main() -> None:
    report = migrate_notes()
    print(f"migrated={report['migrated']} skipped={report['skipped']} errors={len(report['errors'])}")
    for item in report["errors"]:
        print(f"error {item['id']}: {item['error']}")


if __name__ == "__main__":
    main()
