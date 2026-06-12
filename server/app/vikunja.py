from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


class VikunjaError(RuntimeError):
    """Base class for Vikunja integration failures."""


class VikunjaConfigurationError(VikunjaError):
    """Raised when required Vikunja settings are missing."""


class VikunjaAPIError(VikunjaError):
    """Raised when Vikunja rejects or fails a request."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class VikunjaConfig:
    api_url: str
    token: str
    default_project_id: str | None = None
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "VikunjaConfig":
        raw_url = os.getenv("VIKUNJA_URL", "").strip()
        token = vikunja_token_from_env()
        missing = []
        if not raw_url:
            missing.append("VIKUNJA_URL")
        if not token:
            missing.append("VIKUNJA_TOKEN or VIKUNJA_TOKEN_FILE")
        if missing:
            joined = ", ".join(missing)
            raise VikunjaConfigurationError(
                f"Vikunja todo integration is not configured. Set {joined} to use todos."
            )
        default_project_id = (
            os.getenv("VIKUNJA_DEFAULT_PROJECT_ID", "").strip()
            or os.getenv("VIKUNJA_PROJECT_ID", "").strip()
            or None
        )
        timeout = float(os.getenv("VIKUNJA_TIMEOUT_SECONDS", "10"))
        return cls(
            api_url=normalize_vikunja_api_url(raw_url),
            token=token,
            default_project_id=default_project_id,
            timeout_seconds=timeout,
        )

    def require_default_project_id(self) -> str:
        if not self.default_project_id:
            raise VikunjaConfigurationError(
                "Vikunja todo creation requires VIKUNJA_DEFAULT_PROJECT_ID or VIKUNJA_PROJECT_ID."
            )
        return self.default_project_id


@dataclass(frozen=True)
class NormalizedVikunjaTask:
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


class VikunjaClient:
    def __init__(self, config: VikunjaConfig) -> None:
        self.config = config

    @classmethod
    def from_env(cls) -> "VikunjaClient":
        return cls(VikunjaConfig.from_env())

    def list_tasks(self, per_page: int = 200, max_pages: int = 5) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            batch = self._request(
                "GET",
                "/tasks",
                params={
                    "page": page,
                    "per_page": per_page,
                    "sort_by": "updated",
                    "order_by": "desc",
                },
            )
            if not isinstance(batch, list):
                raise VikunjaAPIError("Vikunja returned an unexpected tasks payload")
            tasks.extend(task for task in batch if isinstance(task, dict))
            if len(batch) < per_page:
                break
        return tasks

    def get_task(self, task_id: str) -> dict[str, Any]:
        task = self._request("GET", f"/tasks/{task_id}")
        if not isinstance(task, dict):
            raise VikunjaAPIError("Vikunja returned an unexpected task payload")
        return task

    def list_projects(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/projects")
        if not isinstance(payload, list):
            raise VikunjaAPIError("Vikunja returned an unexpected projects payload")
        return [project for project in payload if isinstance(project, dict)]

    def list_labels(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/labels")
        if not isinstance(payload, list):
            raise VikunjaAPIError("Vikunja returned an unexpected labels payload")
        return [label for label in payload if isinstance(label, dict)]

    def ensure_label(self, title: str) -> dict[str, Any]:
        normalized = title.strip().lower()
        if not normalized:
            raise VikunjaAPIError("label title is required")
        for label in self.list_labels():
            if str(label.get("title", "")).strip().lower() == normalized:
                return label
        payload = self._request("PUT", "/labels", json={"title": normalized})
        if not isinstance(payload, dict):
            raise VikunjaAPIError("Vikunja returned an unexpected label payload")
        return payload

    def set_task_labels(self, task_id: str, label_ids: list[str]) -> None:
        for label_id in label_ids:
            try:
                self._request("PUT", f"/tasks/{task_id}/labels", json={"label_id": label_id})
            except VikunjaAPIError:
                continue

    def create_task(
        self,
        *,
        title: str,
        description: str | None = None,
        due_date: datetime | str | None = None,
        start_date: datetime | str | None = None,
        project_id: str | None = None,
        label_titles: list[str] | None = None,
        priority: int | None = None,
    ) -> dict[str, Any]:
        target_project_id = project_id or self.config.require_default_project_id()
        payload: dict[str, Any] = {"title": title}
        if description:
            payload["description"] = description
        if due_date:
            payload["due_date"] = isoformat_for_vikunja(due_date)
        if start_date:
            payload["start_date"] = isoformat_for_vikunja(start_date)
        if priority is not None:
            payload["priority"] = priority
        task = self._request("PUT", f"/projects/{target_project_id}/tasks", json=payload)
        if not isinstance(task, dict):
            raise VikunjaAPIError("Vikunja returned an unexpected create payload")
        labels = [self.ensure_label(label) for label in (label_titles or [])]
        if labels:
            self.set_task_labels(str(task.get("id")), [str(label.get("id")) for label in labels if label.get("id") is not None])
            task["labels"] = labels
        return task

    def update_task(self, task_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_task(task_id)
        payload = {**existing, **changes}
        task = self._request("POST", f"/tasks/{task_id}", json=payload)
        if not isinstance(task, dict):
            raise VikunjaAPIError("Vikunja returned an unexpected update payload")
        return task

    def complete_task(self, task_id: str) -> dict[str, Any]:
        return self.update_task(task_id, {"done": True})

    def reopen_task(self, task_id: str) -> dict[str, Any]:
        return self.update_task(task_id, {"done": False, "done_at": None})

    def delete_task(self, task_id: str) -> None:
        self._request("DELETE", f"/tasks/{task_id}")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.config.api_url}{path}"
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
            raise VikunjaAPIError(f"Vikunja request timed out: {method} {path}") from exc
        except httpx.RequestError as exc:
            raise VikunjaAPIError(f"Vikunja request failed: {exc}") from exc

        if response.status_code >= 400:
            raise VikunjaAPIError(
                f"Vikunja request failed ({response.status_code}): {readable_error(response)}",
                status_code=response.status_code,
            )
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise VikunjaAPIError("Vikunja returned invalid JSON") from exc


def normalize_vikunja_api_url(raw_url: str) -> str:
    value = raw_url.strip().rstrip("/")
    if not value:
        raise VikunjaConfigurationError("VIKUNJA_URL is empty")
    if value.endswith("/api/v1"):
        return value
    if value.endswith("/api"):
        return f"{value}/v1"
    return f"{value}/api/v1"


def normalize_task(task: dict[str, Any], project_titles: dict[str, str] | None = None) -> NormalizedVikunjaTask:
    external_id = str(task.get("id") or "").strip()
    if not external_id:
        raise VikunjaAPIError("Vikunja task is missing an id")
    project_id = optional_str(task.get("project_id"))
    project_title = (project_titles or {}).get(project_id or "")
    return NormalizedVikunjaTask(
        id=external_id,
        external_id=external_id,
        title=str(task.get("title") or "untitled task").strip() or "untitled task",
        notes=optional_str(task.get("description")),
        status="done" if bool(task.get("done")) else "open",
        due_at=parse_vikunja_datetime(task.get("due_date")),
        scheduled_for=parse_vikunja_datetime(task.get("start_date")),
        tags=task_labels(task),
        priority=optional_int(task.get("priority")),
        provider="vikunja",
        project_id=project_id,
        project_title=project_title or (f"project {project_id}" if project_id else None),
        created_at=parse_vikunja_datetime(task.get("created")),
        updated_at=parse_vikunja_datetime(task.get("updated")),
        completed_at=parse_vikunja_datetime(task.get("done_at")),
        raw=task,
    )


def task_labels(task: dict[str, Any]) -> list[str]:
    labels = task.get("labels")
    if not isinstance(labels, list):
        return []
    titles: list[str] = []
    for label in labels:
        if isinstance(label, dict):
            title = optional_str(label.get("title"))
            if title:
                titles.append(title)
    return titles


def parse_vikunja_datetime(value: object) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text or text.startswith("0001-01-01"):
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def isoformat_for_vikunja(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


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


def vikunja_token_from_env() -> str:
    token = os.getenv("VIKUNJA_TOKEN", "").strip()
    if token:
        return token
    token_file = os.getenv("VIKUNJA_TOKEN_FILE", "").strip()
    if not token_file:
        return ""
    path = Path(token_file).expanduser()
    try:
        file_token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise VikunjaConfigurationError(f"Could not read VIKUNJA_TOKEN_FILE {path}: {exc.strerror}") from exc
    if not file_token:
        raise VikunjaConfigurationError(f"VIKUNJA_TOKEN_FILE {path} is empty")
    return file_token


def readable_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:500] or response.reason_phrase
    if isinstance(payload, dict):
        for key in ("message", "detail", "error"):
            value = payload.get(key)
            if value:
                return str(value)
    return str(payload)[:500]


def vikunja_status() -> dict[str, Any]:
    raw_url = os.getenv("VIKUNJA_URL", "").strip()
    configuration_error = None
    try:
        token = vikunja_token_from_env()
    except VikunjaConfigurationError as exc:
        token = ""
        configuration_error = str(exc)
    default_project_id = (
        os.getenv("VIKUNJA_DEFAULT_PROJECT_ID", "").strip()
        or os.getenv("VIKUNJA_PROJECT_ID", "").strip()
        or None
    )
    status = {
        "configured": bool(raw_url and token),
        "url": normalize_vikunja_api_url(raw_url) if raw_url else None,
        "default_project_configured": default_project_id is not None,
        "provider": "vikunja",
        "token_file_configured": bool(os.getenv("VIKUNJA_TOKEN_FILE", "").strip()),
    }
    if configuration_error:
        status["configuration_error"] = configuration_error
    return status
