"""
Storage abstraction for persistent file artifacts.

Two backends:
  LocalStorageBackend  — writes to LOCAL_STORAGE_DIR; for dev/tests.
  SupabaseStorageBackend — uploads to Supabase Storage; for production.

Path convention (from CLAUDE.md):
  raw uploads:      workspaces/{wid}/datasets/{did}/raw_uploads/{fid}_{filename}
  dataset versions: workspaces/{wid}/datasets/{did}/versions/v{n}_{type}.duckdb
  result artifacts: workspaces/{wid}/datasets/{did}/results/{aid}.{ext}

StoredFile carries the metadata Postgres stores alongside each artifact record.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import UUID


# ---------------------------------------------------------------------------
# Value object returned by every save() call
# ---------------------------------------------------------------------------

@dataclass
class StoredFile:
    storage_backend: str        # "local" | "supabase"
    storage_path: str           # relative path used as the storage key
    storage_bucket: str | None = None
    storage_format: str | None = None
    size_bytes: int | None = None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class StorageBackend(Protocol):
    def save(self, storage_path: str, data: bytes) -> StoredFile: ...
    def read(self, storage_path: str) -> bytes: ...
    def delete(self, storage_path: str) -> None: ...
    def exists(self, storage_path: str) -> bool: ...


# ---------------------------------------------------------------------------
# Local backend
# ---------------------------------------------------------------------------

class LocalStorageBackend:
    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)

    def save(self, storage_path: str, data: bytes) -> StoredFile:
        dest = self._base / storage_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return StoredFile(
            storage_backend="local",
            storage_path=storage_path,
            size_bytes=len(data),
        )

    def read(self, storage_path: str) -> bytes:
        return (self._base / storage_path).read_bytes()

    def delete(self, storage_path: str) -> None:
        p = self._base / storage_path
        if p.exists():
            p.unlink()

    def exists(self, storage_path: str) -> bool:
        return (self._base / storage_path).exists()


# ---------------------------------------------------------------------------
# Supabase Storage backend
# ---------------------------------------------------------------------------

class SupabaseStorageBackend:
    """
    Uses the Supabase service role key so it bypasses RLS.
    Requires SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_STORAGE_BUCKET.
    """

    def __init__(self, url: str, key: str, bucket: str) -> None:
        from supabase import create_client  # noqa: PLC0415
        self._client = create_client(url, key)
        self._bucket = bucket

    def save(self, storage_path: str, data: bytes) -> StoredFile:
        self._client.storage.from_(self._bucket).upload(
            storage_path,
            data,
            {"upsert": "true", "content-type": "application/octet-stream"},
        )
        return StoredFile(
            storage_backend="supabase",
            storage_path=storage_path,
            storage_bucket=self._bucket,
            size_bytes=len(data),
        )

    def read(self, storage_path: str) -> bytes:
        return self._client.storage.from_(self._bucket).download(storage_path)

    def delete(self, storage_path: str) -> None:
        self._client.storage.from_(self._bucket).remove([storage_path])

    def exists(self, storage_path: str) -> bool:
        folder, _, name = storage_path.rpartition("/")
        files = self._client.storage.from_(self._bucket).list(folder) or []
        return any(f.get("name") == name for f in files)


# ---------------------------------------------------------------------------
# Path builders — follow the convention in CLAUDE.md
# ---------------------------------------------------------------------------

def raw_upload_path(workspace_id: UUID, dataset_id: UUID, file_id: UUID, filename: str) -> str:
    safe = filename.replace(" ", "_")
    return f"workspaces/{workspace_id}/datasets/{dataset_id}/raw_uploads/{file_id}_{safe}"


def version_path(
    workspace_id: UUID,
    dataset_id: UUID,
    version_number: int,
    version_type: str,
) -> str:
    return (
        f"workspaces/{workspace_id}/datasets/{dataset_id}"
        f"/versions/v{version_number}_{version_type}.duckdb"
    )


def result_path(workspace_id: UUID, dataset_id: UUID, artifact_id: UUID, ext: str) -> str:
    return f"workspaces/{workspace_id}/datasets/{dataset_id}/results/{artifact_id}.{ext}"
