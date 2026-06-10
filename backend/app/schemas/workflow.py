"""Workflow orchestrator schemas: state, approval items, and response types."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.analytics import AnalyticsOutput, PriorOutputRef, RecentMessage  # noqa: F401
from app.schemas.cleaning import CleaningDecisionItem
from app.schemas.features import FeatureDecisionItem


class WorkflowStage(StrEnum):
    start = "start"
    awaiting_cleaning_approval = "awaiting_cleaning_approval"
    awaiting_feature_approval = "awaiting_feature_approval"
    analysis = "analysis"
    complete = "complete"


class WorkflowIntent(StrEnum):
    clean = "clean"
    analyze = "analyze"
    features = "features"
    unknown = "unknown"


class WorkflowState(BaseModel):
    """Compact state serialized to the client and returned on resume."""
    workspace_id: UUID | None = None
    dataset_id: UUID
    dataset_version_id: UUID
    question: str
    stage: WorkflowStage = WorkflowStage.start
    intent: WorkflowIntent = WorkflowIntent.unknown
    # IDs set during orchestration so later stages reference the right artifacts
    profile_id: UUID | None = None
    cleaning_plan_id: UUID | None = None
    feature_plan_id: UUID | None = None
    # Updated to the cleaned/enriched version once execution completes
    resolved_version_id: UUID | None = None


class ApprovalItem(BaseModel):
    id: str
    title: str
    description: str
    recommended_action: str
    details: str | None = None
    default_decision: str = "approve"


class NeedsApprovalResponse(BaseModel):
    response_type: Literal["needs_approval"] = "needs_approval"
    stage: str  # "cleaning" | "features"
    message: str
    dataset_id: UUID
    dataset_version_id: UUID
    items: list[ApprovalItem]
    workflow_state: WorkflowState


class NeedsClarificationResponse(BaseModel):
    response_type: Literal["needs_clarification"] = "needs_clarification"
    message: str
    dataset_id: UUID
    dataset_version_id: UUID
    options: list[str] = []


class AnalysisResultResponse(BaseModel):
    response_type: Literal["analysis_result"] = "analysis_result"
    dataset_id: UUID
    dataset_version_id: UUID
    summary_text: str
    outputs: list[AnalyticsOutput]
    assumptions_used: list[str] = []


WorkflowResponse = Annotated[
    Union[NeedsApprovalResponse, NeedsClarificationResponse, AnalysisResultResponse],
    Field(discriminator="response_type"),
]


class WorkflowRequest(BaseModel):
    question: str
    # Populated on resume after user submits decisions
    workflow_state: WorkflowState | None = None
    cleaning_decisions: list[CleaningDecisionItem] = []
    feature_decisions: list[FeatureDecisionItem] = []
    recent_messages: list[RecentMessage] = []
    prior_output_refs: list[PriorOutputRef] = []
