"""
M9D integration tests covering gaps not addressed by existing unit tests:

- storage backend selection (get_storage returns correct type based on STORAGE_BACKEND)
- DatasetVersion.storage_path is set to a .duckdb path after upload
- no local files are written when using an in-memory (Supabase-like) fake backend
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos, get_storage
from app.main import app
from app.schemas.workspace import Workspace
from app.tools.files.storage_service import (
    LocalStorageBackend,
    StorageBackend,
    StoredFile,
    SupabaseStorageBackend,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
CSV_BYTES = (FIXTURES / "simple_sales.csv").read_bytes()
WORKSPACE_ID = str(uuid4())


# ---------------------------------------------------------------------------
# Fake in-memory backend (stand-in for SupabaseStorageBackend in tests)
# ---------------------------------------------------------------------------

class FakeStorageBackend:
    """In-memory StorageBackend — no files written to disk."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def save(self, storage_path: str, data: bytes) -> StoredFile:
        self._store[storage_path] = data
        return StoredFile(storage_backend="fake", storage_path=storage_path, size_bytes=len(data))

    def read(self, storage_path: str) -> bytes:
        if storage_path not in self._store:
            raise FileNotFoundError(storage_path)
        return self._store[storage_path]

    def delete(self, storage_path: str) -> None:
        self._store.pop(storage_path, None)

    def exists(self, storage_path: str) -> bool:
        return storage_path in self._store


# ---------------------------------------------------------------------------
# Storage backend selection
# ---------------------------------------------------------------------------

def test_get_storage_returns_local_backend_when_setting_is_local(tmp_path: Path) -> None:
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.STORAGE_BACKEND = "local"
        mock_settings.LOCAL_STORAGE_DIR = str(tmp_path)
        backend = get_storage()
    assert isinstance(backend, LocalStorageBackend)


def test_get_storage_returns_supabase_backend_when_setting_is_supabase(tmp_path: Path) -> None:
    with (
        patch("app.core.config.settings") as mock_settings,
        patch("app.tools.files.storage_service.SupabaseStorageBackend.__init__", return_value=None),
    ):
        mock_settings.STORAGE_BACKEND = "supabase"
        mock_settings.SUPABASE_URL = "https://fake.supabase.co"
        mock_settings.SUPABASE_SERVICE_ROLE_KEY = "fake-key"
        mock_settings.SUPABASE_STORAGE_BUCKET = "test-bucket"
        backend = get_storage()
    assert isinstance(backend, SupabaseStorageBackend)


def test_get_storage_defaults_to_local_for_unknown_backend(tmp_path: Path) -> None:
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.STORAGE_BACKEND = "unknown"
        mock_settings.LOCAL_STORAGE_DIR = str(tmp_path)
        backend = get_storage()
    assert isinstance(backend, LocalStorageBackend)


# ---------------------------------------------------------------------------
# DatasetVersion storage metadata after upload
# ---------------------------------------------------------------------------

def _seed_workspace(repos: Repos) -> None:
    repos.workspace.save(Workspace(
        workspace_id=UUID(WORKSPACE_ID),
        name="test workspace",
        created_by_user_id=uuid4(),
        created_at=datetime.now(tz=UTC),
    ))


@pytest.fixture()
def local_ctx(tmp_path: Path):
    fresh = Repos()
    _seed_workspace(fresh)
    backend = LocalStorageBackend(str(tmp_path / "storage"))
    app.dependency_overrides[get_repos] = lambda: fresh
    app.dependency_overrides[get_storage] = lambda: backend
    yield TestClient(app), fresh, backend
    app.dependency_overrides.clear()


@pytest.fixture()
def fake_ctx(tmp_path: Path):
    """Client + repos + fake in-memory backend — zero disk writes."""
    fresh = Repos()
    _seed_workspace(fresh)
    fake = FakeStorageBackend()
    app.dependency_overrides[get_repos] = lambda: fresh
    app.dependency_overrides[get_storage] = lambda: fake
    yield TestClient(app), fresh, fake
    app.dependency_overrides.clear()


def _upload_and_run(client, repos, backend):
    """Upload CSV, run worker, return (version, uploaded_file)."""
    from app.worker.runner import run_one  # noqa: PLC0415
    client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_BYTES, "text/csv")},
    )
    run_one(repos.job, repos, storage=backend, llm=None)
    versions = list(repos.dataset_version._store.values())
    files = list(repos.uploaded_file._store.values())
    return versions[0], files[0]


def test_dataset_version_storage_path_is_duckdb(local_ctx) -> None:
    client, repos, backend = local_ctx
    version, _ = _upload_and_run(client, repos, backend)
    assert version.storage_path is not None
    assert version.storage_path.endswith(".duckdb"), f"Expected .duckdb, got: {version.storage_path}"


def test_dataset_version_storage_path_contains_workspace_and_dataset(local_ctx) -> None:
    client, repos, backend = local_ctx
    version, _ = _upload_and_run(client, repos, backend)
    assert WORKSPACE_ID in version.storage_path
    assert str(version.dataset_id) in version.storage_path


def test_dataset_table_has_no_individual_storage_path(local_ctx) -> None:
    """Tables live inside the version's .duckdb; they have no own storage path."""
    client, repos, backend = local_ctx
    version, _ = _upload_and_run(client, repos, backend)
    tables = repos.dataset_table.list_by_version(version.dataset_version_id)
    for table in tables:
        assert table.storage_path is None, f"Expected table.storage_path=None, got {table.storage_path!r}"


def test_raw_upload_stored_separately_from_duckdb(local_ctx) -> None:
    """raw_upload_path and version_path must be different storage keys."""
    client, repos, backend = local_ctx
    version, uploaded_file = _upload_and_run(client, repos, backend)
    assert uploaded_file.storage_path != version.storage_path


# ---------------------------------------------------------------------------
# No persistent local files when using in-memory (fake/Supabase) backend
# ---------------------------------------------------------------------------

def test_upload_with_fake_backend_writes_no_local_files(
    fake_ctx, tmp_path: Path
) -> None:
    """When using an in-memory storage backend, no persistent files hit the local filesystem."""
    from app.worker.runner import run_one  # noqa: PLC0415
    client, repos, fake = fake_ctx
    before = set(tmp_path.rglob("*"))
    client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_BYTES, "text/csv")},
    )
    run_one(repos.job, repos, storage=fake, llm=None)
    after = set(tmp_path.rglob("*"))
    assert not (after - before), f"Unexpected local files: {after - before}"


def test_profile_with_fake_backend_writes_no_local_files(
    fake_ctx, tmp_path: Path
) -> None:
    from app.worker.runner import run_one  # noqa: PLC0415
    client, repos, fake = fake_ctx
    _upload_and_run(client, repos, fake)
    version = list(repos.dataset_version._store.values())[0]

    before = set(tmp_path.rglob("*"))
    client.post(f"/datasets/{version.dataset_id}/versions/{version.dataset_version_id}/profile")
    run_one(repos.job, repos, storage=fake, llm=None)
    after = set(tmp_path.rglob("*"))
    assert not (after - before), f"Unexpected local files written during profiling: {after - before}"


def test_fake_backend_holds_both_artifacts_in_memory(fake_ctx) -> None:
    """Both the raw upload and .duckdb version artifact are in the fake store."""
    client, repos, fake = fake_ctx
    version, uploaded_file = _upload_and_run(client, repos, fake)

    assert fake.exists(uploaded_file.storage_path), "Raw upload must be in fake store"
    assert fake.exists(version.storage_path), ".duckdb version artifact must be in fake store"
    duckdb_bytes = fake.read(version.storage_path)
    _DUCKDB_MAGIC = bytes.fromhex("063187b8")
    assert duckdb_bytes[:4] == _DUCKDB_MAGIC, (
        f"Stored artifact must be a valid DuckDB file, got: {duckdb_bytes[:4].hex()}"
    )
