"""
M9D integration tests covering gaps not addressed by existing unit tests:

- storage backend selection (get_storage returns correct type based on STORAGE_BACKEND)
- DatasetVersion.storage_path is set to a .duckdb path after upload
- no local files are written when using an in-memory (Supabase-like) fake backend
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos, get_storage
from app.main import app
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

@pytest.fixture()
def local_client(tmp_path: Path) -> TestClient:
    fresh = Repos()
    backend = LocalStorageBackend(str(tmp_path / "storage"))
    app.dependency_overrides[get_repos] = lambda: fresh
    app.dependency_overrides[get_storage] = lambda: backend
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def fake_client() -> TestClient:
    """Client that uses an in-memory fake backend — zero disk writes."""
    fresh = Repos()
    fake = FakeStorageBackend()
    app.dependency_overrides[get_repos] = lambda: fresh
    app.dependency_overrides[get_storage] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_dataset_version_storage_path_is_duckdb(local_client: TestClient) -> None:
    body = local_client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_BYTES, "text/csv")},
    ).json()
    storage_path = body["dataset_version"]["storage_path"]
    assert storage_path is not None
    assert storage_path.endswith(".duckdb"), f"Expected .duckdb path, got: {storage_path}"


def test_dataset_version_storage_path_contains_workspace_and_dataset(local_client: TestClient) -> None:
    body = local_client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_BYTES, "text/csv")},
    ).json()
    storage_path = body["dataset_version"]["storage_path"]
    dataset_id = body["dataset"]["dataset_id"]
    assert WORKSPACE_ID in storage_path
    assert dataset_id in storage_path


def test_dataset_table_has_no_individual_storage_path(local_client: TestClient) -> None:
    """Tables live inside the version's .duckdb; they have no own storage path."""
    body = local_client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_BYTES, "text/csv")},
    ).json()
    for table in body["dataset_tables"]:
        assert table["storage_path"] is None, (
            f"Expected table.storage_path=None, got {table['storage_path']!r}"
        )


def test_raw_upload_stored_separately_from_duckdb(local_client: TestClient) -> None:
    """raw_upload_path and version_path must be different storage keys."""
    body = local_client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_BYTES, "text/csv")},
    ).json()
    raw_path = body["uploaded_file"]["storage_path"]
    ver_path = body["dataset_version"]["storage_path"]
    assert raw_path != ver_path


# ---------------------------------------------------------------------------
# No persistent local files when using in-memory (fake/Supabase) backend
# ---------------------------------------------------------------------------

def test_upload_with_fake_backend_writes_no_local_files(
    fake_client: TestClient, tmp_path: Path
) -> None:
    """When using an in-memory storage backend, the upload must not write any
    persistent files to the local filesystem."""
    before = set(tmp_path.rglob("*"))
    fake_client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_BYTES, "text/csv")},
    )
    after = set(tmp_path.rglob("*"))
    new_files = after - before
    # temp DuckDB scratch files are cleaned up; no new persistent files should remain
    assert not new_files, f"Unexpected local files written: {new_files}"


def test_profile_with_fake_backend_writes_no_local_files(
    fake_client: TestClient, tmp_path: Path
) -> None:
    upload = fake_client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_BYTES, "text/csv")},
    ).json()
    dataset_id = upload["dataset"]["dataset_id"]
    version_id = upload["dataset_version"]["dataset_version_id"]

    before = set(tmp_path.rglob("*"))
    resp = fake_client.post(f"/datasets/{dataset_id}/versions/{version_id}/profile")
    assert resp.status_code == 200
    after = set(tmp_path.rglob("*"))
    new_files = after - before
    assert not new_files, f"Unexpected local files written during profiling: {new_files}"


def test_fake_backend_holds_both_artifacts_in_memory() -> None:
    """Both the raw upload and .duckdb version artifact are in the fake store."""
    fake = FakeStorageBackend()
    fresh = Repos()
    app.dependency_overrides[get_repos] = lambda: fresh
    app.dependency_overrides[get_storage] = lambda: fake
    try:
        body = TestClient(app).post(
            f"/workspaces/{WORKSPACE_ID}/datasets/upload",
            files={"file": ("simple_sales.csv", CSV_BYTES, "text/csv")},
        ).json()
        raw_path = body["uploaded_file"]["storage_path"]
        ver_path = body["dataset_version"]["storage_path"]
        assert fake.exists(raw_path), "Raw upload must be in fake store"
        assert fake.exists(ver_path), ".duckdb version artifact must be in fake store"
        duckdb_bytes = fake.read(ver_path)
        # DuckDB 1.x file header (first 4 bytes of the block header)
        _DUCKDB_MAGIC = bytes.fromhex("063187b8")
        assert duckdb_bytes[:4] == _DUCKDB_MAGIC, (
            f"Stored artifact must be a valid DuckDB file, got: {duckdb_bytes[:4].hex()}"
        )
    finally:
        app.dependency_overrides.clear()
