"""
Cleaning schemas for the human-in-the-loop cleaning pipeline.

Low-impact auto-approval rules (ALL must be true):
  - affected rows < 10% of total
  - column is not a key metric column
  - issue does not affect joins, pivots, filters, or core calculations

Human approval is REQUIRED when ANY is true:
  - operation changes row count (drop_rows, deduplicate)
  - column is a key metric, ID, or date column
  - issue affects >= 10% of rows
  - operation changes a grouping/filtering/pivot column

Original datasets must never be overwritten.
Cleaning execution creates a new DatasetVersion in later milestones.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import (
    ApprovalStatus,
    ArtifactStatus,
    CleaningOperationType,
    DefaultDecision,
    ExecutionStatus,
    ImpactLevel,
    IssueType,
    UserDecision,
)


class CleaningIssue(BaseModel):
    issue_type: IssueType
    table_name: str
    column_name: str | None = None
    description: str
    affected_rows_count: int
    affected_rows_percent: float
    sample_values: list[Any] = []


class CleaningRecommendation(BaseModel):
    action_type: str
    recommended_action: str
    rationale: str
    impact_level: ImpactLevel
    affects_key_metrics: bool
    requires_human_approval: bool
    default_decision: DefaultDecision


class CleaningOperation(BaseModel):
    operation_type: CleaningOperationType
    parameters: dict[str, Any] = {}


class CleaningPreview(BaseModel):
    rows_before: int
    estimated_rows_after: int
    estimated_rows_removed: int
    columns_changed: list[str] = []
    metrics_potentially_affected: list[str] = []


class CleaningStep(BaseModel):
    step_id: UUID
    sequence_order: int
    issue: CleaningIssue
    recommendation: CleaningRecommendation
    operation: CleaningOperation
    preview: CleaningPreview


class CleaningPlanSummary(BaseModel):
    total_steps: int
    steps_requiring_approval: int
    auto_approved_steps: int
    auto_ignored_steps: int
    estimated_row_count_change: int
    estimated_columns_changed: list[str] = []


class CleaningPlanJson(BaseModel):
    schema_version: str = "1.0"
    plan_id: UUID | None = None
    dataset_version_id: UUID | None = None
    profile_id: UUID | None = None
    created_at: datetime | None = None
    summary: CleaningPlanSummary | None = None
    global_assumptions: list[str] = []
    steps: list[CleaningStep]


class CleaningPlan(BaseModel):
    cleaning_plan_id: UUID
    dataset_version_id: UUID
    analysis_run_id: UUID | None = None
    status: ArtifactStatus
    plan_json: CleaningPlanJson
    created_at: datetime


class CleaningDecisionItem(BaseModel):
    step_id: UUID
    decision: UserDecision
    modified_operation: CleaningOperation | None = None
    note: str | None = None


class CleaningDecisionsJson(BaseModel):
    decisions: list[CleaningDecisionItem]


class CleaningDecisions(BaseModel):
    cleaning_decisions_id: UUID
    cleaning_plan_id: UUID
    decided_by_user_id: UUID
    decisions_json: CleaningDecisionsJson
    created_at: datetime


class ResolvedCleaningStep(BaseModel):
    """Original step merged with the user's decision and any modification."""

    step_id: UUID
    sequence_order: int
    issue: CleaningIssue
    recommendation: CleaningRecommendation
    operation: CleaningOperation
    preview: CleaningPreview
    decision: UserDecision
    modified_operation: CleaningOperation | None = None


class ResolvedCleaningPlanJson(BaseModel):
    steps: list[ResolvedCleaningStep]


class CleaningStepResult(BaseModel):
    step_id: UUID
    status: ExecutionStatus
    rows_affected: int | None = None
    error_message: str | None = None
    warnings: list[str] = []


class CleaningExecutionSummary(BaseModel):
    total_steps: int
    executed_steps: int
    skipped_steps: int
    failed_steps: int
    rows_before: int
    rows_after: int
    rows_removed: int
    columns_changed: list[str] = []


class CleaningExecutionLogJson(BaseModel):
    schema_version: str = "1.0"
    cleaning_run_id: UUID | None = None
    cleaning_plan_id: UUID | None = None
    input_dataset_version_id: UUID | None = None
    output_dataset_version_id: UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    summary: CleaningExecutionSummary | None = None
    step_results: list[CleaningStepResult]
    warnings: list[str] = []
    errors: list[str] = []


class CleaningResult(BaseModel):
    cleaning_result_id: UUID
    cleaning_plan_id: UUID
    cleaning_decisions_id: UUID
    input_dataset_version_id: UUID
    output_dataset_version_id: UUID | None = None
    status: ArtifactStatus
    row_count_before: int | None = None
    row_count_after: int | None = None
    columns_changed: list[str] = []
    execution_log_json: CleaningExecutionLogJson
    created_at: datetime
    approval_status: ApprovalStatus = ApprovalStatus.pending
