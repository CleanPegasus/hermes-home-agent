from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import frontmatter


class VaultError(RuntimeError):
    pass


class VaultConfigurationError(VaultError):
    pass


class VaultNoteNotFoundError(VaultError):
    pass


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "untitled"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_iso(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return utcnow_iso()


def normalize_title(title: str) -> str:
    return title.strip().lower() or "untitled"


def normalize_category(category: str | None) -> str:
    return slugify(category or "inbox")


def normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for tag in tags:
        value = str(tag).strip().lower()
        if value and value not in seen:
            normalized.append(value)
            seen.add(value)
    return normalized


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


def note_to_dict(path: Path, post: frontmatter.Post) -> dict[str, Any]:
    metadata = post.metadata
    note_id = str(metadata.get("id") or "").strip()
    title = normalize_title(str(metadata.get("title") or path.stem))
    category = normalize_category(str(metadata.get("category") or path.parent.name or "inbox"))
    tags = metadata.get("tags")
    archived = bool(metadata.get("archived")) or ".archive" in path.parts
    return {
        "id": note_id,
        "title": title,
        "body_md": post.content,
        "category": category,
        "tags": normalize_tags(tags if isinstance(tags, list) else []),
        "archived": archived,
        "created_at": normalize_iso(metadata.get("created")),
        "updated_at": normalize_iso(metadata.get("updated")),
        "source_job_id": metadata.get("source_job_id") or None,
    }


class VaultStore:
    def __init__(self, root: Path | str | None):
        self.root = Path(root).expanduser() if root else None
        self._cache_signature: tuple[tuple[str, int], ...] | None = None
        self._cache_notes: list[dict[str, Any]] | None = None
        self._cache_paths: dict[str, Path] = {}

    def configured(self) -> bool:
        return self.root is not None

    def ensure_configured(self) -> Path:
        if self.root is None:
            raise VaultConfigurationError("OBSIDIAN_VAULT_PATH is not configured")
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def list_notes(self, category: str | None = None, include_archived: bool = False) -> list[dict[str, Any]]:
        notes = self._scan()
        category_slug = normalize_category(category) if category else None
        visible = [
            note
            for note in notes
            if (include_archived or not note["archived"])
            and (category_slug is None or note["category"] == category_slug)
        ]
        return sorted(visible, key=lambda note: str(note["updated_at"] or ""), reverse=True)

    def get(self, note_id: str) -> dict[str, Any] | None:
        for note in self._scan():
            if note["id"] == note_id:
                return note
        return None

    def create(
        self,
        title: str,
        body_md: str,
        category: str = "inbox",
        tags: list[str] | None = None,
        source_job_id: str | None = None,
        *,
        note_id: str | None = None,
        created_at: Any | None = None,
        updated_at: Any | None = None,
    ) -> dict[str, Any]:
        note_id = note_id or str(uuid4())
        now = utcnow_iso()
        note = {
            "id": note_id,
            "title": normalize_title(title),
            "body_md": body_md.strip(),
            "category": normalize_category(category),
            "tags": normalize_tags(tags),
            "archived": False,
            "created_at": normalize_iso(created_at) if created_at else now,
            "updated_at": normalize_iso(updated_at) if updated_at else now,
            "source_job_id": source_job_id,
        }
        self._write_new(note)
        return self.get(note_id) or note

    def update(
        self,
        note_id: str,
        *,
        title: str | None = None,
        body_md: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        note, path = self._required_note(note_id)
        if title is not None:
            note["title"] = normalize_title(title)
        if body_md is not None:
            note["body_md"] = body_md
        if category is not None:
            note["category"] = normalize_category(category)
        if tags is not None:
            note["tags"] = normalize_tags(tags)
        if archived is not None:
            note["archived"] = archived
        note["updated_at"] = utcnow_iso()
        return self._rewrite(note, path)

    def append(self, note_id: str, text: str) -> dict[str, Any]:
        note, path = self._required_note(note_id)
        addition = text.strip()
        if addition:
            note["body_md"] = f"{note['body_md'].rstrip()}\n\n{addition}".strip()
            note["updated_at"] = utcnow_iso()
            return self._rewrite(note, path)
        return note

    def move(self, note_id: str, category: str) -> dict[str, Any]:
        return self.update(note_id, category=category)

    def archive(self, note_id: str) -> dict[str, Any]:
        return self.update(note_id, archived=True)

    def merge(self, source_id: str, target_id: str) -> dict[str, dict[str, Any]]:
        if source_id == target_id:
            raise VaultError("cannot merge note into itself")
        source, _source_path = self._required_note(source_id)
        target, target_path = self._required_note(target_id)
        merged_body = (
            f"{target['body_md'].rstrip()}\n\n"
            f"## merged: {source['title']}\n\n"
            f"{source['body_md'].strip()}"
        ).strip()
        target["body_md"] = merged_body
        target["updated_at"] = utcnow_iso()
        updated_target = self._rewrite(target, target_path)
        archived_source = self.archive(source_id)
        return {"note": updated_target, "archived_note": archived_source}

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        needle = query.strip().lower()
        if not needle:
            return self.list_notes()[:limit]
        matches = [
            note
            for note in self.list_notes()
            if needle in f"{note['title']} {note['body_md']}".lower()
        ]
        return matches[: max(1, min(limit, 100))]

    def count(self) -> int:
        if not self.configured():
            return 0
        return len(self.list_notes())

    def path_for(self, note_id: str) -> Path | None:
        self._scan()
        return self._cache_paths.get(note_id)

    def _write_new(self, note: dict[str, Any]) -> None:
        root = self.ensure_configured()
        path = self._path_for_note(root, note)
        atomic_write(path, self._serialize(note))
        self._invalidate()

    def _rewrite(self, note: dict[str, Any], old_path: Path) -> dict[str, Any]:
        root = self.ensure_configured()
        next_path = self._path_for_note(root, note)
        atomic_write(next_path, self._serialize(note))
        if old_path != next_path and old_path.exists():
            old_path.unlink()
        self._invalidate()
        current = self.get(note["id"])
        if current is None:
            raise VaultNoteNotFoundError("note not found after write")
        return current

    def _required_note(self, note_id: str) -> tuple[dict[str, Any], Path]:
        note = self.get(note_id)
        path = self.path_for(note_id)
        if note is None or path is None:
            raise VaultNoteNotFoundError("note not found")
        return note, path

    def _path_for_note(self, root: Path, note: dict[str, Any]) -> Path:
        filename = f"{slugify(note['title'])}-{str(note['id'])[:8]}.md"
        if note.get("archived"):
            return root / ".archive" / filename
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
        post = frontmatter.Post(str(note.get("body_md") or ""), **metadata)
        return frontmatter.dumps(post)

    def _scan(self) -> list[dict[str, Any]]:
        root = self.ensure_configured()
        files = [path for path in root.rglob("*.md") if ".sync-conflict-" not in path.name]
        signature = tuple(sorted((str(path.relative_to(root)), path.stat().st_mtime_ns) for path in files if path.exists()))
        if signature == self._cache_signature and self._cache_notes is not None:
            return list(self._cache_notes)

        notes: list[dict[str, Any]] = []
        paths: dict[str, Path] = {}
        for path in files:
            try:
                post = frontmatter.load(path)
            except Exception:
                continue
            if not post.metadata.get("id"):
                continue
            note = note_to_dict(path, post)
            notes.append(note)
            paths[note["id"]] = path
        self._cache_signature = signature
        self._cache_notes = notes
        self._cache_paths = paths
        return list(notes)

    def _invalidate(self) -> None:
        self._cache_signature = None
        self._cache_notes = None
        self._cache_paths = {}
