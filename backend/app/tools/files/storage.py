from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.tools.files.filename import make_safe_filename


def _base() -> Path:
    return Path(settings.LOCAL_STORAGE_DIR)


def build_upload_path(
    workspace_id: UUID,
    data_source_id: UUID,
    file_id: UUID,
    original_filename: str,
) -> Path:
    safe = make_safe_filename(original_filename)
    return (
        _base()
        / "workspaces"
        / str(workspace_id)
        / "sources"
        / str(data_source_id)
        / "original"
        / f"{file_id}__{safe}"
    )


def save_upload(
    workspace_id: UUID,
    data_source_id: UUID,
    file_id: UUID,
    original_filename: str,
    content: bytes,
) -> str:
    """Write bytes to local storage. Returns the storage path as a string."""
    dest = build_upload_path(workspace_id, data_source_id, file_id, original_filename)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return str(dest)


def build_context_path(workspace_id: UUID, context_document_id: UUID) -> Path:
    return (
        _base()
        / "workspaces"
        / str(workspace_id)
        / "context_documents"
        / str(context_document_id)
        / "raw.txt"
    )


def build_cleaned_table_path(
    workspace_id: UUID,
    dataset_id: UUID,
    dataset_version_id: UUID,
    table_name: str,
) -> Path:
    safe = make_safe_filename(f"{table_name}.csv")
    return (
        _base()
        / "workspaces"
        / str(workspace_id)
        / "datasets"
        / str(dataset_id)
        / "versions"
        / str(dataset_version_id)
        / "tables"
        / safe
    )


def save_cleaned_table(
    workspace_id: UUID,
    dataset_id: UUID,
    dataset_version_id: UUID,
    table_name: str,
    content: bytes,
) -> str:
    dest = build_cleaned_table_path(workspace_id, dataset_id, dataset_version_id, table_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return str(dest)


def save_context(workspace_id: UUID, context_document_id: UUID, content: bytes) -> str:
    dest = build_context_path(workspace_id, context_document_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return str(dest)
