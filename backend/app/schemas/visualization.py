from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ArtifactStatus, ChartType, ExecutionStatus, UserDecision

# ---------------------------------------------------------------------------
# M8A: chart suggestion + plan schemas
# ---------------------------------------------------------------------------


class ChartSuggestion(BaseModel):
    visualization_id: UUID
    title: str
    description: str
    chart_type: ChartType
    input_table: str
    x_column: str
    y_column: str | None = None
    y_columns: list[str] = []
    group_by: str | None = None
    aggregation: str | None = None
    filters: dict[str, Any] = {}
    sort: str | None = None
    limit: int | None = None
    user_facing_explanation: str
    requires_human_approval: bool = True


class VisualizationPlanJson(BaseModel):
    suggestions: list[ChartSuggestion]


class VisualizationPlan(BaseModel):
    visualization_plan_id: UUID
    dataset_version_id: UUID
    analysis_run_id: UUID | None = None
    status: ArtifactStatus
    plan_json: VisualizationPlanJson
    created_at: datetime


# ---------------------------------------------------------------------------
# M8B: chart spec + execution result schemas
# ---------------------------------------------------------------------------


class SeriesSpec(BaseModel):
    data_key: str
    label: str


class ChartSpec(BaseModel):
    visualization_id: str
    title: str
    chart_type: str
    x_key: str
    series: list[SeriesSpec]
    data: list[dict[str, Any]]
    description: str


class ChartExecutionResult(BaseModel):
    visualization_id: UUID
    status: ExecutionStatus
    chart_spec: ChartSpec | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# M8B-C: decision schemas (pure data, no logic)
# ---------------------------------------------------------------------------


class VisualizationDecisionItem(BaseModel):
    visualization_id: UUID
    decision: UserDecision
    note: str | None = None


class VisualizationDecisionsJson(BaseModel):
    decisions: list[VisualizationDecisionItem]


class VisualizationDecisions(BaseModel):
    visualization_decisions_id: UUID
    visualization_plan_id: UUID
    decided_by_user_id: UUID
    decisions_json: VisualizationDecisionsJson
    created_at: datetime


# ---------------------------------------------------------------------------
# M8C: visualization result
# ---------------------------------------------------------------------------


class VisualizationResult(BaseModel):
    visualization_result_id: UUID
    visualization_plan_id: UUID
    dataset_version_id: UUID
    status: ArtifactStatus
    chart_specs: list[ChartSpec]
    chart_results: list[ChartExecutionResult]
    created_at: datetime


# ---------------------------------------------------------------------------
# Legacy M1 schema — kept for backward compatibility
# ---------------------------------------------------------------------------


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
