from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import Repos, get_llm_provider, get_repos
from app.tools.llm.provider import LLMProvider
from app.schemas.visualization import (
    VisualizationDecisionItem,
    VisualizationDecisions,
    VisualizationDecisionsJson,
    VisualizationPlan,
    VisualizationResult,
)
from app.services.visualization_service import DecisionValidation, VisualizationService

router = APIRouter()


class CreateVisualizationPlanRequest(BaseModel):
    profile_id: UUID


class ValidateVisualizationDecisionsRequest(BaseModel):
    decisions: list[VisualizationDecisionItem]


class ValidateVisualizationDecisionsResponse(BaseModel):
    can_generate: bool
    total_charts: int
    approved_charts: int
    rejected_charts: int
    blocked_charts: int


class GenerateVisualizationRequest(BaseModel):
    generated_by_user_id: UUID
    decisions: list[VisualizationDecisionItem]


def _service(repos: Repos, llm: LLMProvider) -> VisualizationService:
    return VisualizationService(
        repos.profile,
        repos.dataset_table,
        repos.visualization_plan,
        repos.visualization_result,
        llm,
    )


@router.post(
    "/datasets/{dataset_id}/versions/{dataset_version_id}/visualization-plans",
    response_model=VisualizationPlan,
    status_code=201,
)
def create_visualization_plan(
    dataset_id: UUID,
    dataset_version_id: UUID,
    body: CreateVisualizationPlanRequest,
    repos: Repos = Depends(get_repos),
    llm: LLMProvider = Depends(get_llm_provider),
) -> VisualizationPlan:
    try:
        return _service(repos, llm).create_visualization_plan(body.profile_id, dataset_version_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/visualization-plans/{visualization_plan_id}/decisions/validate",
    response_model=ValidateVisualizationDecisionsResponse,
)
def validate_visualization_decisions(
    visualization_plan_id: UUID,
    body: ValidateVisualizationDecisionsRequest,
    repos: Repos = Depends(get_repos),
    llm: LLMProvider = Depends(get_llm_provider),
) -> ValidateVisualizationDecisionsResponse:
    try:
        v: DecisionValidation = _service(repos, llm).validate_decisions(
            visualization_plan_id, body.decisions
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ValidateVisualizationDecisionsResponse(
        can_generate=v.can_generate,
        total_charts=v.total_charts,
        approved_charts=v.approved_charts,
        rejected_charts=v.rejected_charts,
        blocked_charts=v.blocked_charts,
    )


@router.post(
    "/visualization-plans/{visualization_plan_id}/generate",
    response_model=VisualizationResult,
    status_code=201,
)
def generate_visualization(
    visualization_plan_id: UUID,
    body: GenerateVisualizationRequest,
    repos: Repos = Depends(get_repos),
    llm: LLMProvider = Depends(get_llm_provider),
) -> VisualizationResult:
    decisions = VisualizationDecisions(
        visualization_decisions_id=uuid4(),
        visualization_plan_id=visualization_plan_id,
        decided_by_user_id=body.generated_by_user_id,
        decisions_json=VisualizationDecisionsJson(decisions=body.decisions),
        created_at=datetime.now(tz=UTC),
    )
    try:
        return _service(repos, llm).generate(visualization_plan_id, decisions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
