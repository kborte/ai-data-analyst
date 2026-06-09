"""
Tests for the storage abstraction (M9A).

LocalStorageBackend — tested against a real tmp_path.
SupabaseStorageBackend — tested via FakeStorageBackend that implements the
same protocol; no live Supabase credentials required.
"""

from pathlib import Path
from uuid import uuid4

import pytest

from app.tools.files.storage_service import (
    LocalStorageBackend,
    StorageBackend,
    StoredFile,
    raw_upload_path,
    result_path,
    version_path,
)


# ---------------------------------------------------------------------------
# Fake backend — stands in for SupabaseStorageBackend in tests
# ---------------------------------------------------------------------------

class FakeStorageBackend:
    """In-memory StorageBackend; satisfies the protocol without network calls."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def save(self, storage_path: str, data: bytes) -> StoredFile:
        self._store[storage_path] = data
        return StoredFile(
            storage_backend="fake",
            storage_path=storage_path,
            storage_bucket="fake-bucket",
            size_bytes=len(data),
        )

    def read(self, storage_path: str) -> bytes:
        if storage_path not in self._store:
            raise FileNotFoundError(storage_path)
        return self._store[storage_path]

    def delete(self, storage_path: str) -> None:
        self._store.pop(storage_path, None)

    def exists(self, storage_path: str) -> bool:
        return storage_path in self._store


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

def test_local_backend_satisfies_protocol(tmp_path: Path) -> None:
    backend = LocalStorageBackend(str(tmp_path))
    assert isinstance(backend, StorageBackend)


def test_fake_backend_satisfies_protocol() -> None:
    assert isinstance(FakeStorageBackend(), StorageBackend)


# ---------------------------------------------------------------------------
# LocalStorageBackend
# ---------------------------------------------------------------------------

def test_local_save_and_read(tmp_path: Path) -> None:
    b = LocalStorageBackend(str(tmp_path))
    result = b.save("a/b/file.csv", b"hello")
    assert result.storage_backend == "local"
    assert result.storage_path == "a/b/file.csv"
    assert result.size_bytes == 5
    assert b.read("a/b/file.csv") == b"hello"


def test_local_exists(tmp_path: Path) -> None:
    b = LocalStorageBackend(str(tmp_path))
    assert not b.exists("missing.csv")
    b.save("present.csv", b"x")
    assert b.exists("present.csv")


def test_local_delete(tmp_path: Path) -> None:
    b = LocalStorageBackend(str(tmp_path))
    b.save("del.csv", b"data")
    b.delete("del.csv")
    assert not b.exists("del.csv")


def test_local_delete_missing_is_noop(tmp_path: Path) -> None:
    LocalStorageBackend(str(tmp_path)).delete("ghost.csv")


def test_local_creates_nested_dirs(tmp_path: Path) -> None:
    b = LocalStorageBackend(str(tmp_path))
    b.save("deep/nested/dir/file.bin", b"data")
    assert (tmp_path / "deep" / "nested" / "dir" / "file.bin").exists()


# ---------------------------------------------------------------------------
# FakeStorageBackend (stands in for Supabase in tests)
# ---------------------------------------------------------------------------

def test_fake_save_and_read() -> None:
    b = FakeStorageBackend()
    stored = b.save("ws/123/file.duckdb", b"\x01\x02")
    assert stored.storage_backend == "fake"
    assert stored.size_bytes == 2
    assert b.read("ws/123/file.duckdb") == b"\x01\x02"


def test_fake_exists_and_delete() -> None:
    b = FakeStorageBackend()
    b.save("f.bin", b"y")
    assert b.exists("f.bin")
    b.delete("f.bin")
    assert not b.exists("f.bin")


def test_fake_read_missing_raises() -> None:
    with pytest.raises(FileNotFoundError):
        FakeStorageBackend().read("not_there.bin")


# ---------------------------------------------------------------------------
# Path builders
# ---------------------------------------------------------------------------

def test_raw_upload_path() -> None:
    wid, did, fid = uuid4(), uuid4(), uuid4()
    p = raw_upload_path(wid, did, fid, "my data.csv")
    assert p.startswith(f"workspaces/{wid}/datasets/{did}/raw_uploads/")
    assert str(fid) in p
    assert "my_data.csv" in p


def test_version_path() -> None:
    wid, did = uuid4(), uuid4()
    p = version_path(wid, did, 3, "cleaned")
    assert p == f"workspaces/{wid}/datasets/{did}/versions/v3_cleaned.duckdb"


def test_result_path() -> None:
    wid, did, aid = uuid4(), uuid4(), uuid4()
    p = result_path(wid, did, aid, "csv")
    assert p == f"workspaces/{wid}/datasets/{did}/results/{aid}.csv"
