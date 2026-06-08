from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import DatasetSourceRole, DatasetVersionType, DataType


class Dataset(BaseModel):
    dataset_id: UUID
    workspace_id: UUID
    name: str
    description: str | None = None
    created_by_user_id: UUID
    created_at: datetime


class DatasetSource(BaseModel):
    """Links a Dataset to one DataSource, with an analytical role."""

    dataset_source_id: UUID
    dataset_id: UUID
    data_source_id: UUID
    role: DatasetSourceRole


class DatasetVersion(BaseModel):
    """
    Materialized state of a dataset.

    version_number is unique within each dataset (conceptually unique(dataset_id, version_number)).
    Multiple versions may share the same version_type — e.g. several successive cleaned versions.
    Original data must never be overwritten; cleaning/enrichment always creates a new version.
    """

    dataset_version_id: UUID
    dataset_id: UUID
    parent_version_id: UUID | None = None
    version_number: int
    version_type: DatasetVersionType
    display_name: str | None = None
    description: str | None = None
    storage_path: str | None = None
    row_count: int | None = None
    column_count: int | None = None
    created_by_user_id: UUID
    created_at: datetime
    metadata: dict[str, Any] = {}


class DatasetTable(BaseModel):
    """One table/sheet inside a dataset version."""

    table_id: UUID
    dataset_version_id: UUID
    table_name: str
    storage_path: str | None = None
    row_count: int | None = None
    column_count: int | None = None


class DatasetColumn(BaseModel):
    column_name: str
    data_type: DataType
    nullable: bool = True
    sample_values: list[Any] = []


class DatasetPreview(BaseModel):
    dataset_version_id: UUID
    table_name: str
    columns: list[DatasetColumn]
    rows: list[dict[str, Any]]
    total_rows: int
