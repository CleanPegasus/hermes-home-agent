from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeVikunja:
    token = "test-vikunja-token"
    default_project_id = "7"

    def __init__(self) -> None:
        self.tasks: dict[str, dict] = {}
        self.labels: dict[str, dict] = {
            "3": {"id": 3, "title": "groceries", "hex_color": "#4CAF50"},
            "4": {"id": 4, "title": "urgent", "hex_color": "#E51400"},
        }
        self.projects: list[dict] = [
            {"id": 7, "title": "home", "hex_color": "#1BA1E2"},
            {"id": 8, "title": "errands", "hex_color": "#4CAF50"},
        ]
        self.calls: list[dict] = []
        self._next_id = 1
        self._next_label_id = 10

    @property
    def url(self) -> str:
        return "http://fake-vikunja.test"

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def request(self, method: str, url: str, headers: dict[str, str], body: dict | None = None) -> httpx.Response:
        parsed = urlparse(url)
        payload = body or {}
        self.calls.append({"method": method, "path": parsed.path, "query": parse_qs(parsed.query), "body": payload})
        if headers.get("authorization") != f"Bearer {self.token}":
            return httpx.Response(401, json={"message": "missing, malformed, expired or otherwise invalid token provided"})
        parts = parsed.path.strip("/").split("/")
        if parts == ["api", "v1", "projects"] and method == "GET":
            return httpx.Response(200, json=self.projects)
        if parts == ["api", "v1", "labels"] and method == "GET":
            return httpx.Response(200, json=list(self.labels.values()))
        if parts == ["api", "v1", "labels"] and method == "PUT":
            label_id = str(self._next_label_id)
            self._next_label_id += 1
            label = {"id": int(label_id), "title": payload["title"], "hex_color": payload.get("hex_color", "")}
            self.labels[label_id] = label
            return httpx.Response(201, json=label)
        if parts == ["api", "v1", "tasks"] and method == "GET":
            return httpx.Response(200, json=list(self.tasks.values()))
        if len(parts) == 5 and parts[:3] == ["api", "v1", "tasks"] and parts[4] == "labels" and method == "PUT":
            task = self.tasks.get(parts[3])
            if not task:
                return httpx.Response(404, json={"message": "task not found"})
            label_id = str(payload.get("label_id") or payload.get("id"))
            label = self.labels.get(label_id)
            if label and label not in task["labels"]:
                task["labels"].append(label)
            return httpx.Response(200, json=task)
        if len(parts) == 5 and parts[:3] == ["api", "v1", "projects"] and parts[4] == "tasks" and method == "PUT":
            return httpx.Response(201, json=self.create_task(parts[3], payload))
        if len(parts) == 4 and parts[:3] == ["api", "v1", "tasks"]:
            task_id = parts[3]
            if method == "GET":
                task = self.tasks.get(task_id)
                return httpx.Response(200, json=task) if task else httpx.Response(404, json={"message": "task not found"})
            if method == "POST":
                return httpx.Response(200, json=self.update_task(task_id, payload))
            if method == "DELETE":
                self.tasks.pop(task_id, None)
                return httpx.Response(200, json={"message": "deleted"})
        return httpx.Response(404, json={"message": "not found"})

    def httpx_client(self):
        fake = self

        class FakeClient:
            def __init__(self, *args: object, **kwargs: object) -> None:
                return

            def __enter__(self) -> "FakeClient":
                return self

            def __exit__(self, *args: object) -> None:
                return

            def request(
                self,
                method: str,
                url: str,
                headers: dict[str, str],
                json: dict[str, Any] | None = None,
                params: dict[str, Any] | None = None,
            ) -> httpx.Response:
                return fake.request(method, url, headers, json)

        return FakeClient

    def create_task(self, project_id: str, body: dict) -> dict:
        task_id = str(self._next_id)
        self._next_id += 1
        now = datetime.now(timezone.utc).isoformat()
        task = {
            "id": int(task_id),
            "project_id": int(project_id),
            "title": body.get("title", "untitled task"),
            "description": body.get("description", ""),
            "done": bool(body.get("done", False)),
            "done_at": body.get("done_at"),
            "due_date": body.get("due_date"),
            "start_date": body.get("start_date"),
            "labels": body.get("labels", []),
            "priority": body.get("priority"),
            "created": now,
            "updated": now,
        }
        self.tasks[task_id] = task
        return task

    def update_task(self, task_id: str, body: dict) -> dict:
        if task_id not in self.tasks:
            return {"message": "task not found"}
        now = datetime.now(timezone.utc).isoformat()
        task = {**self.tasks[task_id], **body, "id": int(task_id), "updated": now}
        if task.get("done") and not task.get("done_at"):
            task["done_at"] = now
        if not task.get("done"):
            task["done_at"] = None
        self.tasks[task_id] = task
        return task


@pytest.fixture
def fake_vikunja(monkeypatch: pytest.MonkeyPatch) -> FakeVikunja:
    server = FakeVikunja()
    server.start()
    import app.vikunja as vikunja

    monkeypatch.setattr(vikunja.httpx, "Client", server.httpx_client())
    try:
        yield server
    finally:
        server.stop()


def build_app(tmp_path: Path, agent_cmd: str | None = None, vikunja: FakeVikunja | None = None):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'hermes-home-test.db'}"
    os.environ["HOME_API_TOKEN"] = "test-token"
    os.environ["HERMES_ENV"] = "test"
    os.environ.pop("CODEX_ENABLED", None)
    os.environ.pop("PUBLIC_BASE_URL", None)
    os.environ.pop("SERVER_HOST", None)
    os.environ.pop("VITE_API_BASE", None)
    if agent_cmd:
        os.environ["AGENT_CMD"] = agent_cmd
    else:
        os.environ.pop("AGENT_CMD", None)
    if vikunja:
        os.environ.pop("VIKUNJA_TOKEN_FILE", None)
        os.environ["VIKUNJA_URL"] = vikunja.url
        os.environ["VIKUNJA_TOKEN"] = vikunja.token
        os.environ["VIKUNJA_DEFAULT_PROJECT_ID"] = vikunja.default_project_id
    else:
        os.environ.pop("VIKUNJA_URL", None)
        os.environ.pop("VIKUNJA_TOKEN", None)
        os.environ.pop("VIKUNJA_TOKEN_FILE", None)
        os.environ.pop("VIKUNJA_DEFAULT_PROJECT_ID", None)
        os.environ.pop("VIKUNJA_PROJECT_ID", None)
    os.environ.pop("HERMES_CALENDAR_EVENTS_JSON", None)
    os.environ.pop("HERMES_CHANNEL_MESSAGES_JSON", None)
    os.environ.pop("HERMES_SPEND_ITEMS_JSON", None)

    import app.main as main

    importlib.reload(main)
    return main.create_app()


def build_client(tmp_path: Path, agent_cmd: str | None = None, vikunja: FakeVikunja | None = None) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=build_app(tmp_path, agent_cmd=agent_cmd, vikunja=vikunja))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def test_run_home_agent_syncs_vikunja_env_to_mcp_profile(tmp_path: Path) -> None:
    yaml = pytest.importorskip("yaml")
    env_file = tmp_path / ".env"
    profile_config = tmp_path / "profile" / "config.yaml"
    env_file.write_text(
        "\n".join(
            [
                "HOME_API_TOKEN=test-token",
                f"DATABASE_URL=sqlite:///{tmp_path / 'home.db'}",
                "HERMES_HOME_JOB_ID=",
                "VIKUNJA_URL=http://127.0.0.1:3456",
                "VIKUNJA_TOKEN=test-vikunja-token",
                "VIKUNJA_DEFAULT_PROJECT_ID=2",
                "VIKUNJA_TIMEOUT_SECONDS=3",
            ]
        )
        + "\n"
    )
    profile_config.parent.mkdir(parents=True)
    profile_config.write_text(
        "\n".join(
            [
                "mcp_servers:",
                "  hermes-home:",
                "    env:",
                "      VIKUNJA_TOKEN_FILE: /stale/token",
            ]
        )
        + "\n"
    )

    env = os.environ.copy()
    env.update(
        {
            "HERMES_HOME_COMMAND": "add replace filter to my todos",
            "HERMES_HOME_JOB_ID": "job-123",
            "HERMES_HOME_ENV_FILE": str(env_file),
            "HERMES_HOME_PROFILE_CONFIG": str(profile_config),
            "HERMES_HOME_PROFILE_PYTHON": sys.executable,
            "HERMES_HOME_UPDATE_PROFILE_ONLY": "1",
        }
    )

    subprocess.run(
        [str(Path(__file__).resolve().parents[2] / "bin" / "run-home-agent")],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    data = yaml.safe_load(profile_config.read_text())
    mcp_env = data["mcp_servers"]["hermes-home"]["env"]
    assert mcp_env["DATABASE_URL"] == f"sqlite:///{tmp_path / 'home.db'}"
    assert mcp_env["HOME_API_TOKEN"] == "test-token"
    assert mcp_env["HERMES_HOME_JOB_ID"] == "job-123"
    assert mcp_env["HERMES_HOME_COMMAND"] == "add replace filter to my todos"
    assert mcp_env["VIKUNJA_URL"] == "http://127.0.0.1:3456"
    assert mcp_env["VIKUNJA_TOKEN"] == "test-vikunja-token"
    assert mcp_env["VIKUNJA_DEFAULT_PROJECT_ID"] == "2"
    assert mcp_env["VIKUNJA_TIMEOUT_SECONDS"] == "3"
    assert "VIKUNJA_TOKEN_FILE" not in mcp_env


def test_run_home_agent_preserves_active_app_env_over_env_file(tmp_path: Path) -> None:
    yaml = pytest.importorskip("yaml")
    env_file = tmp_path / ".env"
    profile_config = tmp_path / "profile" / "config.yaml"
    env_file.write_text(
        "\n".join(
            [
                "HOME_API_TOKEN=stale-token",
                f"DATABASE_URL=sqlite:///{tmp_path / 'stale.db'}",
                "HERMES_HOME_JOB_ID=",
                "HERMES_HOME_COMMAND=",
            ]
        )
        + "\n"
    )

    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{tmp_path / 'active.db'}",
            "HOME_API_TOKEN": "active-token",
            "HERMES_HOME_COMMAND": "add active env to my todos",
            "HERMES_HOME_JOB_ID": "active-job-123",
            "HERMES_HOME_ENV_FILE": str(env_file),
            "HERMES_HOME_PROFILE_CONFIG": str(profile_config),
            "HERMES_HOME_PROFILE_PYTHON": sys.executable,
            "HERMES_HOME_UPDATE_PROFILE_ONLY": "1",
        }
    )

    subprocess.run(
        [str(Path(__file__).resolve().parents[2] / "bin" / "run-home-agent")],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    data = yaml.safe_load(profile_config.read_text())
    mcp_env = data["mcp_servers"]["hermes-home"]["env"]
    assert mcp_env["DATABASE_URL"] == f"sqlite:///{tmp_path / 'active.db'}"
    assert mcp_env["HOME_API_TOKEN"] == "active-token"
    assert mcp_env["HERMES_HOME_JOB_ID"] == "active-job-123"
    assert mcp_env["HERMES_HOME_COMMAND"] == "add active env to my todos"


def test_vikunja_config_accepts_token_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_file = tmp_path / "vikunja.token"
    token_file.write_text("file-token\n")
    monkeypatch.setenv("VIKUNJA_URL", "http://127.0.0.1:3456")
    monkeypatch.delenv("VIKUNJA_TOKEN", raising=False)
    monkeypatch.setenv("VIKUNJA_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("VIKUNJA_DEFAULT_PROJECT_ID", "2")

    from app.vikunja import VikunjaConfig, vikunja_status

    config = VikunjaConfig.from_env()
    status = vikunja_status()

    assert config.token == "file-token"
    assert config.default_project_id == "2"
    assert status["configured"] is True
    assert status["token_file_configured"] is True


def test_mcp_vikunja_normalize_accepts_null_labels() -> None:
    module_path = Path(__file__).resolve().parents[2] / "mcp" / "hermes_home_mcp" / "server.py"
    spec = importlib.util.spec_from_file_location("hermes_home_mcp_test_server", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    task = module.normalize_vikunja_task({"id": 1, "title": "test task", "labels": None})

    assert task["external_id"] == "1"
    assert task["tags"] == []


async def wait_for_job(client: httpx.AsyncClient, job_id: str, attempts: int = 40) -> dict:
    job: dict | None = None
    for _ in range(attempts):
        response = await client.get(f"/api/jobs/{job_id}", headers=auth_headers())
        assert response.status_code == 200
        job = response.json()["job"]
        if job["status"] in {"done", "failed", "needs_approval", "cancelled"}:
            return job
        await asyncio.sleep(0.05)
    assert job is not None
    return job


@pytest.mark.anyio
async def test_api_requires_bearer_token(tmp_path: Path) -> None:
    async with build_client(tmp_path) as client:
        response = await client.get("/api/tiles")

        assert response.status_code == 401
        assert response.json()["detail"] == "missing bearer token"


@pytest.mark.anyio
async def test_seed_tiles_are_returned_in_sort_order(tmp_path: Path) -> None:
    async with build_client(tmp_path) as client:
        response = await client.get("/api/tiles", headers=auth_headers())

        assert response.status_code == 200
        payload = response.json()
    assert [tile["key"] for tile in payload["tiles"][:5]] == [
        "jobs",
        "todos",
        "calendar",
        "notes",
        "approvals",
    ]
    assert payload["tiles"][0]["front"]["line"] == "ready"
    assert payload["tiles"][0]["front"]["emoji"] == "⚙️"
    assert payload["tiles"][1]["front"]["emoji"] == "✅"
    assert payload["tiles"][1]["size"] == "m"


@pytest.mark.anyio
async def test_todos_degrade_when_vikunja_configuration_is_missing(tmp_path: Path) -> None:
    async with build_client(tmp_path) as client:
        response = await client.get("/api/todos", headers=auth_headers())

        assert response.status_code == 200
        payload = response.json()
        assert payload["todos"] == []
        assert payload["configured"] is False
        assert payload["status"]["provider"] == "vikunja"
        assert "VIKUNJA_URL" in payload["warning"]

        tiles = (await client.get("/api/tiles", headers=auth_headers())).json()["tiles"]
        todos_tile = next(tile for tile in tiles if tile["key"] == "todos")
        assert todos_tile["front"]["line"] == "setup"
        assert todos_tile["front"]["sub"] == "connect Vikunja"


@pytest.mark.anyio
async def test_command_creates_vikunja_todo_events_page_and_tile_updates(tmp_path: Path, fake_vikunja: FakeVikunja) -> None:
    async with build_client(tmp_path, vikunja=fake_vikunja) as client:
        command_response = await client.post(
            "/api/command",
            headers=auth_headers(),
            json={"text": "add buy oat milk tomorrow to my todos"},
        )

        assert command_response.status_code == 200
        job_id = command_response.json()["job_id"]

        job = await wait_for_job(client, job_id)
        assert job["status"] == "done"
        assert job["page_id"] is not None

        events_response = await client.get(f"/api/jobs/{job_id}/events", headers=auth_headers())
        assert events_response.status_code == 200
        event_text = events_response.text
        assert "event: step" in event_text
        assert "reading command" in event_text
        assert "publishing page" in event_text

        stream_response = await client.get(f"/api/jobs/{job_id}/stream", headers=auth_headers())
        assert stream_response.status_code == 200
        assert "publishing page" in stream_response.text

        timeline_response = await client.get(f"/api/jobs/{job_id}/timeline", headers=auth_headers())
        assert timeline_response.status_code == 200
        assert [event["text"] for event in timeline_response.json()["events"]][-1] == "publishing page"

        diagnostics_response = await client.get(f"/api/jobs/{job_id}/diagnostics", headers=auth_headers())
        assert diagnostics_response.status_code == 200
        diagnostics = diagnostics_response.json()
        assert diagnostics["page"]["html_bytes"] > 0
        assert diagnostics["environment"]["database"] == "sqlite"

        page_response = await client.get(f"/api/pages/{job['page_id']}", headers=auth_headers())
        assert page_response.status_code == 200
        page = page_response.json()["page"]
        assert "buy oat milk" in page["html"]
        assert "<script" not in page["html"].lower()
        assert "onclick=" not in page["html"].lower()
        assert "data-action=\"todos.complete\"" in page["html"]
        assert page["provenance"]["reads"][0]["type"] == "command"
        assert any(write["type"] == "todo" for write in page["provenance"]["writes"])
        assert any(write["type"] == "page" for write in page["provenance"]["writes"])
        assert page["provenance"]["skipped"][0]["type"] == "external_agent"

        todos_response = await client.get("/api/todos", headers=auth_headers())
        assert todos_response.status_code == 200
        todos = todos_response.json()["todos"]
        assert todos[0]["title"] == "buy oat milk"
        assert todos[0]["status"] == "open"
        assert todos[0]["provider"] == "vikunja"
        assert todos[0]["external_id"] == "1"
        expected_due_date = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
        assert todos[0]["due_at"].startswith(expected_due_date)

        create_call = next(call for call in fake_vikunja.calls if call["method"] == "PUT")
        assert create_call["path"] == f"/api/v1/projects/{fake_vikunja.default_project_id}/tasks"
        assert create_call["body"]["title"] == "buy oat milk"
        assert create_call["body"]["due_date"].startswith(expected_due_date)

        tiles_response = await client.get("/api/tiles", headers=auth_headers())
        todos_tile = next(tile for tile in tiles_response.json()["tiles"] if tile["key"] == "todos")
        assert todos_tile["front"]["count"] == 1


@pytest.mark.anyio
async def test_page_action_completes_vikunja_todo_and_refreshes_tile(tmp_path: Path, fake_vikunja: FakeVikunja) -> None:
    async with build_client(tmp_path, vikunja=fake_vikunja) as client:
        command_response = await client.post(
            "/api/command",
            headers=auth_headers(),
            json={"text": "add replace filter to my todos"},
        )
        job_id = command_response.json()["job_id"]
        job = await wait_for_job(client, job_id)
        page = (await client.get(f"/api/pages/{job['page_id']}", headers=auth_headers())).json()["page"]
        todo_id = (await client.get("/api/todos", headers=auth_headers())).json()["todos"][0]["id"]

        response = await client.post(
            "/api/actions",
            headers=auth_headers(),
            json={
                "action": "todos.complete",
                "payload": {"todo_id": todo_id, "page_id": page["id"], "job_id": job_id},
                "idempotency_key": "complete-filter",
            },
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True
        replay = await client.post(
            "/api/actions",
            headers=auth_headers(),
            json={
                "action": "todos.complete",
                "payload": {"todo_id": todo_id, "page_id": page["id"], "job_id": job_id},
                "idempotency_key": "complete-filter",
            },
        )
        assert replay.status_code == 200
        assert replay.json()["idempotent_replay"] is True
        filtered_runs = (
            await client.get(
                f"/api/action-runs?action=todos.complete&status=done&source_job_id={job_id}&source_page_id={page['id']}",
                headers=auth_headers(),
            )
        ).json()["action_runs"]
        assert len(filtered_runs) == 1
        assert filtered_runs[0]["source_job_id"] == job_id
        assert filtered_runs[0]["source_page_id"] == page["id"]
        assert "todos.complete" in filtered_runs[0]["summary"]
        todos = (await client.get("/api/todos", headers=auth_headers())).json()["todos"]
        assert todos[0]["status"] == "done"
        complete_call = [call for call in fake_vikunja.calls if call["method"] == "POST" and call["path"] == "/api/v1/tasks/1"][-1]
        assert complete_call["body"]["done"] is True
        tiles = (await client.get("/api/tiles", headers=auth_headers())).json()["tiles"]
        todos_tile = next(tile for tile in tiles if tile["key"] == "todos")
        assert todos_tile["front"]["count"] == 0
        assert todos_tile["back"]["line"] == "last finished"

        pinned = await client.post(f"/api/pages/{page['id']}/pin", headers=auth_headers())
        assert pinned.status_code == 200
        assert pinned.json()["page"]["pinned_at"] is not None
        pages = (await client.get("/api/pages", headers=auth_headers())).json()["pages"]
        assert pages[0]["id"] == page["id"]


@pytest.mark.anyio
async def test_local_todo_rows_are_not_authoritative(tmp_path: Path, fake_vikunja: FakeVikunja) -> None:
    app = build_app(tmp_path, vikunja=fake_vikunja)
    from app.models import Todo

    with app.state.session_factory() as session:
        session.add(Todo(title="local-only task", status="open", source="agent"))
        session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        todos_response = await client.get("/api/todos", headers=auth_headers())
        assert todos_response.status_code == 200
        assert todos_response.json()["todos"] == []

        vitals = (await client.get("/api/vitals", headers=auth_headers())).json()
        assert vitals["counts"]["todos_open"] == 0


def test_create_todo_passes_project_labels_and_priority(tmp_path: Path, fake_vikunja: FakeVikunja) -> None:
    app = build_app(tmp_path, vikunja=fake_vikunja)
    from app.todo_provider import create_todo

    with app.state.session_factory() as session:
        todo = create_todo(
            session,
            title="Buy oat milk",
            project_id="8",
            label_titles=["groceries", "pantry"],
            priority=5,
        )
        session.commit()

    create_call = next(call for call in fake_vikunja.calls if call["method"] == "PUT" and call["path"].endswith("/projects/8/tasks"))
    assert create_call["body"]["priority"] == 5
    assert todo.project_id == "8"
    assert todo.project_title == "errands"
    assert todo.tags == ["groceries", "pantry"]
    assert todo.priority == 5
    assert any(call["path"].endswith(f"/tasks/{todo.external_id}/labels") for call in fake_vikunja.calls)


@pytest.mark.anyio
async def test_todos_response_includes_projects_labels_and_priority(tmp_path: Path, fake_vikunja: FakeVikunja) -> None:
    fake_vikunja.create_task("8", {"title": "buy oat milk", "priority": 4, "labels": [fake_vikunja.labels["3"]]})
    async with build_client(tmp_path, vikunja=fake_vikunja) as client:
        response = await client.get("/api/todos", headers=auth_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["projects"][1]["title"] == "errands"
    assert payload["labels"][0]["title"] == "groceries"
    assert payload["todos"][0]["project"] == "errands"
    assert payload["todos"][0]["tags"] == ["groceries"]
    assert payload["todos"][0]["priority"] == 4


def test_agent_environment_includes_profile_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.jobs import agent_environment
    from app.models import AgentProfile, Job

    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp.db")
    monkeypatch.setenv("HOME_API_TOKEN", "token-1")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", "/srv/hermes/vault")
    job = Job(id="00000000-0000-0000-0000-000000000001", command="write code", status="queued")
    profile = AgentProfile(
        id="00000000-0000-0000-0000-000000000002",
        slug="coding",
        name="coding agent",
        emoji="💻",
        color="#1BA1E2",
        persona="Prefer precise implementation notes.",
        is_default=False,
    )

    env = agent_environment(job, profile)

    assert env["HERMES_HOME_JOB_ID"] == "00000000000000000000000000000001"
    assert env["HERMES_HOME_COMMAND"] == "write code"
    assert env["HERMES_HOME_PROFILE_ID"] == "00000000-0000-0000-0000-000000000002"
    assert env["HERMES_HOME_PROFILE_NAME"] == "coding agent"
    assert env["HERMES_HOME_PROFILE_PERSONA"] == "Prefer precise implementation notes."
    assert env["OBSIDIAN_VAULT_PATH"] == "/srv/hermes/vault"


def test_agent_environment_absolutizes_relative_sqlite_database_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.jobs import agent_environment
    from app.models import Job

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./hermes-home-dev.db")
    job = Job(id="00000000-0000-0000-0000-000000000001", command="write code", status="queued")

    env = agent_environment(job)

    assert env["DATABASE_URL"] == f"sqlite:///{tmp_path / 'hermes-home-dev.db'}"
    assert env["HERMES_HOME_JOB_ID"] == "00000000000000000000000000000001"


@pytest.mark.anyio
async def test_profile_crud_default_and_job_filter(tmp_path: Path) -> None:
    async with build_client(tmp_path) as client:
        initial = (await client.get("/api/profiles", headers=auth_headers())).json()
        assert len(initial["profiles"]) >= 1
        default_id = initial["default_id"]

        created_response = await client.post(
            "/api/profiles",
            headers=auth_headers(),
            json={"name": "Coding Agent", "emoji": "💻", "color": "#1BA1E2", "persona": "Use repo context."},
        )
        assert created_response.status_code == 200
        created = created_response.json()["profile"]

        patched = await client.patch(
            f"/api/profiles/{created['id']}",
            headers=auth_headers(),
            json={"is_default": True, "persona": "Use tests first."},
        )
        assert patched.status_code == 200
        profiles = (await client.get("/api/profiles", headers=auth_headers())).json()
        assert profiles["default_id"] == created["id"]
        assert next(profile for profile in profiles["profiles"] if profile["id"] == default_id)["is_default"] is False

        blocked = await client.delete(f"/api/profiles/{created['id']}", headers=auth_headers())
        assert blocked.status_code == 409

        command_response = await client.post(
            "/api/command",
            headers=auth_headers(),
            json={"text": "add profile test to my todos", "profile_id": created["id"]},
        )
        job_id = command_response.json()["job_id"]
        job = (await client.get(f"/api/jobs/{job_id}", headers=auth_headers())).json()["job"]
        filtered = (await client.get(f"/api/jobs?profile_id={created['id']}", headers=auth_headers())).json()["jobs"]

    assert job["profile_id"] == created["id"]
    assert job["profile"]["emoji"] == "💻"
    assert [item["id"] for item in filtered] == [job_id]


@pytest.mark.anyio
async def test_command_returns_before_slow_external_agent_finishes(tmp_path: Path) -> None:
    fake_agent = tmp_path / "fake-agent"
    fake_agent.write_text("#!/bin/sh\nsleep 0.8\necho no page published\n")
    fake_agent.chmod(0o755)

    async with build_client(tmp_path, agent_cmd=str(fake_agent)) as client:
        started = time.perf_counter()
        command_response = await client.post(
            "/api/command",
            headers=auth_headers(),
            json={"text": "do a slow external thing"},
        )
        elapsed = time.perf_counter() - started

        assert command_response.status_code == 200
        assert elapsed < 0.5
        session_response = await client.get("/api/session", headers=auth_headers())
        assert session_response.status_code == 200

        job = await wait_for_job(client, command_response.json()["job_id"], attempts=40)
        assert job["status"] == "failed"
        assert "no page published" in job["error"]


@pytest.mark.anyio
async def test_external_agent_can_publish_page_after_parent_polling_starts(tmp_path: Path) -> None:
    fake_agent = tmp_path / "fake-publishing-agent.py"
    fake_agent.write_text(
        "\n".join(
            [
                "import asyncio",
                "import sys",
                "import time",
                f"sys.path.insert(0, {str(Path(__file__).resolve().parents[2] / 'mcp')!r})",
                "from hermes_home_mcp.server import pages_publish",
                "time.sleep(0.7)",
                "asyncio.run(pages_publish('published externally', '<p>done</p>'))",
                "time.sleep(0.7)",
            ]
        )
        + "\n"
    )

    async with build_client(tmp_path, agent_cmd=f"{sys.executable} {fake_agent}") as client:
        command_response = await client.post(
            "/api/command",
            headers=auth_headers(),
            json={"text": "publish a page externally"},
        )

        assert command_response.status_code == 200
        job = await wait_for_job(client, command_response.json()["job_id"], attempts=30)
        assert job["status"] == "done"
        assert job["page_id"] is not None


@pytest.mark.anyio
async def test_session_capabilities_categories_and_approvals(tmp_path: Path) -> None:
    async with build_client(tmp_path) as client:
        session_response = await client.get("/api/session", headers=auth_headers())
        assert session_response.status_code == 200
        assert session_response.json()["agent"]["configured"] is False

        capabilities = (await client.get("/api/capabilities", headers=auth_headers())).json()
        assert "todos.complete" in {action["name"] for action in capabilities["actions"]}
        assert "approvals" in capabilities["tiles"]

        categories = (await client.get("/api/categories", headers=auth_headers())).json()["categories"]
        assert {category["slug"] for category in categories} == {"inbox", "home", "errands", "health", "reference"}

        approval_response = await client.post(
            "/api/actions",
            headers=auth_headers(),
            json={
                "action": "approvals.request",
                "payload": {
                    "action_name": "calendar.create_event",
                    "scope": {"summary": "dentist", "starts_at": "2026-06-16T16:00:00+00:00", "ends_at": "2026-06-16T17:00:00+00:00"},
                },
            },
        )
        assert approval_response.status_code == 200
        approval_id = approval_response.json()["approval_id"]
        approvals = (await client.get("/api/approvals", headers=auth_headers())).json()["approvals"]
        assert approvals[0]["status"] == "pending"

        approve_response = await client.post(f"/api/approvals/{approval_id}/approve", headers=auth_headers())
        assert approve_response.status_code == 200
        assert approve_response.json()["status"] == "approved"
        assert approve_response.json()["result"]["executed"] is True

        calendar = (await client.get("/api/calendar", headers=auth_headers())).json()
        assert calendar["adapter"] == "local.calendar_events"
        assert calendar["events"][0]["summary"] == "dentist"

        action_runs = (await client.get("/api/action-runs", headers=auth_headers())).json()["action_runs"]
        assert isinstance(action_runs, list)

        vitals = (await client.get("/api/vitals", headers=auth_headers())).json()
        assert vitals["counts"]["calendar_events"] == 1

        channels = (await client.get("/api/channels", headers=auth_headers())).json()
        spend = (await client.get("/api/spend", headers=auth_headers())).json()
        assert channels["configured"] is False
        assert spend["total_cents"] == 0


@pytest.mark.anyio
async def test_connector_json_sync_imports_local_read_models(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    calendar_path = tmp_path / "calendar.json"
    channels_path = tmp_path / "channels.json"
    spend_path = tmp_path / "spend.json"
    calendar_path.write_text('[{"summary":"lunch","starts_at":"2026-06-18T12:00:00+00:00"}]')
    channels_path.write_text('[{"channel":"mail","sender":"a@example.test","subject":"hello","body":"world"}]')
    spend_path.write_text('[{"merchant":"market","amount_cents":1299,"category":"groceries"}]')
    os.environ["HERMES_CALENDAR_EVENTS_JSON"] = str(calendar_path)
    os.environ["HERMES_CHANNEL_MESSAGES_JSON"] = str(channels_path)
    os.environ["HERMES_SPEND_ITEMS_JSON"] = str(spend_path)

    try:
        async with client:
            sync = await client.post("/api/connectors/sync", headers=auth_headers())
            assert sync.status_code == 200
            sync_payload = sync.json()
            assert sync_payload["result"]["calendar"]["imported"] == 1
            assert sync_payload["result"]["calendar"]["status"] == "success"
            assert sync_payload["connectors"]["calendar"]["last_sync"]["status"] == "success"
            assert len(sync_payload["history"]) == 3

            calendar = (await client.get("/api/calendar", headers=auth_headers())).json()
            channels = (await client.get("/api/channels", headers=auth_headers())).json()
            spend = (await client.get("/api/spend", headers=auth_headers())).json()
            assert calendar["events"][0]["summary"] == "lunch"
            assert channels["messages"][0]["subject"] == "hello"
            assert spend["items"][0]["merchant"] == "market"
            assert spend["total_cents"] == 1299

            repeat_sync = await client.post("/api/connectors/sync", headers=auth_headers())
            assert repeat_sync.status_code == 200
            assert repeat_sync.json()["result"]["calendar"]["status"] == "success"
            assert len((await client.get("/api/calendar", headers=auth_headers())).json()["events"]) == 1
            assert len((await client.get("/api/channels", headers=auth_headers())).json()["messages"]) == 1
            assert len((await client.get("/api/spend", headers=auth_headers())).json()["items"]) == 1

            spend_path.write_text("{bad json")
            failed_sync = await client.post("/api/connectors/sync", headers=auth_headers())
            assert failed_sync.status_code == 200
            failed_payload = failed_sync.json()
            assert failed_payload["result"]["spend"]["status"] == "error"
            assert "Expecting property name" in failed_payload["result"]["spend"]["error"]
            assert failed_payload["connectors"]["spend"]["last_sync"]["status"] == "error"
    finally:
        os.environ.pop("HERMES_CALENDAR_EVENTS_JSON", None)
        os.environ.pop("HERMES_CHANNEL_MESSAGES_JSON", None)
        os.environ.pop("HERMES_SPEND_ITEMS_JSON", None)


@pytest.mark.anyio
async def test_note_detail_update_merge_and_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path / "vault"))
    app = build_app(tmp_path)
    from app.vault import VaultStore

    vault = VaultStore(tmp_path / "vault")
    first = vault.create("hallway filter", "size is 20x25x1", category="home", tags=["hvac"])
    second = vault.create("filter reminder", "replace quarterly", category="home")
    first_id = first["id"]
    second_id = second["id"]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        list_response = await client.get("/api/notes?category=home&q=filter", headers=auth_headers())
        assert list_response.status_code == 200
        assert list_response.json()["configured"] is True
        listed_first = next(note for note in list_response.json()["notes"] if note["id"] == first_id)
        assert listed_first["category"] == "home"
        assert listed_first["tags"] == ["hvac"]

        detail = await client.get(f"/api/notes/{first_id}", headers=auth_headers())
        assert detail.status_code == 200
        assert detail.json()["note"]["title"] == "hallway filter"

        update = await client.patch(
            f"/api/notes/{first_id}",
            headers=auth_headers(),
            json={"title": "hallway hvac filter", "body_md": "20x25x1 filter", "category": "health", "tags": ["hvac", "home"]},
        )
        assert update.status_code == 200
        assert update.json()["note"]["title"] == "hallway hvac filter"
        assert update.json()["note"]["category"] == "health"
        assert update.json()["note"]["tags"] == ["hvac", "home"]

        merge = await client.post(
            f"/api/notes/{second_id}/merge",
            headers=auth_headers(),
            json={"target_note_id": first_id},
        )
        assert merge.status_code == 200
        assert "replace quarterly" in merge.json()["note"]["body_md"]
        assert merge.json()["archived_note"]["archived"] is True

        archive = await client.post(f"/api/notes/{first_id}/archive", headers=auth_headers())
        assert archive.status_code == 200
        assert archive.json()["note"]["archived"] is True


@pytest.mark.anyio
async def test_notes_unconfigured_returns_empty_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
    app = build_app(tmp_path)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/notes", headers=auth_headers())

    assert response.status_code == 200
    assert response.json()["notes"] == []
    assert response.json()["configured"] is False
    assert "OBSIDIAN_VAULT_PATH" in response.json()["warning"]


@pytest.mark.anyio
async def test_codex_tile_and_yolo_run_records_output(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    os.environ["CODEX_BIN"] = "/bin/echo"
    os.environ["CODEX_ENABLED"] = "true"
    try:
        async with client:
            tiles = (await client.get("/api/tiles", headers=auth_headers())).json()["tiles"]
            assert any(tile["key"] == "codex" and tile["front"]["glyph"] == "gear" for tile in tiles)
            codex_state = (await client.get("/api/codex", headers=auth_headers())).json()
            assert codex_state["workdir"].endswith("/web")
            assert codex_state["mode"] == "dangerously-bypass-approvals-and-sandbox"
            assert codex_state["effort"] == "xhigh"
            assert codex_state["effort_options"] == ["low", "medium", "high", "xhigh"]

            invalid = await client.post(
                "/api/codex-runs",
                headers=auth_headers(),
                json={"prompt": "try unsupported effort", "effort": "whatever"},
            )
            assert invalid.status_code == 422

            unconfirmed = await client.post(
                "/api/codex-runs",
                headers=auth_headers(),
                json={"prompt": "missing confirmation", "effort": "high"},
            )
            assert unconfirmed.status_code == 400
            assert "dangerous mode" in unconfirmed.json()["detail"]

            created = await client.post(
                "/api/codex-runs",
                headers=auth_headers(),
                json={"prompt": "add a compact settings tile", "effort": "high", "confirm_dangerous_mode": True},
            )
            assert created.status_code == 200
            run_id = created.json()["codex_run"]["id"]
            assert created.json()["codex_run"]["effort"] == "high"

            detail = created.json()["codex_run"]
            for _ in range(20):
                detail = (await client.get(f"/api/codex-runs/{run_id}", headers=auth_headers())).json()["codex_run"]
                if detail["status"] in {"done", "failed"}:
                    break
                await asyncio.sleep(0.05)
            assert detail["status"] == "done"
            assert detail["workdir"].endswith("/web")
            assert "--dangerously-bypass-approvals-and-sandbox" in detail["command"]
            assert 'model_reasoning_effort="high"' in detail["command"]
            assert "add a compact settings tile" in detail["stdout_tail"]
            assert detail["before_status"] is not None
            assert detail["after_status"] is not None
            assert detail["process_id"] is None

            previous = (await client.get("/api/codex-runs", headers=auth_headers())).json()["codex_runs"]
            assert previous[0]["prompt"] == "add a compact settings tile"
            assert previous[0]["effort"] == "high"
    finally:
        os.environ.pop("CODEX_BIN", None)
        os.environ.pop("CODEX_ENABLED", None)


@pytest.mark.anyio
async def test_codex_run_can_be_cancelled(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    fake_codex = tmp_path / "fake-codex"
    fake_codex.write_text("#!/bin/sh\nsleep 5\necho should-not-finish\n")
    fake_codex.chmod(0o755)
    os.environ["CODEX_BIN"] = str(fake_codex)
    os.environ["CODEX_ENABLED"] = "true"
    try:
        async with client:
            created = await client.post(
                "/api/codex-runs",
                headers=auth_headers(),
                json={"prompt": "wait until cancelled", "confirm_dangerous_mode": True},
            )
            assert created.status_code == 200
            run_id = created.json()["codex_run"]["id"]
            running = created.json()["codex_run"]
            for _ in range(30):
                running = (await client.get(f"/api/codex-runs/{run_id}", headers=auth_headers())).json()["codex_run"]
                if running["status"] == "running":
                    break
                await asyncio.sleep(0.05)
            assert running["status"] == "running"
            assert running["process_id"] is not None

            cancel = await client.post(f"/api/codex-runs/{run_id}/cancel", headers=auth_headers())
            assert cancel.status_code == 200
            detail = cancel.json()["codex_run"]
            for _ in range(30):
                detail = (await client.get(f"/api/codex-runs/{run_id}", headers=auth_headers())).json()["codex_run"]
                if detail["status"] == "cancelled":
                    break
                await asyncio.sleep(0.05)
            assert detail["status"] == "cancelled"
            assert detail["cancel_requested"] is True
            assert detail["process_id"] is None
            assert detail["error"] == "cancelled by user"
    finally:
        os.environ.pop("CODEX_BIN", None)
        os.environ.pop("CODEX_ENABLED", None)


def test_page_document_sanitizes_full_document_and_escapes_title() -> None:
    from app.sanitize import page_document

    html = page_document(
        '"><img src=x onerror="window.evil=1"><script>bad()</script>',
        '<p onclick="bad()">ok</p><script>window.evil = true</script>',
    )

    lowered = html.lower()
    assert "<script" not in lowered
    assert "onclick" not in lowered
    assert "onerror" not in lowered
    assert "&lt;img" in html


@pytest.mark.anyio
async def test_expired_approval_cannot_execute(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    from app.models import Approval

    with app.state.session_factory() as session:
        approval = Approval(
            job_id="00000000-0000-0000-0000-000000000001",
            action="calendar.create_event",
            scope={"summary": "expired event"},
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        session.add(approval)
        session.commit()
        approval_id = approval.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/approvals/{approval_id}/approve", headers=auth_headers())
        assert response.status_code == 400
        assert response.json()["detail"] == "approval expired"

        detail = (await client.get(f"/api/approvals/{approval_id}", headers=auth_headers())).json()["approval"]
        assert detail["status"] == "expired"
        assert detail["result"]["executed"] is False

        calendar = (await client.get("/api/calendar", headers=auth_headers())).json()
        assert calendar["events"] == []


@pytest.mark.anyio
async def test_deployment_self_check_flags_default_token_on_public_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'public.db'}")
    monkeypatch.setenv("HOME_API_TOKEN", "dev-token")
    monkeypatch.setenv("HERMES_ENV", "production")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://home.example.test")
    monkeypatch.setenv("HERMES_STRICT_DEPLOYMENT_CHECKS", "false")
    monkeypatch.delenv("AGENT_CMD", raising=False)

    if "app.main" in sys.modules:
        main = importlib.reload(sys.modules["app.main"])
    else:
        import app.main as main
    app = main.app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://home.example.test") as client:
        response = await client.get(
            "/api/deployment/self-check",
            headers={"Authorization": "Bearer dev-token", "Host": "home.example.test"},
        )

    assert response.status_code == 200
    payload = response.json()
    checks = {item["code"]: item for item in payload["checks"]}
    assert payload["ok"] is False
    assert checks["home_api_token"]["status"] == "fail"
    assert checks["request_authorization"]["status"] == "pass"
    assert payload["request"]["authorization_scheme"] == "bearer"


def test_startup_recovery_marks_stale_jobs_and_codex_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'recovery.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("HOME_API_TOKEN", "test-token")
    monkeypatch.setenv("HERMES_ENV", "test")

    from app.db import init_db, make_engine, make_session_factory
    from app.models import CodexRun, Job, JobEvent

    engine = make_engine(database_url)
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        job = Job(command="stale command", status="running")
        run = CodexRun(prompt="stale prompt", effort="low", workdir=str(tmp_path), command=["echo"], status="queued")
        session.add_all([job, run])
        session.commit()
        job_id = job.id
        run_id = run.id

    if "app.main" in sys.modules:
        main = importlib.reload(sys.modules["app.main"])
    else:
        import app.main as main
    app = main.app
    assert app.state.startup_recovery == {"jobs": 1, "codex_runs": 1}
    with app.state.session_factory() as session:
        assert session.get(Job, job_id).status == "failed"
        assert "startup recovery" in session.get(Job, job_id).error
        assert session.get(CodexRun, run_id).status == "failed"
        assert session.query(JobEvent).filter(JobEvent.job_id == job_id).count() == 1


def test_derive_history_meta_cases() -> None:
    from app.jobs import derive_history_meta

    assert derive_history_meta("add buy oat milk to my todos", "done") == ("✅", "add buy oat milk to my todos")
    assert derive_history_meta("   summarize   the hallway filter notes   ", "done") == ("🔎", "summarize the hallway filter notes")
    assert derive_history_meta("schedule dentist next tuesday", "failed")[0] == "⚠️"
    assert derive_history_meta("cancel this stale run", "cancelled")[0] == "🛑"
    emoji, summary = derive_history_meta("x" * 80, "done")
    assert emoji == "💬"
    assert summary.endswith("...")
    assert len(summary) == 60


@pytest.mark.anyio
async def test_jobs_limit_and_history_metadata_fallback(tmp_path: Path) -> None:
    async with build_client(tmp_path) as client:
        for command in ["add first task to my todos", "remember second task", "look up third thing"]:
            response = await client.post("/api/command", headers=auth_headers(), json={"text": command})
            assert response.status_code == 200

        response = await client.get("/api/jobs?limit=2", headers=auth_headers())

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert len(jobs) == 2
    assert all(job["emoji"] for job in jobs)
    assert all(job["summary"] for job in jobs)


@pytest.mark.anyio
async def test_mcp_job_set_summary_updates_current_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'mcp-summary.db'}")
    monkeypatch.setenv("HERMES_HOME_JOB_ID", "job-1")
    module = load_mcp_module()
    module.execute(
        "INSERT INTO jobs (id, command, status) VALUES (:id, :command, :status)",
        {"id": "job-1", "command": "agent command", "status": "running"},
    )

    result = await module.job_set_summary("📝", "wrote a useful note with enough extra words to trim")
    row = module.fetch_one("SELECT emoji, summary FROM jobs WHERE id = :job_id", {"job_id": "job-1"})

    assert result == {"ok": True, "job_id": "job-1"}
    assert row["emoji"] == "📝"
    assert row["summary"] == "wrote a useful note with enough extra words to trim"


@pytest.mark.anyio
async def test_codex_execution_can_be_disabled(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    os.environ["CODEX_BIN"] = "/bin/echo"
    os.environ["CODEX_ENABLED"] = "false"
    try:
        async with client:
            state = (await client.get("/api/codex", headers=auth_headers())).json()
            assert state["enabled"] is False
            assert state["available"] is False

            response = await client.post(
                "/api/codex-runs",
                headers=auth_headers(),
                json={"prompt": "should not run", "effort": "low", "confirm_dangerous_mode": True},
            )
            assert response.status_code == 403
            assert "disabled" in response.json()["detail"]
    finally:
        os.environ.pop("CODEX_BIN", None)
        os.environ.pop("CODEX_ENABLED", None)


def test_schema_files_cover_sqlalchemy_and_mcp_columns() -> None:
    from app.models import Base

    postgres_schema = (Path(__file__).resolve().parents[2] / "db" / "schema.sql").read_text()
    mcp_schema = ";\n".join(load_mcp_module().SQLITE_SCHEMA) + ";"
    for table_name, table in Base.metadata.tables.items():
        expected = set(table.columns.keys())
        assert expected <= schema_columns(postgres_schema, table_name), table_name
        assert expected <= schema_columns(mcp_schema, table_name), table_name


def test_postgres_uuid_columns_use_sqlalchemy_uuid_type() -> None:
    from sqlalchemy import Uuid

    from app.models import Base

    postgres_schema = (Path(__file__).resolve().parents[2] / "db" / "schema.sql").read_text()
    for table_name, column_name in schema_uuid_columns(postgres_schema):
        column_type = Base.metadata.tables[table_name].columns[column_name].type
        assert isinstance(column_type, Uuid), f"{table_name}.{column_name}"


def test_postgres_array_columns_use_sqlalchemy_array_type() -> None:
    from sqlalchemy import Text
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import ARRAY

    from app.models import Base

    postgres_schema = (Path(__file__).resolve().parents[2] / "db" / "schema.sql").read_text()
    dialect = postgresql.dialect()
    for table_name, column_name in schema_text_array_columns(postgres_schema):
        column_type = Base.metadata.tables[table_name].columns[column_name].type.dialect_impl(dialect)
        assert isinstance(column_type, ARRAY), f"{table_name}.{column_name}"
        assert isinstance(column_type.item_type, Text), f"{table_name}.{column_name}"


def load_mcp_module():
    module_path = Path(__file__).resolve().parents[2] / "mcp" / "hermes_home_mcp" / "server.py"
    spec = importlib.util.spec_from_file_location("hermes_home_mcp_schema_test_server", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def schema_columns(schema: str, table_name: str) -> set[str]:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {re.escape(table_name)}\s*\((.*?)\)\s*(?:;|$)",
        schema,
        re.IGNORECASE | re.DOTALL,
    )
    assert match is not None, f"missing table {table_name}"
    columns: set[str] = set()
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip().rstrip(",")
        if not line or line.startswith("--"):
            continue
        name = line.split(None, 1)[0].strip('"')
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name) and name.upper() not in {
            "CHECK",
            "CONSTRAINT",
            "FOREIGN",
            "PRIMARY",
            "UNIQUE",
        }:
            columns.add(name)
    return columns


def schema_uuid_columns(schema: str) -> set[tuple[str, str]]:
    matches = re.finditer(
        r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)\s*(?:;|$)",
        schema,
        re.IGNORECASE | re.DOTALL,
    )
    columns: set[tuple[str, str]] = set()
    for match in matches:
        table_name = match.group(1)
        for raw_line in match.group(2).splitlines():
            line = raw_line.strip().rstrip(",")
            if not line or line.startswith("--"):
                continue
            parts = line.split(None, 2)
            if len(parts) >= 2 and parts[1].upper() == "UUID":
                columns.add((table_name, parts[0].strip('"')))
    return columns


def schema_text_array_columns(schema: str) -> set[tuple[str, str]]:
    matches = re.finditer(
        r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)\s*(?:;|$)",
        schema,
        re.IGNORECASE | re.DOTALL,
    )
    columns: set[tuple[str, str]] = set()
    for match in matches:
        table_name = match.group(1)
        for raw_line in match.group(2).splitlines():
            line = raw_line.strip().rstrip(",")
            if not line or line.startswith("--"):
                continue
            parts = line.split(None, 2)
            if len(parts) >= 2 and parts[1].upper() == "TEXT[]":
                columns.add((table_name, parts[0].strip('"')))
    return columns
