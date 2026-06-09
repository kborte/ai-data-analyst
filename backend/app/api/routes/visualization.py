from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import Repos, get_llm_provider, get_repos
from app.tools.llm.provider import LLMProvider
from app.schemas.common import JobStatus, JobType
from app.schemas.job import Job
from app.schemas.visualization import (
    VisualizationDecisionItem,
    VisualizationPlan,
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
    response_model=Job,
    status_code=201,
)
def generate_visualization(
    visualization_plan_id: UUID,
    body: GenerateVisualizationRequest,
    repos: Repos = Depends(get_repos),
    llm: LLMProvider = Depends(get_llm_provider),
) -> Job:
    plan = repos.visualization_plan.get(visualization_plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"VisualizationPlan {visualization_plan_id} not found.")

    dataset_version = repos.dataset_version.get(plan.dataset_version_id)
    dataset_id = dataset_version.dataset_id if dataset_version else None
    workspace_id_val = uuid4()
    if dataset_id:
        ds = repos.dataset.get(dataset_id)
        if ds:
            workspace_id_val = ds.workspace_id

    job = Job(
        job_id=uuid4(),
        workspace_id=workspace_id_val,
        dataset_id=dataset_id,
        input_dataset_version_id=plan.dataset_version_id,
        job_type=JobType.generate_visualizations,
        status=JobStatus.queued,
        payload_json={
            "visualization_plan_id": str(visualization_plan_id),
            "decisions_id": str(uuid4()),
            "generated_by_user_id": str(body.generated_by_user_id),
            "decisions": [d.model_dump() for d in body.decisions],
        },
        created_at=datetime.now(tz=UTC),
    )
    return repos.job.save(job)
