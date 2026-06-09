"""
Unit tests for the workspace-backed file upload flow.

Covers:
- POST /auth/login creates / retrieves a real user record
- POST /workspaces creates a workspace with FK-valid created_by_user_id
- POST /workspaces/{id}/members adds a known user
- GET /users/{id}/workspaces lists workspaces for the user
- GET /users?username= looks up a user by username
- Upload rejects unknown workspace_id (404, not 500 FK violation)
- Full flow: login → create workspace → upload file → job queued with matching workspace_id
- Worker processes an upload job when the workspace row is present

All tests use in-memory repositories; no external services required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos, get_storage
from app.main import app
from app.schemas.workspace import Workspace
from app.tools.files.storage_service import LocalStorageBackend
from app.worker.runner import run_one

FIXTURES = Path(__file__).parent.parent / "fixtures"
CSV_BYTES = b"product,revenue\nWidget A,500\nWidget B,300\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login(client: TestClient, username: str) -> dict:
    resp = client.post("/auth/login", json={"username": username})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_workspace(client: TestClient, name: str, user_id: str) -> dict:
    resp = client.post("/workspaces", json={"name": name, "created_by_user_id": user_id})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture()
def ctx(storage_dir: Path):
    fresh_repos = Repos()
    backend = LocalStorageBackend(str(storage_dir))
    app.dependency_overrides[get_repos] = lambda: fresh_repos
    app.dependency_overrides[get_storage] = lambda: backend
    client = TestClient(app)
    yield client, fresh_repos, backend
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth: login / user creation
# ---------------------------------------------------------------------------


def test_login_creates_user(ctx) -> None:
    client, repos, _ = ctx
    body = _login(client, "alice")
    assert body["username"] == "alice"
    assert "user_id" in body
    assert UUID(body["user_id"])


def test_login_same_username_returns_same_user_id(ctx) -> None:
    client, repos, _ = ctx
    first = _login(client, "alice")
    second = _login(client, "alice")
    assert first["user_id"] == second["user_id"]


def test_login_different_usernames_get_different_ids(ctx) -> None:
    client, repos, _ = ctx
    alice = _login(client, "alice")
    bob = _login(client, "bob")
    assert alice["user_id"] != bob["user_id"]


def test_login_normalises_username_to_lowercase(ctx) -> None:
    client, repos, _ = ctx
    body = _login(client, "  Alice  ")
    assert body["username"] == "alice"


def test_login_empty_username_returns_400(ctx) -> None:
    client, _, _ = ctx
    resp = client.post("/auth/login", json={"username": "   "})
    assert resp.status_code == 400


def test_login_user_is_stored_in_repo(ctx) -> None:
    client, repos, _ = ctx
    body = _login(client, "alice")
    stored = repos.user.get(UUID(body["user_id"]))
    assert stored is not None
    assert stored.display_name == "alice"


# ---------------------------------------------------------------------------
# User lookup
# ---------------------------------------------------------------------------


def test_lookup_existing_user(ctx) -> None:
    client, _, _ = ctx
    _login(client, "alice")
    resp = client.get("/users?username=alice")
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"


def test_lookup_unknown_user_returns_404(ctx) -> None:
    client, _, _ = ctx
    resp = client.get("/users?username=nobody")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Workspace creation
# ---------------------------------------------------------------------------


def test_create_workspace_returns_201(ctx) -> None:
    client, _, _ = ctx
    user = _login(client, "alice")
    resp = client.post(
        "/workspaces",
        json={"name": "My Workspace", "created_by_user_id": user["user_id"]},
    )
    assert resp.status_code == 201


def test_create_workspace_response_shape(ctx) -> None:
    client, _, _ = ctx
    user = _login(client, "alice")
    ws = _create_workspace(client, "Analytics", user["user_id"])
    assert "workspace_id" in ws
    assert ws["name"] == "Analytics"
    assert ws["created_by_user_id"] == user["user_id"]


def test_create_workspace_stored_in_repo(ctx) -> None:
    client, repos, _ = ctx
    user = _login(client, "alice")
    ws = _create_workspace(client, "Analytics", user["user_id"])
    stored = repos.workspace.get(UUID(ws["workspace_id"]))
    assert stored is not None
    assert stored.name == "Analytics"


def test_create_workspace_unknown_user_returns_404(ctx) -> None:
    client, _, _ = ctx
    resp = client.post(
        "/workspaces",
        json={"name": "X", "created_by_user_id": str(uuid4())},
    )
    assert resp.status_code == 404


def test_creator_is_added_as_member(ctx) -> None:
    client, repos, _ = ctx
    user = _login(client, "alice")
    ws = _create_workspace(client, "Analytics", user["user_id"])
    listed = repos.workspace.list_by_user(UUID(user["user_id"]))
    assert any(w.workspace_id == UUID(ws["workspace_id"]) for w in listed)


# ---------------------------------------------------------------------------
# Workspace listing
# ---------------------------------------------------------------------------


def test_list_user_workspaces_returns_created_workspace(ctx) -> None:
    client, _, _ = ctx
    user = _login(client, "alice")
    ws = _create_workspace(client, "My WS", user["user_id"])
    resp = client.get(f"/users/{user['user_id']}/workspaces")
    assert resp.status_code == 200
    ids = [w["workspace_id"] for w in resp.json()]
    assert ws["workspace_id"] in ids


def test_list_workspaces_empty_for_new_user(ctx) -> None:
    client, _, _ = ctx
    user = _login(client, "newperson")
    resp = client.get(f"/users/{user['user_id']}/workspaces")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_workspaces_only_shows_own(ctx) -> None:
    client, _, _ = ctx
    alice = _login(client, "alice")
    bob = _login(client, "bob")
    _create_workspace(client, "Alice WS", alice["user_id"])
    bob_ws = _create_workspace(client, "Bob WS", bob["user_id"])
    resp = client.get(f"/users/{bob['user_id']}/workspaces")
    assert resp.status_code == 200
    ids = [w["workspace_id"] for w in resp.json()]
    assert bob_ws["workspace_id"] in ids
    # Alice's workspace must not appear
    alice_resp = client.get(f"/users/{alice['user_id']}/workspaces")
    alice_ids = [w["workspace_id"] for w in alice_resp.json()]
    for i in ids:
        assert i not in alice_ids or i == bob_ws["workspace_id"]


# ---------------------------------------------------------------------------
# Add workspace member
# ---------------------------------------------------------------------------


def test_add_member_returns_204(ctx) -> None:
    client, _, _ = ctx
    alice = _login(client, "alice")
    _login(client, "bob")
    ws = _create_workspace(client, "Shared", alice["user_id"])
    resp = client.post(
        f"/workspaces/{ws['workspace_id']}/members",
        json={"username": "bob"},
    )
    assert resp.status_code == 204


def test_added_member_sees_workspace(ctx) -> None:
    client, _, _ = ctx
    alice = _login(client, "alice")
    bob = _login(client, "bob")
    ws = _create_workspace(client, "Shared", alice["user_id"])
    client.post(f"/workspaces/{ws['workspace_id']}/members", json={"username": "bob"})
    resp = client.get(f"/users/{bob['user_id']}/workspaces")
    ids = [w["workspace_id"] for w in resp.json()]
    assert ws["workspace_id"] in ids


def test_add_unknown_user_as_member_returns_404(ctx) -> None:
    client, _, _ = ctx
    user = _login(client, "alice")
    ws = _create_workspace(client, "WS", user["user_id"])
    resp = client.post(
        f"/workspaces/{ws['workspace_id']}/members",
        json={"username": "ghost"},
    )
    assert resp.status_code == 404


def test_add_member_to_unknown_workspace_returns_404(ctx) -> None:
    client, _, _ = ctx
    _login(client, "alice")
    resp = client.post(
        f"/workspaces/{uuid4()}/members",
        json={"username": "alice"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Upload: workspace FK enforcement
# ---------------------------------------------------------------------------


def test_upload_to_nonexistent_workspace_returns_404(ctx) -> None:
    """Upload route must return 404, not a 500 FK violation, for unknown workspace."""
    client, _, _ = ctx
    resp = client.post(
        f"/workspaces/{uuid4()}/datasets/upload",
        files={"file": ("data.csv", CSV_BYTES, "text/csv")},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_upload_to_existing_workspace_returns_201(ctx) -> None:
    client, _, _ = ctx
    user = _login(client, "alice")
    ws = _create_workspace(client, "WS", user["user_id"])
    resp = client.post(
        f"/workspaces/{ws['workspace_id']}/datasets/upload",
        files={"file": ("data.csv", CSV_BYTES, "text/csv")},
    )
    assert resp.status_code == 201


def test_upload_job_workspace_id_matches_workspace(ctx) -> None:
    client, _, _ = ctx
    user = _login(client, "alice")
    ws = _create_workspace(client, "WS", user["user_id"])
    body = client.post(
        f"/workspaces/{ws['workspace_id']}/datasets/upload",
        files={"file": ("data.csv", CSV_BYTES, "text/csv")},
    ).json()
    assert body["workspace_id"] == ws["workspace_id"]


def test_upload_job_is_queued(ctx) -> None:
    client, _, _ = ctx
    user = _login(client, "alice")
    ws = _create_workspace(client, "WS", user["user_id"])
    body = client.post(
        f"/workspaces/{ws['workspace_id']}/datasets/upload",
        files={"file": ("data.csv", CSV_BYTES, "text/csv")},
    ).json()
    assert body["status"] == "queued"
    assert body["job_type"] == "upload_import"


def test_upload_pending_file_saved_to_storage(ctx, storage_dir: Path) -> None:
    client, _, _ = ctx
    user = _login(client, "alice")
    ws = _create_workspace(client, "WS", user["user_id"])
    body = client.post(
        f"/workspaces/{ws['workspace_id']}/datasets/upload",
        files={"file": ("data.csv", CSV_BYTES, "text/csv")},
    ).json()
    pending_path = body["payload_json"]["pending_storage_path"]
    assert (storage_dir / pending_path).exists()


def test_unsupported_extension_rejected_before_workspace_check(ctx) -> None:
    """A bad file type should be rejected with 422 regardless of workspace existence."""
    client, _, _ = ctx
    resp = client.post(
        f"/workspaces/{uuid4()}/datasets/upload",
        files={"file": ("data.pdf", b"%PDF", "application/pdf")},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Full flow: login → workspace → upload → worker
# ---------------------------------------------------------------------------


def test_full_flow_worker_completes_job(ctx, storage_dir: Path) -> None:
    client, repos, backend = ctx
    # 1. Login (creates DB user)
    user = _login(client, "alice")
    # 2. Create workspace (creates DB workspace with FK to user)
    ws = _create_workspace(client, "Sales Data", user["user_id"])
    # 3. Upload file (job references real workspace_id)
    body = client.post(
        f"/workspaces/{ws['workspace_id']}/datasets/upload",
        files={"file": ("data.csv", CSV_BYTES, "text/csv")},
    ).json()
    job_id = UUID(body["job_id"])
    # 4. Worker processes the job
    run_one(repos.job, repos, storage=backend, llm=None)
    job = repos.job.get(job_id)
    assert job is not None
    assert job.status == "completed"


def test_full_flow_dataset_workspace_id_matches(ctx) -> None:
    client, repos, backend = ctx
    user = _login(client, "alice")
    ws = _create_workspace(client, "Sales Data", user["user_id"])
    client.post(
        f"/workspaces/{ws['workspace_id']}/datasets/upload",
        files={"file": ("data.csv", CSV_BYTES, "text/csv")},
    )
    run_one(repos.job, repos, storage=backend, llm=None)
    datasets = list(repos.dataset._store.values())
    assert len(datasets) == 1
    assert str(datasets[0].workspace_id) == ws["workspace_id"]


def test_full_flow_version_created_with_duckdb(ctx, storage_dir: Path) -> None:
    client, repos, backend = ctx
    user = _login(client, "alice")
    ws = _create_workspace(client, "Sales Data", user["user_id"])
    client.post(
        f"/workspaces/{ws['workspace_id']}/datasets/upload",
        files={"file": ("data.csv", CSV_BYTES, "text/csv")},
    )
    run_one(repos.job, repos, storage=backend, llm=None)
    versions = list(repos.dataset_version._store.values())
    assert versions
    duckdb_path = storage_dir / versions[0].storage_path
    assert duckdb_path.exists()


def test_full_flow_two_users_isolated_datasets(ctx) -> None:
    """Datasets created by different users in different workspaces must not mix."""
    client, repos, backend = ctx
    alice = _login(client, "alice")
    bob = _login(client, "bob")
    ws_alice = _create_workspace(client, "Alice WS", alice["user_id"])
    ws_bob = _create_workspace(client, "Bob WS", bob["user_id"])

    client.post(
        f"/workspaces/{ws_alice['workspace_id']}/datasets/upload",
        files={"file": ("a.csv", b"x\n1\n", "text/csv")},
    )
    run_one(repos.job, repos, storage=backend, llm=None)

    client.post(
        f"/workspaces/{ws_bob['workspace_id']}/datasets/upload",
        files={"file": ("b.csv", b"y\n2\n", "text/csv")},
    )
    run_one(repos.job, repos, storage=backend, llm=None)

    all_datasets = list(repos.dataset._store.values())
    assert len(all_datasets) == 2
    ws_ids = {str(d.workspace_id) for d in all_datasets}
    assert ws_alice["workspace_id"] in ws_ids
    assert ws_bob["workspace_id"] in ws_ids
