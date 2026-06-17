from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

REST_BASE = "https://api.todoist.com/rest/v2"
SYNC_BASE = "https://api.todoist.com/sync/v9"


class TodoistError(RuntimeError):
    """Base class for Todoist integration failures."""


class TodoistConfigurationError(TodoistError):
    """Raised when required Todoist settings are missing."""


class TodoistAPIError(TodoistError):
    """Raised when Todoist rejects or fails a request."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class TodoistConfig:
    token: str
    default_project_id: str | None = None
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "TodoistConfig":
        token = todoist_token_from_env()
        if not token:
            raise TodoistConfigurationError(
                "Todoist todo integration is not configured. Set TODOIST_TOKEN or TODOIST_TOKEN_FILE to use todos."
            )
        default_project_id = os.getenv("TODOIST_DEFAULT_PROJECT_ID", "").strip() or None
        timeout = float(os.getenv("TODOIST_TIMEOUT_SECONDS", "10"))
        return cls(token=token, default_project_id=default_project_id, timeout_seconds=timeout)


@dataclass(frozen=True)
class NormalizedTodoistTask:
    id: str
    external_id: str
    title: str
    notes: str | None
    status: str
    due_at: datetime | None
    scheduled_for: datetime | None
    tags: list[str]
    priority: int | None
    provider: str
    project_id: str | None
    project_title: str | None
    created_at: datetime | None
    updated_at: datetime | None
    completed_at: datetime | None
    raw: dict[str, Any]


class TodoistClient:
    def __init__(self, config: TodoistConfig) -> None:
        self.config = config

    @classmethod
    def from_env(cls) -> "TodoistClient":
        return cls(TodoistConfig.from_env())

    def list_tasks(self) -> list[dict[str, Any]]:
        """Active (non-completed) tasks. Todoist's REST list returns open tasks only."""
        payload = self._request("GET", "/tasks")
        if not isinstance(payload, list):
            raise TodoistAPIError("Todoist returned an unexpected tasks payload")
        return [task for task in payload if isinstance(task, dict)]

    def list_completed_tasks(self, limit: int = 200) -> list[dict[str, Any]]:
        """Recently completed tasks via the Sync API completed endpoint."""
        payload = self._request("GET", "/completed/get_all", params={"limit": limit}, base=SYNC_BASE)
        if not isinstance(payload, dict):
            return []
        items = payload.get("items")
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def get_task(self, task_id: str) -> dict[str, Any]:
        task = self._request("GET", f"/tasks/{task_id}")
        if not isinstance(task, dict):
            raise TodoistAPIError("Todoist returned an unexpected task payload")
        return task

    def list_projects(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/projects")
        if not isinstance(payload, list):
            raise TodoistAPIError("Todoist returned an unexpected projects payload")
        return [project for project in payload if isinstance(project, dict)]

    def list_labels(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/labels")
        if not isinstance(payload, list):
            raise TodoistAPIError("Todoist returned an unexpected labels payload")
        return [label for label in payload if isinstance(label, dict)]

    def ensure_label(self, name: str) -> dict[str, Any]:
        normalized = name.strip()
        if not normalized:
            raise TodoistAPIError("label name is required")
        for label in self.list_labels():
            if str(label.get("name", "")).strip().lower() == normalized.lower():
                return label
        payload = self._request("POST", "/labels", json={"name": normalized})
        if not isinstance(payload, dict):
            raise TodoistAPIError("Todoist returned an unexpected label payload")
        return payload

    def set_task_labels(self, task_id: str, label_names: list[str]) -> dict[str, Any]:
        # Todoist v2 stores labels as plain names directly on the task.
        return self.update_task(task_id, {"labels": label_names})

    def create_task(
        self,
        *,
        title: str,
        description: str | None = None,
        due_date: datetime | str | None = None,
        start_date: datetime | str | None = None,  # unused by Todoist; kept for interface parity
        project_id: str | None = None,
        label_titles: list[str] | None = None,
        priority: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"content": title}
        target_project_id = project_id or self.config.default_project_id
        if target_project_id:
            payload["project_id"] = target_project_id
        if description:
            payload["description"] = description
        if due_date:
            self._apply_due(payload, due_date)
        if priority is not None:
            payload["priority"] = clamp_priority(priority)
        if label_titles:
            payload["labels"] = [name.strip() for name in label_titles if name.strip()]
        task = self._request("POST", "/tasks", json=payload)
        if not isinstance(task, dict):
            raise TodoistAPIError("Todoist returned an unexpected create payload")
        return task

    def update_task(self, task_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        task = self._request("POST", f"/tasks/{task_id}", json=changes)
        if not isinstance(task, dict):
            raise TodoistAPIError("Todoist returned an unexpected update payload")
        return task

    def complete_task(self, task_id: str) -> None:
        self._request("POST", f"/tasks/{task_id}/close")

    def reopen_task(self, task_id: str) -> None:
        self._request("POST", f"/tasks/{task_id}/reopen")

    def delete_task(self, task_id: str) -> None:
        self._request("DELETE", f"/tasks/{task_id}")

    def _apply_due(self, payload: dict[str, Any], value: datetime | str) -> None:
        if isinstance(value, datetime):
            if value.hour or value.minute or value.second:
                payload["due_datetime"] = value.isoformat()
            else:
                payload["due_date"] = value.date().isoformat()
        else:
            payload["due_string"] = str(value)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        base: str = REST_BASE,
    ) -> Any:
        url = f"{base}{path}"
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.config.token}",
        }
        if json is not None:
            headers["content-type"] = "application/json"
        try:
            with httpx.Client(timeout=self.config.timeout_seconds) as client:
                response = client.request(method, url, headers=headers, json=json, params=params)
        except httpx.TimeoutException as exc:
            raise TodoistAPIError(f"Todoist request timed out: {method} {path}") from exc
        except httpx.RequestError as exc:
            raise TodoistAPIError(f"Todoist request failed: {exc}") from exc

        if response.status_code >= 400:
            raise TodoistAPIError(
                f"Todoist request failed ({response.status_code}): {readable_error(response)}",
                status_code=response.status_code,
            )
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise TodoistAPIError("Todoist returned invalid JSON") from exc


def normalize_task(task: dict[str, Any], project_titles: dict[str, str] | None = None) -> NormalizedTodoistTask:
    external_id = str(task.get("id") or "").strip()
    if not external_id:
        raise TodoistAPIError("Todoist task is missing an id")
    project_id = optional_str(task.get("project_id"))
    project_title = (project_titles or {}).get(project_id or "")
    return NormalizedTodoistTask(
        id=external_id,
        external_id=external_id,
        title=str(task.get("content") or "untitled task").strip() or "untitled task",
        notes=optional_str(task.get("description")),
        status="done" if bool(task.get("is_completed")) else "open",
        due_at=parse_due(task.get("due")),
        scheduled_for=None,
        tags=[str(label) for label in task.get("labels", []) if str(label).strip()],
        priority=optional_int(task.get("priority")),
        provider="todoist",
        project_id=project_id,
        project_title=project_title or (f"project {project_id}" if project_id else None),
        created_at=parse_todoist_datetime(task.get("created_at")),
        updated_at=parse_todoist_datetime(task.get("created_at")),
        completed_at=None,
        raw=task,
    )


def normalize_completed_task(item: dict[str, Any], project_titles: dict[str, str] | None = None) -> NormalizedTodoistTask:
    external_id = str(item.get("task_id") or item.get("id") or "").strip()
    if not external_id:
        raise TodoistAPIError("Todoist completed item is missing a task id")
    project_id = optional_str(item.get("project_id"))
    project_title = (project_titles or {}).get(project_id or "")
    completed_at = parse_todoist_datetime(item.get("completed_at"))
    return NormalizedTodoistTask(
        id=external_id,
        external_id=external_id,
        title=str(item.get("content") or "untitled task").strip() or "untitled task",
        notes=None,
        status="done",
        due_at=None,
        scheduled_for=None,
        tags=[],
        priority=None,
        provider="todoist",
        project_id=project_id,
        project_title=project_title or (f"project {project_id}" if project_id else None),
        created_at=None,
        updated_at=completed_at,
        completed_at=completed_at,
        raw=item,
    )


def clamp_priority(value: int) -> int:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(4, priority))


def parse_due(due: object) -> datetime | None:
    if not isinstance(due, dict):
        return None
    return parse_todoist_datetime(due.get("datetime") or due.get("date"))


def parse_todoist_datetime(value: object) -> datetime | None:
    if value is None or isinstance(value, bool):
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


def optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def todoist_token_from_env() -> str:
    token = os.getenv("TODOIST_TOKEN", "").strip()
    if token:
        return token
    token_file = os.getenv("TODOIST_TOKEN_FILE", "").strip()
    if not token_file:
        return ""
    path = Path(token_file).expanduser()
    try:
        file_token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise TodoistConfigurationError(f"Could not read TODOIST_TOKEN_FILE {path}: {exc.strerror}") from exc
    if not file_token:
        raise TodoistConfigurationError(f"TODOIST_TOKEN_FILE {path} is empty")
    return file_token


def readable_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:500] or response.reason_phrase
    if isinstance(payload, dict):
        for key in ("error", "message", "detail"):
            value = payload.get(key)
            if value:
                return str(value)
    return str(payload)[:500]


def todoist_status() -> dict[str, Any]:
    configuration_error = None
    try:
        token = todoist_token_from_env()
    except TodoistConfigurationError as exc:
        token = ""
        configuration_error = str(exc)
    default_project_id = os.getenv("TODOIST_DEFAULT_PROJECT_ID", "").strip() or None
    status = {
        "configured": bool(token),
        "url": REST_BASE,
        "default_project_configured": default_project_id is not None,
        "provider": "todoist",
        "token_file_configured": bool(os.getenv("TODOIST_TOKEN_FILE", "").strip()),
    }
    if configuration_error:
        status["configuration_error"] = configuration_error
    return status
