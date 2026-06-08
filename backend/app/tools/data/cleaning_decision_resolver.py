"""
Deterministic cleaning decision resolver.

Given a CleaningPlan and user-provided CleaningDecisionsJson, resolves the
effective outcome for every step. No cleaning execution. No data mutation.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.schemas.cleaning import (
    CleaningDecisionItem,
    CleaningDecisionsJson,
    CleaningOperation,
    CleaningPlan,
    CleaningStep,
)
from app.schemas.common import CleaningOperationType, DefaultDecision, UserDecision

# Operations the executor supports (validated on modify).
_SUPPORTED_OPERATION_TYPES: frozenset[CleaningOperationType] = frozenset(
    {
        CleaningOperationType.ignore_issue,
        CleaningOperationType.drop_rows,
        CleaningOperationType.fill_missing,
        CleaningOperationType.deduplicate,
        CleaningOperationType.strip_whitespace,
        CleaningOperationType.cast_type,
        CleaningOperationType.parse_dates,
        CleaningOperationType.normalize_format,
    }
)


class StepOutcome(StrEnum):
    approved = "approved"
    rejected = "rejected"
    modified = "modified"
    auto_approved = "auto_approved"
    blocked = "blocked"
    skipped = "skipped"


@dataclass(frozen=True)
class StepResolution:
    step: CleaningStep
    outcome: StepOutcome
    effective_operation: CleaningOperation
    user_decision: CleaningDecisionItem | None = None


@dataclass(frozen=True)
class DecisionResolutionSummary:
    total_steps: int
    approved_steps: int
    rejected_steps: int
    modified_steps: int
    blocked_steps: int
    auto_approved_steps: int
    skipped_steps: int
    can_execute: bool


@dataclass(frozen=True)
class ResolutionResult:
    resolutions: list[StepResolution]
    summary: DecisionResolutionSummary


def _validate_decisions(
    steps: list[CleaningStep],
    decisions: list[CleaningDecisionItem],
) -> dict[UUID, CleaningDecisionItem]:
    """Validate decisions and return a lookup keyed by step_id."""
    step_ids: set[UUID] = {s.step_id for s in steps}

    # Duplicate check
    seen: set[UUID] = set()
    for d in decisions:
        if d.step_id in seen:
            raise ValueError(f"Duplicate decision for step {d.step_id}")
        seen.add(d.step_id)

    # Unknown step IDs
    for d in decisions:
        if d.step_id not in step_ids:
            raise ValueError(f"Decision references unknown step {d.step_id}")

    # Modified operations must use a supported operation type
    for d in decisions:
        if d.decision == UserDecision.modify:
            if d.modified_operation is None:
                raise ValueError(
                    f"Step {d.step_id} is marked 'modify' but no modified_operation was provided"
                )
            if d.modified_operation.operation_type not in _SUPPORTED_OPERATION_TYPES:
                raise ValueError(
                    f"Step {d.step_id} modified_operation uses unsupported type "
                    f"'{d.modified_operation.operation_type}'"
                )

    return {d.step_id: d for d in decisions}


def _resolve_step(
    step: CleaningStep,
    decision_map: dict[UUID, CleaningDecisionItem],
) -> StepResolution:
    user_dec = decision_map.get(step.step_id)

    # Explicit user decision
    if user_dec is not None:
        if user_dec.decision == UserDecision.approve:
            return StepResolution(
                step=step,
                outcome=StepOutcome.approved,
                effective_operation=step.operation,
                user_decision=user_dec,
            )
        if user_dec.decision == UserDecision.reject:
            return StepResolution(
                step=step,
                outcome=StepOutcome.rejected,
                effective_operation=step.operation,
                user_decision=user_dec,
            )
        if user_dec.decision == UserDecision.modify:
            # modified_operation already validated non-None
            return StepResolution(
                step=step,
                outcome=StepOutcome.modified,
                effective_operation=user_dec.modified_operation,  # type: ignore[arg-type]
                user_decision=user_dec,
            )

    # No user decision — apply default rules
    if step.operation.operation_type == CleaningOperationType.ignore_issue:
        return StepResolution(
            step=step,
            outcome=StepOutcome.skipped,
            effective_operation=step.operation,
        )

    if step.recommendation.requires_human_approval:
        return StepResolution(
            step=step,
            outcome=StepOutcome.blocked,
            effective_operation=step.operation,
        )

    default = step.recommendation.default_decision
    if default == DefaultDecision.approve:
        return StepResolution(
            step=step,
            outcome=StepOutcome.auto_approved,
            effective_operation=step.operation,
        )

    # require_review or reject with no user input → blocked
    return StepResolution(
        step=step,
        outcome=StepOutcome.blocked,
        effective_operation=step.operation,
    )


def resolve_decisions(
    plan: CleaningPlan,
    decisions_json: CleaningDecisionsJson,
) -> ResolutionResult:
    """
    Resolve user decisions against a CleaningPlan.

    Raises ValueError for invalid decisions (unknown step IDs, duplicates,
    unsupported modified operations, missing required approvals are NOT errors —
    they result in blocked steps).
    """
    steps = plan.plan_json.steps
    decisions = decisions_json.decisions

    decision_map = _validate_decisions(steps, decisions)

    resolutions: list[StepResolution] = [_resolve_step(s, decision_map) for s in steps]

    counts: dict[StepOutcome, int] = {o: 0 for o in StepOutcome}
    for r in resolutions:
        counts[r.outcome] += 1

    blocked = counts[StepOutcome.blocked]
    summary = DecisionResolutionSummary(
        total_steps=len(resolutions),
        approved_steps=counts[StepOutcome.approved],
        rejected_steps=counts[StepOutcome.rejected],
        modified_steps=counts[StepOutcome.modified],
        blocked_steps=blocked,
        auto_approved_steps=counts[StepOutcome.auto_approved],
        skipped_steps=counts[StepOutcome.skipped],
        can_execute=blocked == 0,
    )
    return ResolutionResult(resolutions=resolutions, summary=summary)
