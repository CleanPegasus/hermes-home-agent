from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import frontmatter


class VaultConfigurationError(RuntimeError):
    pass


class VaultNoteNotFoundError(RuntimeError):
    pass


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "untitled"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_title(title: str) -> str:
    return title.strip().lower() or "untitled"


def normalize_category(category: str | None) -> str:
    return slugify(category or "inbox")


def normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        value = str(tag).strip().lower()
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def normalize_iso(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return utcnow_iso()


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temp_file:
            temp_name = temp_file.name
            temp_file.write(content)
        os.replace(temp_name, path)
    finally:
        if temp_name:
            temp_path = Path(temp_name)
            if temp_path.exists():
                temp_path.unlink()


class VaultStore:
    def __init__(self, root: Path | str | None):
        self.root = Path(root).expanduser() if root else None

    def configured(self) -> bool:
        return self.root is not None

    def ensure_root(self) -> Path:
        if self.root is None:
            raise VaultConfigurationError("OBSIDIAN_VAULT_PATH is not configured")
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def list_notes(self, category: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        category_slug = normalize_category(category) if category else None
        rows = [
            note
            for note in self._scan()
            if not note["archived"] and (category_slug is None or note["category"] == category_slug)
        ]
        rows.sort(key=lambda note: str(note["updated_at"] or ""), reverse=True)
        return rows[: max(1, min(limit, 200))]

    def count(self) -> int:
        if not self.configured():
            return 0
        return len(self.list_notes(limit=10_000))

    def get(self, note_id: str) -> tuple[dict[str, Any], Path]:
        for note, path in self._scan_with_paths():
            if note["id"] == note_id:
                return note, path
        raise VaultNoteNotFoundError("note not found")

    def create(
        self,
        title: str,
        body_md: str,
        category: str = "inbox",
        tags: list[str] | None = None,
        source_job_id: str | None = None,
    ) -> dict[str, Any]:
        now = utcnow_iso()
        note = {
            "id": str(uuid4()),
            "title": normalize_title(title),
            "body_md": body_md.strip(),
            "category": normalize_category(category),
            "tags": normalize_tags(tags),
            "archived": False,
            "created_at": now,
            "updated_at": now,
            "source_job_id": source_job_id,
        }
        atomic_write(self._path_for(note), self._serialize(note))
        return note

    def append(self, note_id: str, body_md: str) -> dict[str, Any]:
        note, path = self.get(note_id)
        addition = body_md.strip()
        if addition:
            note["body_md"] = f"{note['body_md'].rstrip()}\n\n{addition}".strip()
            note["updated_at"] = utcnow_iso()
            atomic_write(path, self._serialize(note))
        return note

    def move(self, note_id: str, category: str) -> dict[str, Any]:
        note, old_path = self.get(note_id)
        note["category"] = normalize_category(category)
        note["updated_at"] = utcnow_iso()
        next_path = self._path_for(note)
        atomic_write(next_path, self._serialize(note))
        if old_path != next_path and old_path.exists():
            old_path.unlink()
        return note

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        needle = query.strip().lower()
        if not needle:
            return self.list_notes(limit=limit)
        matches = [
            note
            for note in self.list_notes(limit=10_000)
            if needle in f"{note['title']} {note['body_md']}".lower()
        ]
        return matches[: max(1, min(limit, 100))]

    def _path_for(self, note: dict[str, Any]) -> Path:
        root = self.ensure_root()
        filename = f"{slugify(note['title'])}-{str(note['id'])[:8]}.md"
        return root / normalize_category(note.get("category")) / filename

    def _serialize(self, note: dict[str, Any]) -> str:
        metadata = {
            "id": note["id"],
            "title": note["title"],
            "category": normalize_category(note.get("category")),
            "tags": normalize_tags(note.get("tags")),
            "created": normalize_iso(note.get("created_at")),
            "updated": normalize_iso(note.get("updated_at")),
            "archived": bool(note.get("archived")),
        }
        if note.get("source_job_id"):
            metadata["source_job_id"] = note["source_job_id"]
        return frontmatter.dumps(frontmatter.Post(str(note.get("body_md") or ""), **metadata))

    def _scan(self) -> list[dict[str, Any]]:
        return [note for note, _path in self._scan_with_paths()]

    def _scan_with_paths(self) -> list[tuple[dict[str, Any], Path]]:
        root = self.ensure_root()
        rows: list[tuple[dict[str, Any], Path]] = []
        for path in root.rglob("*.md"):
            if ".sync-conflict-" in path.name:
                continue
            try:
                post = frontmatter.load(path)
            except Exception:
                continue
            note_id = str(post.metadata.get("id") or "").strip()
            if not note_id:
                continue
            tags = post.metadata.get("tags")
            rows.append((
                {
                    "id": note_id,
                    "title": normalize_title(str(post.metadata.get("title") or path.stem)),
                    "body_md": post.content,
                    "category": normalize_category(str(post.metadata.get("category") or path.parent.name or "inbox")),
                    "tags": normalize_tags(tags if isinstance(tags, list) else []),
                    "archived": bool(post.metadata.get("archived")) or ".archive" in path.parts,
                    "created_at": normalize_iso(post.metadata.get("created")),
                    "updated_at": normalize_iso(post.metadata.get("updated")),
                    "source_job_id": post.metadata.get("source_job_id") or None,
                },
                path,
            ))
        return rows
