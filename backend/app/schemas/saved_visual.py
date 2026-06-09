from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class SavedVisualSourceType(StrEnum):
    visualization_result = "visualization_result"
    chart_spec = "chart_spec"
    view_data = "view_data"
    direct = "direct"


class SavedVisual(BaseModel):
    visual_id: UUID
    workspace_id: UUID
    dataset_id: UUID
    dataset_version_id: UUID
    title: str
    description: str | None = None
    chart_type: str
    chart_spec_json: dict[str, Any] = {}
    source_type: SavedVisualSourceType
    source_visualization_result_id: UUID | None = None
    source_view_id: UUID | None = None
    source_spec_json: dict[str, Any] = {}
    data_storage_backend: str | None = None
    data_storage_bucket: str | None = None
    data_storage_path: str | None = None
    created_at: datetime
    created_by_user_id: UUID | None = None
    metadata_json: dict[str, Any] = {}


class SavedVisualCreate(BaseModel):
    title: str
    description: str | None = None
    chart_type: str
    chart_spec_json: dict[str, Any] = {}
    source_type: SavedVisualSourceType
    source_visualization_result_id: UUID | None = None
    source_view_id: UUID | None = None
    source_spec_json: dict[str, Any] = {}
    data_storage_backend: str | None = None
    data_storage_bucket: str | None = None
    data_storage_path: str | None = None
    created_by_user_id: UUID | None = None
    metadata_json: dict[str, Any] = {}
