from __future__ import annotations

import importlib
import os
from pathlib import Path

from fastapi.testclient import TestClient


def build_client(tmp_path: Path) -> TestClient:
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'hermes-home-test.db'}"
    os.environ["HOME_API_TOKEN"] = "test-token"
    os.environ.pop("AGENT_CMD", None)

    import app.main as main

    importlib.reload(main)
    return TestClient(main.create_app())


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def test_api_requires_bearer_token(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    response = client.get("/api/tiles")

    assert response.status_code == 401
    assert response.json()["detail"] == "missing bearer token"


def test_seed_tiles_are_returned_in_sort_order(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    response = client.get("/api/tiles", headers=auth_headers())

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
    assert payload["tiles"][1]["size"] == "m"


def test_command_creates_job_events_page_and_tile_updates(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    command_response = client.post(
        "/api/command",
        headers=auth_headers(),
        json={"text": "add buy oat milk to my todos"},
    )

    assert command_response.status_code == 200
    job_id = command_response.json()["job_id"]

    job_response = client.get(f"/api/jobs/{job_id}", headers=auth_headers())
    assert job_response.status_code == 200
    job = job_response.json()["job"]
    assert job["status"] == "done"
    assert job["page_id"] is not None

    events_response = client.get(f"/api/jobs/{job_id}/events", headers=auth_headers())
    assert events_response.status_code == 200
    event_text = events_response.text
    assert "event: step" in event_text
    assert "reading command" in event_text
    assert "publishing page" in event_text

    page_response = client.get(f"/api/pages/{job['page_id']}", headers=auth_headers())
    assert page_response.status_code == 200
    page = page_response.json()["page"]
    assert "buy oat milk" in page["html"]
    assert "<script" not in page["html"].lower()
    assert "onclick=" not in page["html"].lower()
    assert "data-action=\"todos.complete\"" in page["html"]

    todos_response = client.get("/api/todos", headers=auth_headers())
    assert todos_response.status_code == 200
    todos = todos_response.json()["todos"]
    assert todos[0]["title"] == "buy oat milk"
    assert todos[0]["status"] == "open"

    tiles_response = client.get("/api/tiles", headers=auth_headers())
    todos_tile = next(tile for tile in tiles_response.json()["tiles"] if tile["key"] == "todos")
    assert todos_tile["front"]["count"] == 1


def test_page_action_completes_todo_and_refreshes_tile(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    command_response = client.post(
        "/api/command",
        headers=auth_headers(),
        json={"text": "add replace filter to my todos"},
    )
    job_id = command_response.json()["job_id"]
    job = client.get(f"/api/jobs/{job_id}", headers=auth_headers()).json()["job"]
    page = client.get(f"/api/pages/{job['page_id']}", headers=auth_headers()).json()["page"]
    todo_id = client.get("/api/todos", headers=auth_headers()).json()["todos"][0]["id"]

    response = client.post(
        "/api/actions",
        headers=auth_headers(),
        json={"action": "todos.complete", "payload": {"todo_id": todo_id, "page_id": page["id"]}},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    todos = client.get("/api/todos", headers=auth_headers()).json()["todos"]
    assert todos[0]["status"] == "done"
    tiles = client.get("/api/tiles", headers=auth_headers()).json()["tiles"]
    todos_tile = next(tile for tile in tiles if tile["key"] == "todos")
    assert todos_tile["front"]["count"] == 0
    assert todos_tile["back"]["line"] == "last finished"
