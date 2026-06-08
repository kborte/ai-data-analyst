"""Unit tests for the deterministic cleaning rule engine (M4A)."""

import uuid
from datetime import UTC, datetime

from app.schemas.common import (
    CleaningOperationType,
    DefaultDecision,
    ImpactLevel,
    IssueType,
)
from app.schemas.profile import DataProfile, DataQualityIssue
from app.tools.data.cleaning_rule_engine import generate_cleaning_steps

_PROFILE_ID = uuid.uuid4()
_VERSION_ID = uuid.uuid4()


def _make_profile(
    issues: list[DataQualityIssue],
    *,
    row_count: int = 100,
    metric_cols: list[str] | None = None,
    date_cols: list[str] | None = None,
    id_cols: list[str] | None = None,
    cat_cols: list[str] | None = None,
) -> DataProfile:
    return DataProfile(
        profile_id=_PROFILE_ID,
        dataset_version_id=_VERSION_ID,
        table_name="orders",
        row_count=row_count,
        column_count=len({i.column_name for i in issues if i.column_name}),
        column_profiles=[],
        quality_issues=issues,
        likely_metric_columns=metric_cols or [],
        likely_date_columns=date_cols or [],
        likely_id_columns=id_cols or [],
        likely_categorical_columns=cat_cols or [],
        created_at=datetime.now(tz=UTC),
    )


def _issue(
    issue_type: IssueType,
    column: str | None,
    *,
    affected_count: int = 10,
    affected_pct: float = 10.0,
) -> DataQualityIssue:
    return DataQualityIssue(
        issue_type=issue_type,
        table_name="orders",
        column_name=column,
        description="test issue",
        affected_rows_count=affected_count,
        affected_rows_percent=affected_pct,
        impact_level=ImpactLevel.medium,
    )


# ---------------------------------------------------------------------------
# 1. Missing revenue requires approval
# ---------------------------------------------------------------------------


def test_missing_revenue_requires_approval() -> None:
    issue = _issue(IssueType.missing_values, "revenue", affected_count=5, affected_pct=5.0)
    profile = _make_profile([issue], metric_cols=["revenue"])
    steps = generate_cleaning_steps(profile)
    assert len(steps) == 1
    rec = steps[0].recommendation
    assert rec.requires_human_approval is True
    assert rec.default_decision == DefaultDecision.require_review
    assert rec.affects_key_metrics is True


def test_missing_revenue_operation_is_drop_rows() -> None:
    issue = _issue(IssueType.missing_values, "revenue", affected_count=5, affected_pct=5.0)
    profile = _make_profile([issue], metric_cols=["revenue"])
    steps = generate_cleaning_steps(profile)
    assert steps[0].operation.operation_type == CleaningOperationType.drop_rows


# ---------------------------------------------------------------------------
# 2. Missing notes column is auto-approved (low-importance column)
# ---------------------------------------------------------------------------


def test_missing_notes_default_approved() -> None:
    issue = _issue(IssueType.missing_values, "notes", affected_count=3, affected_pct=3.0)
    profile = _make_profile([issue])  # notes not in any "likely" list
    steps = generate_cleaning_steps(profile)
    assert len(steps) == 1
    rec = steps[0].recommendation
    assert rec.requires_human_approval is False
    assert rec.default_decision == DefaultDecision.approve


def test_missing_notes_operation_is_ignore() -> None:
    issue = _issue(IssueType.missing_values, "notes", affected_count=3, affected_pct=3.0)
    profile = _make_profile([issue])
    steps = generate_cleaning_steps(profile)
    assert steps[0].operation.operation_type == CleaningOperationType.ignore_issue


# ---------------------------------------------------------------------------
# 3. Duplicate rows require approval
# ---------------------------------------------------------------------------


def test_duplicate_rows_require_approval() -> None:
    issue = _issue(IssueType.duplicate_rows, None, affected_count=8, affected_pct=8.0)
    profile = _make_profile([issue])
    steps = generate_cleaning_steps(profile)
    assert len(steps) == 1
    rec = steps[0].recommendation
    assert rec.requires_human_approval is True
    assert rec.default_decision == DefaultDecision.require_review
    assert rec.affects_key_metrics is True


def test_duplicate_rows_operation_is_deduplicate() -> None:
    issue = _issue(IssueType.duplicate_rows, None)
    profile = _make_profile([issue])
    steps = generate_cleaning_steps(profile)
    assert steps[0].operation.operation_type == CleaningOperationType.deduplicate


# ---------------------------------------------------------------------------
# 4. Whitespace defaults to approved
# ---------------------------------------------------------------------------


def test_whitespace_default_approved() -> None:
    issue = _issue(IssueType.whitespace, "country")
    profile = _make_profile([issue])
    steps = generate_cleaning_steps(profile)
    assert len(steps) == 1
    rec = steps[0].recommendation
    assert rec.requires_human_approval is False
    assert rec.default_decision == DefaultDecision.approve


def test_whitespace_operation_is_strip() -> None:
    issue = _issue(IssueType.whitespace, "country")
    profile = _make_profile([issue])
    steps = generate_cleaning_steps(profile)
    assert steps[0].operation.operation_type == CleaningOperationType.strip_whitespace


# ---------------------------------------------------------------------------
# 5. Numeric stored as text in revenue requires approval
# ---------------------------------------------------------------------------


def test_numeric_as_text_revenue_requires_approval() -> None:
    issue = _issue(IssueType.numeric_stored_as_text, "revenue")
    profile = _make_profile([issue], metric_cols=["revenue"])
    steps = generate_cleaning_steps(profile)
    assert len(steps) == 1
    rec = steps[0].recommendation
    assert rec.requires_human_approval is True
    assert rec.default_decision == DefaultDecision.require_review
    assert rec.affects_key_metrics is True


def test_numeric_as_text_non_metric_auto_approved() -> None:
    issue = _issue(IssueType.numeric_stored_as_text, "zip_code")
    profile = _make_profile([issue])  # zip_code not in metric cols
    steps = generate_cleaning_steps(profile)
    rec = steps[0].recommendation
    assert rec.requires_human_approval is False
    assert rec.default_decision == DefaultDecision.approve


# ---------------------------------------------------------------------------
# 6. Date stored as text in date column requires approval
# ---------------------------------------------------------------------------


def test_date_as_text_date_col_requires_approval() -> None:
    issue = _issue(IssueType.date_stored_as_text, "order_date")
    profile = _make_profile([issue], date_cols=["order_date"])
    steps = generate_cleaning_steps(profile)
    assert len(steps) == 1
    rec = steps[0].recommendation
    assert rec.requires_human_approval is True
    assert rec.default_decision == DefaultDecision.require_review


def test_date_as_text_operation_is_parse_dates() -> None:
    issue = _issue(IssueType.date_stored_as_text, "order_date")
    profile = _make_profile([issue], date_cols=["order_date"])
    steps = generate_cleaning_steps(profile)
    assert steps[0].operation.operation_type == CleaningOperationType.parse_dates


# ---------------------------------------------------------------------------
# 7. High-cardinality category is ignored / auto-approved
# ---------------------------------------------------------------------------


def test_high_cardinality_auto_approved() -> None:
    issue = _issue(IssueType.high_cardinality_category, "product_name")
    profile = _make_profile([issue])
    steps = generate_cleaning_steps(profile)
    assert len(steps) == 1
    rec = steps[0].recommendation
    assert rec.requires_human_approval is False
    assert rec.default_decision == DefaultDecision.approve


def test_high_cardinality_operation_is_ignore() -> None:
    issue = _issue(IssueType.high_cardinality_category, "product_name")
    profile = _make_profile([issue])
    steps = generate_cleaning_steps(profile)
    assert steps[0].operation.operation_type == CleaningOperationType.ignore_issue


# ---------------------------------------------------------------------------
# 8. Stable sequence order and valid schema
# ---------------------------------------------------------------------------


def test_steps_have_stable_sequence_order() -> None:
    issues = [
        _issue(IssueType.missing_values, "revenue"),
        _issue(IssueType.duplicate_rows, None),
        _issue(IssueType.whitespace, "country"),
    ]
    profile = _make_profile(issues, metric_cols=["revenue"])
    steps = generate_cleaning_steps(profile)
    assert [s.sequence_order for s in steps] == [1, 2, 3]


def test_step_ids_are_deterministic() -> None:
    issues = [_issue(IssueType.whitespace, "country")]
    profile = _make_profile(issues)
    steps_a = generate_cleaning_steps(profile)
    steps_b = generate_cleaning_steps(profile)
    assert steps_a[0].step_id == steps_b[0].step_id


def test_step_ids_differ_by_position() -> None:
    issues = [
        _issue(IssueType.whitespace, "country"),
        _issue(IssueType.whitespace, "city"),
    ]
    profile = _make_profile(issues)
    steps = generate_cleaning_steps(profile)
    assert steps[0].step_id != steps[1].step_id


def test_empty_issues_returns_empty_list() -> None:
    profile = _make_profile([])
    steps = generate_cleaning_steps(profile)
    assert steps == []


def test_unknown_issue_type_is_skipped() -> None:
    """Issues whose type has no handler are silently skipped."""
    issue = _issue(IssueType.outlier, "revenue")
    profile = _make_profile([issue])
    steps = generate_cleaning_steps(profile)
    assert steps == []


def test_preview_reflects_row_removal_for_drop() -> None:
    issue = _issue(IssueType.missing_values, "revenue", affected_count=10, affected_pct=10.0)
    profile = _make_profile([issue], row_count=100, metric_cols=["revenue"])
    steps = generate_cleaning_steps(profile)
    preview = steps[0].preview
    assert preview.rows_before == 100
    assert preview.estimated_rows_removed == 10
    assert preview.estimated_rows_after == 90


def test_preview_no_row_change_for_fill() -> None:
    issue = _issue(IssueType.missing_values, "segment", affected_count=5, affected_pct=5.0)
    profile = _make_profile([issue], row_count=100, cat_cols=["segment"])
    steps = generate_cleaning_steps(profile)
    preview = steps[0].preview
    assert preview.estimated_rows_removed == 0
    assert preview.estimated_rows_after == 100
