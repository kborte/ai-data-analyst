from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class SavedViewSourceType(StrEnum):
    query = "query"
    aggregation = "aggregation"
    pivot = "pivot"
    join = "join"
    filter = "filter"
    feature_result = "feature_result"
    visualization_result = "visualization_result"
    chat_output = "chat_output"
    manual = "manual"


class SavedView(BaseModel):
    saved_view_id: UUID
    workspace_id: UUID
    dataset_id: UUID
    dataset_version_id: UUID
    name: str
    description: str | None = None
    source_type: SavedViewSourceType
    source_spec_json: dict[str, Any] = {}
    storage_backend: str | None = None
    storage_bucket: str | None = None
    storage_path: str | None = None
    storage_format: str | None = None
    row_count: int | None = None
    column_count: int | None = None
    created_at: datetime
    created_by_user_id: UUID | None = None
    metadata_json: dict[str, Any] = {}


class SavedViewCreate(BaseModel):
    name: str
    description: str | None = None
    source_type: SavedViewSourceType
    source_spec_json: dict[str, Any] = {}
    storage_backend: str | None = None
    storage_bucket: str | None = None
    storage_path: str | None = None
    storage_format: str | None = None
    row_count: int | None = None
    column_count: int | None = None
    created_by_user_id: UUID | None = None
    metadata_json: dict[str, Any] = {}


PREVIEW_ROW_LIMIT = 100


class SavedViewPreview(BaseModel):
    saved_view_id: UUID
    columns: list[str]
    rows: list[list[Any]]
    preview_row_count: int
    total_rows_in_artifact: int | None = None
