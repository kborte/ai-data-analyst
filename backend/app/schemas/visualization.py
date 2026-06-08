from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ArtifactStatus, ChartType


class VisualizationSpec(BaseModel):
    visualization_id: UUID
    dataset_version_id: UUID
    analysis_run_id: UUID | None = None
    chart_type: ChartType
    title: str
    x_axis: str | None = None
    y_axis: str | None = None
    group_by: list[str] = []
    filters: dict[str, Any] = {}
    aggregation: str | None = None
    rationale: str | None = None
    spec: dict[str, Any] = {}
    created_at: datetime


class VisualizationResult(BaseModel):
    visualization_result_id: UUID
    visualization_id: UUID
    storage_path: str | None = None
    status: ArtifactStatus
    metadata: dict[str, Any] = {}
    created_at: datetime
