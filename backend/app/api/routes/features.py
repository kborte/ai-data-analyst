from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import Repos, get_llm_provider, get_repos
from app.tools.llm.provider import LLMProvider
from app.schemas.features import (
    FeatureDecisionItem,
    FeatureDecisions,
    FeatureDecisionsJson,
    FeaturePlan,
    FeatureResult,
)
from app.services.feature_service import DecisionValidation, FeatureService

router = APIRouter()


class CreateFeaturePlanRequest(BaseModel):
    profile_id: UUID


class ValidateFeatureDecisionsRequest(BaseModel):
    decisions: list[FeatureDecisionItem]


class ValidateFeatureDecisionsResponse(BaseModel):
    can_execute: bool
    total_features: int
    approved_features: int
    rejected_features: int
    blocked_features: int


class ExecuteFeaturePlanRequest(BaseModel):
    workspace_id: UUID
    dataset_id: UUID
    input_dataset_version_id: UUID
    executed_by_user_id: UUID
    decisions: list[FeatureDecisionItem]


def _service(repos: Repos, llm: LLMProvider) -> FeatureService:
    return FeatureService(
        repos.profile,
        repos.dataset_version,
        repos.dataset_table,
        repos.feature_plan,
        repos.feature_result,
        llm,
    )


@router.post(
    "/datasets/{dataset_id}/versions/{dataset_version_id}/feature-plans",
    response_model=FeaturePlan,
    status_code=201,
)
def create_feature_plan(
    dataset_id: UUID,
    dataset_version_id: UUID,
    body: CreateFeaturePlanRequest,
    repos: Repos = Depends(get_repos),
    llm: LLMProvider = Depends(get_llm_provider),
) -> FeaturePlan:
    try:
        return _service(repos, llm).create_feature_plan(body.profile_id, dataset_version_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/feature-plans/{feature_plan_id}/decisions/validate",
    response_model=ValidateFeatureDecisionsResponse,
)
def validate_feature_decisions(
    feature_plan_id: UUID,
    body: ValidateFeatureDecisionsRequest,
    repos: Repos = Depends(get_repos),
    llm: LLMProvider = Depends(get_llm_provider),
) -> ValidateFeatureDecisionsResponse:
    try:
        v: DecisionValidation = _service(repos, llm).validate_decisions(feature_plan_id, body.decisions)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ValidateFeatureDecisionsResponse(
        can_execute=v.can_execute,
        total_features=v.total_features,
        approved_features=v.approved_features,
        rejected_features=v.rejected_features,
        blocked_features=v.blocked_features,
    )


@router.post(
    "/feature-plans/{feature_plan_id}/execute",
    response_model=FeatureResult,
    status_code=201,
)
def execute_feature_plan(
    feature_plan_id: UUID,
    body: ExecuteFeaturePlanRequest,
    repos: Repos = Depends(get_repos),
    llm: LLMProvider = Depends(get_llm_provider),
) -> FeatureResult:
    decisions = FeatureDecisions(
        feature_decisions_id=uuid4(),
        feature_plan_id=feature_plan_id,
        decided_by_user_id=body.executed_by_user_id,
        decisions_json=FeatureDecisionsJson(decisions=body.decisions),
        created_at=datetime.now(tz=UTC),
    )
    try:
        return _service(repos, llm).execute_feature_plan(
            workspace_id=body.workspace_id,
            dataset_id=body.dataset_id,
            input_dataset_version_id=body.input_dataset_version_id,
            feature_plan_id=feature_plan_id,
            decisions=decisions,
            executed_by_user_id=body.executed_by_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
