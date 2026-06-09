from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.repositories.memory import CleaningPlanRepository, DataProfileRepository
from app.schemas.cleaning import (
    CleaningOperationType,
    CleaningPlan,
    CleaningPlanJson,
    CleaningPlanSummary,
    CleaningStep,
)
from app.schemas.common import ArtifactStatus
from app.tools.data.cleaning_rule_engine import generate_cleaning_steps
from app.tools.llm.prompts import CLEANING_ENRICH_SCHEMA, cleaning_enrich_prompt
from app.tools.llm.provider import FakeLLMProvider, LLMProvider

_IGNORE_OPS = {CleaningOperationType.ignore_issue}
_GLOBAL_ASSUMPTIONS = [
    "Original dataset is never modified.",
    "Cleaning creates a new dataset version in a later milestone.",
    "Steps marked require_review must be approved before execution.",
]
# LLM only called for steps above this affected-row threshold to limit tokens.
_LLM_ENRICH_THRESHOLD_PCT = 5.0


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


def _enrich_steps_with_llm(
    steps: list[CleaningStep],
    table_name: str,
    llm: LLMProvider,
) -> list[CleaningStep]:
    """
    ONE LLM call: sends only high-impact steps (requires_human_approval=True
    and affected_rows_percent >= threshold) for rationale enrichment.
    Falls back to original steps on any failure.
    """
    candidates = [
        s for s in steps
        if s.recommendation.requires_human_approval
        and s.issue.affected_rows_percent >= _LLM_ENRICH_THRESHOLD_PCT
    ]
    if not candidates:
        return steps

    prompt = cleaning_enrich_prompt(candidates, table_name)
    result = llm.complete_structured(prompt, "enrich_cleaning_steps", CLEANING_ENRICH_SCHEMA)
    enriched_map: dict[str, dict] = {
        e["step_id"]: e for e in result.get("enriched_steps", [])
    }
    if not enriched_map:
        return steps

    out: list[CleaningStep] = []
    for step in steps:
        enriched = enriched_map.get(str(step.step_id))
        if enriched:
            rec = step.recommendation.model_copy(update={
                "rationale": enriched.get("rationale", step.recommendation.rationale),
                "recommended_action": enriched.get(
                    "recommended_action", step.recommendation.recommended_action
                ),
            })
            out.append(step.model_copy(update={"recommendation": rec}))
        else:
            out.append(step)
    return out


class CleaningPlanService:
    def __init__(
        self,
        profile_repo: DataProfileRepository,
        cleaning_plan_repo: CleaningPlanRepository,
        llm: LLMProvider | None = None,
    ) -> None:
        self._profiles = profile_repo
        self._plans = cleaning_plan_repo
        self._llm = llm or FakeLLMProvider()

    def create_cleaning_plan(
        self,
        profile_id: UUID,
        dataset_version_id: UUID,
    ) -> CleaningPlan:
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise ValueError(f"DataProfile {profile_id} not found")

        steps = generate_cleaning_steps(profile)

        if self._llm.is_available():
            steps = _enrich_steps_with_llm(steps, profile.table_name, self._llm)

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
