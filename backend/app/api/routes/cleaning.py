from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import Repos, get_llm_provider, get_repos
from app.tools.llm.provider import LLMProvider
from app.schemas.cleaning import (
    CleaningDecisionItem,
    CleaningDecisionsJson,
    CleaningPlan,
    CleaningResult,
)
from app.schemas.common import JobStatus, JobType
from app.schemas.job import Job
from app.services.cleaning_plan_service import CleaningPlanService
from app.tools.data.cleaning_decision_resolver import resolve_decisions

router = APIRouter()


class CreateCleaningPlanRequest(BaseModel):
    profile_id: UUID
    workspace_id: UUID | None = None
    created_by_user_id: UUID | None = None


class ValidateDecisionsRequest(BaseModel):
    decisions: list[CleaningDecisionItem]
    workspace_id: UUID | None = None
    dataset_id: UUID | None = None
    created_by_user_id: UUID | None = None


class ValidateDecisionsResponse(BaseModel):
    can_execute: bool
    total_steps: int
    approved_steps: int
    rejected_steps: int
    modified_steps: int
    blocked_steps: int
    auto_approved_steps: int
    skipped_steps: int


class ExecuteCleaningPlanRequest(BaseModel):
    workspace_id: UUID
    dataset_id: UUID
    input_dataset_version_id: UUID
    executed_by_user_id: UUID
    decisions: list[CleaningDecisionItem]


@router.post(
    "/datasets/{dataset_id}/versions/{dataset_version_id}/cleaning-plans",
    response_model=CleaningPlan,
    status_code=201,
)
def create_cleaning_plan(
    dataset_id: UUID,
    dataset_version_id: UUID,
    body: CreateCleaningPlanRequest,
    repos: Repos = Depends(get_repos),
    llm: LLMProvider = Depends(get_llm_provider),
) -> CleaningPlan:
    service = CleaningPlanService(repos.profile, repos.cleaning_plan, llm)
    try:
        return service.create_cleaning_plan(body.profile_id, dataset_version_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/cleaning-plans/{cleaning_plan_id}", response_model=CleaningPlan)
def get_cleaning_plan(
    cleaning_plan_id: UUID,
    repos: Repos = Depends(get_repos),
) -> CleaningPlan:
    plan = repos.cleaning_plan.get(cleaning_plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"CleaningPlan {cleaning_plan_id} not found.")
    return plan


@router.post(
    "/cleaning-plans/{cleaning_plan_id}/decisions/validate",
    response_model=ValidateDecisionsResponse,
)
def validate_decisions(
    cleaning_plan_id: UUID,
    body: ValidateDecisionsRequest,
    repos: Repos = Depends(get_repos),
) -> ValidateDecisionsResponse:
    plan = repos.cleaning_plan.get(cleaning_plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"CleaningPlan {cleaning_plan_id} not found.")
    try:
        result = resolve_decisions(plan, CleaningDecisionsJson(decisions=body.decisions))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    s = result.summary
    return ValidateDecisionsResponse(
        can_execute=s.can_execute,
        total_steps=s.total_steps,
        approved_steps=s.approved_steps,
        rejected_steps=s.rejected_steps,
        modified_steps=s.modified_steps,
        blocked_steps=s.blocked_steps,
        auto_approved_steps=s.auto_approved_steps,
        skipped_steps=s.skipped_steps,
    )


@router.post(
    "/cleaning-plans/{cleaning_plan_id}/execute",
    response_model=Job,
    status_code=201,
)
def execute_cleaning_plan(
    cleaning_plan_id: UUID,
    body: ExecuteCleaningPlanRequest,
    repos: Repos = Depends(get_repos),
) -> Job:
    plan = repos.cleaning_plan.get(cleaning_plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"CleaningPlan {cleaning_plan_id} not found.")

    job = Job(
        job_id=uuid4(),
        workspace_id=body.workspace_id,
        dataset_id=body.dataset_id,
        input_dataset_version_id=body.input_dataset_version_id,
        job_type=JobType.execute_cleaning,
        status=JobStatus.queued,
        payload_json={
            "cleaning_plan_id": str(cleaning_plan_id),
            "decisions_id": str(uuid4()),
            "executed_by_user_id": str(body.executed_by_user_id),
            "decisions": [d.model_dump() for d in body.decisions],
        },
        created_at=datetime.now(tz=UTC),
    )
    return repos.job.save(job)


@router.get("/cleaning-results/{cleaning_result_id}", response_model=CleaningResult)
def get_cleaning_result(
    cleaning_result_id: UUID,
    repos: Repos = Depends(get_repos),
) -> CleaningResult:
    result = repos.cleaning_result.get(cleaning_result_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"CleaningResult {cleaning_result_id} not found.")
    return result
