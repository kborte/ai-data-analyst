from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import DataSourceKind, UploadedFileKind


class DataSource(BaseModel):
    data_source_id: UUID
    workspace_id: UUID
    source_kind: DataSourceKind
    display_name: str
    description: str | None = None
    storage_path: str | None = None
    created_by_user_id: UUID
    created_at: datetime


class UploadedFile(BaseModel):
    """Physical uploaded-file metadata. file_kind describes the type of file, not its analytical role."""

    file_id: UUID
    workspace_id: UUID
    data_source_id: UUID
    file_kind: UploadedFileKind
    original_filename: str
    storage_path: str
    size_bytes: int
    uploaded_by_user_id: UUID
    uploaded_at: datetime
