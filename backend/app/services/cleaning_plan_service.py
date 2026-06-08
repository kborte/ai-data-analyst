"""
CleaningPlanService: builds and persists CleaningPlan objects.

No LLM calls. No cleaning execution. No dataset mutation.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.repositories.memory import CleaningPlanRepository, DataProfileRepository
from app.schemas.cleaning import (
    CleaningOperationType,
    CleaningPlan,
    CleaningPlanJson,
    CleaningPlanSummary,
)
from app.schemas.common import ArtifactStatus
from app.tools.data.cleaning_rule_engine import generate_cleaning_steps

_IGNORE_OPS = {CleaningOperationType.ignore_issue}
_GLOBAL_ASSUMPTIONS = [
    "Original dataset is never modified.",
    "Cleaning creates a new dataset version in a later milestone.",
    "Steps marked require_review must be approved before execution.",
]


def _build_summary(steps: list) -> CleaningPlanSummary:
    approval_required = sum(1 for s in steps if s.recommendation.requires_human_approval)
    auto_ignored = sum(1 for s in steps if s.operation.operation_type in _IGNORE_OPS)
    auto_approved = len(steps) - approval_required - auto_ignored
    row_change = sum(s.preview.estimated_rows_removed for s in steps)
    cols_changed: list[str] = []
    seen: set[str] = set()
    for s in steps:
        for c in s.preview.columns_changed:
            if c not in seen:
                cols_changed.append(c)
                seen.add(c)
    return CleaningPlanSummary(
        total_steps=len(steps),
        steps_requiring_approval=approval_required,
        auto_approved_steps=max(auto_approved, 0),
        auto_ignored_steps=auto_ignored,
        estimated_row_count_change=row_change,
        estimated_columns_changed=cols_changed,
    )


class CleaningPlanService:
    def __init__(
        self,
        profile_repo: DataProfileRepository,
        cleaning_plan_repo: CleaningPlanRepository,
    ) -> None:
        self._profiles = profile_repo
        self._plans = cleaning_plan_repo

    def create_cleaning_plan(
        self,
        profile_id: UUID,
        dataset_version_id: UUID,
    ) -> CleaningPlan:
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise ValueError(f"DataProfile {profile_id} not found")

        steps = generate_cleaning_steps(profile)
        now = datetime.now(tz=UTC)
        plan_id = uuid4()
        summary = _build_summary(steps)

        plan_json = CleaningPlanJson(
            plan_id=plan_id,
            dataset_version_id=dataset_version_id,
            profile_id=profile_id,
            created_at=now,
            summary=summary,
            global_assumptions=_GLOBAL_ASSUMPTIONS,
            steps=steps,
        )
        plan = CleaningPlan(
            cleaning_plan_id=plan_id,
            dataset_version_id=dataset_version_id,
            status=ArtifactStatus.completed,
            plan_json=plan_json,
            created_at=now,
        )
        return self._plans.save(plan)
