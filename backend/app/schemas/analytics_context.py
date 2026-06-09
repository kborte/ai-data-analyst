"""M12B: Compact dataset context schema for the analytics planner."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

# Maximum top_values entries per column kept in context.
_MAX_TOP_VALUES = 5

# Maximum saved views/visuals included in context.
_MAX_ARTIFACTS = 10


class DatasetContextColumn(BaseModel):
    column_name: str
    data_type: str
    null_percent: float | None = None
    unique_count: int | None = None
    is_likely_id: bool = False
    is_likely_metric: bool = False
    is_likely_categorical: bool = False
    is_likely_date: bool = False
    top_values: list[Any] = []


class DatasetContextTable(BaseModel):
    table_name: str
    row_count: int | None = None
    column_count: int | None = None
    columns: list[DatasetContextColumn] = []
    has_profile: bool = False
    quality_issue_count: int = 0


class DatasetContextView(BaseModel):
    saved_view_id: UUID
    name: str
    source_type: str
    row_count: int | None = None
    column_count: int | None = None


class DatasetContextVisual(BaseModel):
    visual_id: UUID
    title: str
    chart_type: str


class DatasetContext(BaseModel):
    dataset_id: UUID
    dataset_name: str
    dataset_version_id: UUID
    version_number: int
    version_type: str
    display_name: str | None = None
    tables: list[DatasetContextTable] = []
    saved_views: list[DatasetContextView] = []
    saved_visuals: list[DatasetContextVisual] = []
