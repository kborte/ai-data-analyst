"""Unit tests for the cleaning decision resolver (M5A)."""

import uuid
from datetime import UTC, datetime

import pytest

from app.schemas.cleaning import (
    CleaningDecisionItem,
    CleaningDecisionsJson,
    CleaningIssue,
    CleaningOperation,
    CleaningPlan,
    CleaningPlanJson,
    CleaningPreview,
    CleaningRecommendation,
    CleaningStep,
)
from app.schemas.common import (
    ArtifactStatus,
    CleaningOperationType,
    DefaultDecision,
    ImpactLevel,
    IssueType,
    UserDecision,
)
from app.tools.data.cleaning_decision_resolver import (
    StepOutcome,
    resolve_decisions,
)

_VERSION_ID = uuid.uuid4()
_PLAN_ID = uuid.uuid4()


def _step(
    *,
    operation_type: CleaningOperationType = CleaningOperationType.strip_whitespace,
    requires_approval: bool = False,
    default_decision: DefaultDecision = DefaultDecision.approve,
    affected_count: int = 5,
    affected_pct: float = 5.0,
) -> CleaningStep:
    sid = uuid.uuid4()
    return CleaningStep(
        step_id=sid,
        sequence_order=1,
        issue=CleaningIssue(
            issue_type=IssueType.whitespace,
            table_name="orders",
            description="test issue",
            affected_rows_count=affected_count,
            affected_rows_percent=affected_pct,
        ),
        recommendation=CleaningRecommendation(
            action_type="test",
            recommended_action="test action",
            rationale="test rationale",
            impact_level=ImpactLevel.low,
            affects_key_metrics=False,
            requires_human_approval=requires_approval,
            default_decision=default_decision,
        ),
        operation=CleaningOperation(
            operation_type=operation_type,
            parameters={},
        ),
        preview=CleaningPreview(
            rows_before=100,
            estimated_rows_after=95,
            estimated_rows_removed=5,
        ),
    )


def _plan(*steps: CleaningStep) -> CleaningPlan:
    return CleaningPlan(
        cleaning_plan_id=_PLAN_ID,
        dataset_version_id=_VERSION_ID,
        status=ArtifactStatus.completed,
        plan_json=CleaningPlanJson(steps=list(steps)),
        created_at=datetime.now(tz=UTC),
    )


def _decisions(*items: CleaningDecisionItem) -> CleaningDecisionsJson:
    return CleaningDecisionsJson(decisions=list(items))


def _approve(step: CleaningStep) -> CleaningDecisionItem:
    return CleaningDecisionItem(step_id=step.step_id, decision=UserDecision.approve)


def _reject(step: CleaningStep) -> CleaningDecisionItem:
    return CleaningDecisionItem(step_id=step.step_id, decision=UserDecision.reject)


def _modify(step: CleaningStep, op: CleaningOperation) -> CleaningDecisionItem:
    return CleaningDecisionItem(
        step_id=step.step_id, decision=UserDecision.modify, modified_operation=op
    )


# ---------------------------------------------------------------------------
# 1. Required approval missing blocks execution
# ---------------------------------------------------------------------------


def test_missing_required_approval_blocks() -> None:
    s = _step(requires_approval=True, default_decision=DefaultDecision.require_review)
    result = resolve_decisions(_plan(s), _decisions())
    res = result.resolutions[0]
    assert res.outcome == StepOutcome.blocked
    assert result.summary.blocked_steps == 1
    assert result.summary.can_execute is False


# ---------------------------------------------------------------------------
# 2. Explicit approval allows required step
# ---------------------------------------------------------------------------


def test_explicit_approval_clears_required_step() -> None:
    s = _step(requires_approval=True, default_decision=DefaultDecision.require_review)
    result = resolve_decisions(_plan(s), _decisions(_approve(s)))
    res = result.resolutions[0]
    assert res.outcome == StepOutcome.approved
    assert result.summary.can_execute is True


# ---------------------------------------------------------------------------
# 3. Explicit rejection skips step
# ---------------------------------------------------------------------------


def test_explicit_rejection_outcome() -> None:
    s = _step()
    result = resolve_decisions(_plan(s), _decisions(_reject(s)))
    res = result.resolutions[0]
    assert res.outcome == StepOutcome.rejected
    assert result.summary.rejected_steps == 1


# ---------------------------------------------------------------------------
# 4. Default-approved low-risk step executes without user decision
# ---------------------------------------------------------------------------


def test_default_approved_auto_executes() -> None:
    s = _step(requires_approval=False, default_decision=DefaultDecision.approve)
    result = resolve_decisions(_plan(s), _decisions())
    res = result.resolutions[0]
    assert res.outcome == StepOutcome.auto_approved
    assert result.summary.auto_approved_steps == 1
    assert result.summary.can_execute is True


# ---------------------------------------------------------------------------
# 5. ignore_issue operation is skipped
# ---------------------------------------------------------------------------


def test_ignore_issue_is_skipped() -> None:
    s = _step(operation_type=CleaningOperationType.ignore_issue)
    result = resolve_decisions(_plan(s), _decisions())
    res = result.resolutions[0]
    assert res.outcome == StepOutcome.skipped
    assert result.summary.skipped_steps == 1
    assert result.summary.can_execute is True


# ---------------------------------------------------------------------------
# 6. Unknown step ID is rejected with ValueError
# ---------------------------------------------------------------------------


def test_unknown_step_id_raises() -> None:
    s = _step()
    unknown = CleaningDecisionItem(step_id=uuid.uuid4(), decision=UserDecision.approve)
    with pytest.raises(ValueError, match="unknown step"):
        resolve_decisions(_plan(s), _decisions(unknown))


# ---------------------------------------------------------------------------
# 7. Duplicate decisions are rejected
# ---------------------------------------------------------------------------


def test_duplicate_decision_raises() -> None:
    s = _step()
    with pytest.raises(ValueError, match="Duplicate"):
        resolve_decisions(_plan(s), _decisions(_approve(s), _approve(s)))


# ---------------------------------------------------------------------------
# 8. Modified step validates operation type
# ---------------------------------------------------------------------------


def test_modified_step_valid_operation() -> None:
    s = _step(requires_approval=True, default_decision=DefaultDecision.require_review)
    new_op = CleaningOperation(
        operation_type=CleaningOperationType.fill_missing,
        parameters={"column": "x", "fill_value": "Unknown"},
    )
    result = resolve_decisions(_plan(s), _decisions(_modify(s, new_op)))
    res = result.resolutions[0]
    assert res.outcome == StepOutcome.modified
    assert res.effective_operation.operation_type == CleaningOperationType.fill_missing


def test_modified_step_missing_modified_operation_raises() -> None:
    s = _step()
    bad = CleaningDecisionItem(step_id=s.step_id, decision=UserDecision.modify, modified_operation=None)
    with pytest.raises(ValueError, match="no modified_operation"):
        resolve_decisions(_plan(s), _decisions(bad))


# ---------------------------------------------------------------------------
# 9. Summary counts are correct across mixed steps
# ---------------------------------------------------------------------------


def test_summary_counts_mixed() -> None:
    auto = _step(requires_approval=False, default_decision=DefaultDecision.approve)
    blocked = _step(requires_approval=True, default_decision=DefaultDecision.require_review)
    ignored = _step(operation_type=CleaningOperationType.ignore_issue)
    explicit = _step(requires_approval=True, default_decision=DefaultDecision.require_review)
    rejected = _step()

    result = resolve_decisions(
        _plan(auto, blocked, ignored, explicit, rejected),
        _decisions(_approve(explicit), _reject(rejected)),
    )
    s = result.summary
    assert s.total_steps == 5
    assert s.auto_approved_steps == 1
    assert s.blocked_steps == 1
    assert s.skipped_steps == 1
    assert s.approved_steps == 1
    assert s.rejected_steps == 1
    assert s.modified_steps == 0
    assert s.can_execute is False  # one blocked step


def test_summary_can_execute_true_when_no_blocked() -> None:
    auto = _step(requires_approval=False, default_decision=DefaultDecision.approve)
    ignored = _step(operation_type=CleaningOperationType.ignore_issue)
    explicit = _step(requires_approval=True, default_decision=DefaultDecision.require_review)

    result = resolve_decisions(
        _plan(auto, ignored, explicit),
        _decisions(_approve(explicit)),
    )
    assert result.summary.can_execute is True
    assert result.summary.blocked_steps == 0
