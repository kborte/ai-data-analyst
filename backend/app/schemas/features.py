from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ArtifactStatus, ExecutionStatus, FeatureOperationType, UserDecision


class FeatureDefinition(BaseModel):
    feature_id: UUID
    feature_name: str
    display_name: str = ""
    description: str = ""
    operation_type: FeatureOperationType
    formula_display: str
    input_table: str = ""
    output_table: str | None = None
    output_column: str | None = None
    required_columns: list[str]
    grouping_columns: list[str] = []
    sort_columns: list[str] = []
    reset_period: str | None = None
    assumptions: list[str] = []
    parameters: dict[str, Any] = {}
    requires_human_approval: bool = True


class FeaturePlanJson(BaseModel):
    features: list[FeatureDefinition]


class FeaturePlan(BaseModel):
    feature_plan_id: UUID
    dataset_version_id: UUID
    analysis_run_id: UUID | None = None
    status: ArtifactStatus
    plan_json: FeaturePlanJson
    created_at: datetime


class FeatureDecisionItem(BaseModel):
    feature_id: UUID
    decision: UserDecision
    modified_definition: FeatureDefinition | None = None
    note: str | None = None


class FeatureDecisionsJson(BaseModel):
    decisions: list[FeatureDecisionItem]


class FeatureDecisions(BaseModel):
    feature_decisions_id: UUID
    feature_plan_id: UUID
    decided_by_user_id: UUID
    decisions_json: FeatureDecisionsJson
    created_at: datetime


class FeatureExecutionLogJson(BaseModel):
    feature_results: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []


class FeatureResult(BaseModel):
    feature_result_id: UUID
    feature_plan_id: UUID
    feature_decisions_id: UUID
    input_dataset_version_id: UUID
    output_dataset_version_id: UUID | None = None
    status: ArtifactStatus
    features_added: list[str] = []
    execution_log_json: FeatureExecutionLogJson
    created_at: datetime
    execution_status: ExecutionStatus = ExecutionStatus.success
