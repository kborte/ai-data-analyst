"""Unit tests for the deterministic cleaning executor (M5B)."""

import uuid

import pandas as pd

from app.schemas.cleaning import (
    CleaningIssue,
    CleaningOperation,
    CleaningPreview,
    CleaningRecommendation,
    CleaningStep,
)
from app.schemas.common import (
    CleaningOperationType,
    DefaultDecision,
    ExecutionStatus,
    ImpactLevel,
    IssueType,
)
from app.tools.data.cleaning_decision_resolver import StepOutcome, StepResolution
from app.tools.data.cleaning_executor import execute_cleaning


def _resolution(
    operation_type: CleaningOperationType,
    params: dict,
    table: str = "orders",
    outcome: StepOutcome = StepOutcome.auto_approved,
) -> StepResolution:
    step_id = uuid.uuid4()
    op = CleaningOperation(operation_type=operation_type, parameters=params)
    step = CleaningStep(
        step_id=step_id,
        sequence_order=1,
        issue=CleaningIssue(
            issue_type=IssueType.whitespace,
            table_name=table,
            description="test",
            affected_rows_count=1,
            affected_rows_percent=1.0,
        ),
        recommendation=CleaningRecommendation(
            action_type="test",
            recommended_action="test",
            rationale="test",
            impact_level=ImpactLevel.low,
            affects_key_metrics=False,
            requires_human_approval=False,
            default_decision=DefaultDecision.approve,
        ),
        operation=op,
        preview=CleaningPreview(rows_before=5, estimated_rows_after=5, estimated_rows_removed=0),
    )
    return StepResolution(step=step, outcome=outcome, effective_operation=op)


# ---------------------------------------------------------------------------
# 1. Drop rows with missing revenue
# ---------------------------------------------------------------------------


def test_drop_rows_missing_revenue() -> None:
    df = pd.DataFrame({"revenue": [100.0, None, 300.0], "product": ["A", "B", "C"]})
    res = _resolution(CleaningOperationType.drop_rows, {"column": "revenue"})
    result = execute_cleaning({"orders": df}, [res])
    out = result.tables["orders"]
    assert len(out) == 2
    assert out["revenue"].notna().all()
    sr = result.step_results[0]
    assert sr.status == ExecutionStatus.success
    assert sr.rows_removed == 1


# ---------------------------------------------------------------------------
# 2. Fill missing country with Unknown
# ---------------------------------------------------------------------------


def test_fill_missing_country() -> None:
    df = pd.DataFrame({"country": ["US", None, "UK", None]})
    res = _resolution(
        CleaningOperationType.fill_missing,
        {"column": "country", "fill_value": "Unknown"},
    )
    result = execute_cleaning({"orders": df}, [res])
    out = result.tables["orders"]
    assert (out["country"] == "Unknown").sum() == 2
    assert result.step_results[0].status == ExecutionStatus.success


# ---------------------------------------------------------------------------
# 3. Remove exact duplicates
# ---------------------------------------------------------------------------


def test_remove_exact_duplicates() -> None:
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    res = _resolution(CleaningOperationType.deduplicate, {})
    result = execute_cleaning({"orders": df}, [res])
    assert len(result.tables["orders"]) == 2
    assert result.step_results[0].rows_removed == 1


# ---------------------------------------------------------------------------
# 4. Trim whitespace in product names
# ---------------------------------------------------------------------------


def test_trim_whitespace() -> None:
    df = pd.DataFrame({"product": ["  Widget  ", "Gadget", "  Doohickey"]})
    res = _resolution(CleaningOperationType.strip_whitespace, {"column": "product"})
    result = execute_cleaning({"orders": df}, [res])
    out = result.tables["orders"]
    assert out["product"].tolist() == ["Widget", "Gadget", "Doohickey"]
    assert result.step_results[0].status == ExecutionStatus.success


# ---------------------------------------------------------------------------
# 5. Convert numeric stored as text
# ---------------------------------------------------------------------------


def test_convert_numeric() -> None:
    df = pd.DataFrame({"revenue": ["100", "200", "not_a_number", "400"]})
    res = _resolution(CleaningOperationType.cast_type, {"column": "revenue"})
    result = execute_cleaning({"orders": df}, [res])
    out = result.tables["orders"]
    assert pd.api.types.is_float_dtype(out["revenue"])
    assert out["revenue"].iloc[0] == 100.0
    assert pd.isna(out["revenue"].iloc[2])


# ---------------------------------------------------------------------------
# 6. Parse dates stored as text
# ---------------------------------------------------------------------------


def test_parse_dates() -> None:
    df = pd.DataFrame({"order_date": ["2024-01-01", "2024-01-02", "not-a-date"]})
    res = _resolution(CleaningOperationType.parse_dates, {"column": "order_date"})
    result = execute_cleaning({"orders": df}, [res])
    out = result.tables["orders"]
    assert pd.api.types.is_datetime64_any_dtype(out["order_date"])
    assert pd.isna(out["order_date"].iloc[2])


# ---------------------------------------------------------------------------
# 7. Standardize categories using explicit mapping
# ---------------------------------------------------------------------------


def test_standardize_categories() -> None:
    df = pd.DataFrame({"status": ["complete", "COMPLETE", "completed", "Pending"]})
    mapping = {"complete": "Completed", "COMPLETE": "Completed", "completed": "Completed"}
    res = _resolution(
        CleaningOperationType.normalize_format,
        {"column": "status", "mapping": mapping},
    )
    result = execute_cleaning({"orders": df}, [res])
    out = result.tables["orders"]
    assert (out["status"] == "Completed").sum() == 3
    assert out["status"].iloc[3] == "Pending"


# ---------------------------------------------------------------------------
# 8. ignore_issue does not change data
# ---------------------------------------------------------------------------


def test_ignore_issue_no_change() -> None:
    df = pd.DataFrame({"col": [1, 2, 3]})
    res = _resolution(CleaningOperationType.ignore_issue, {})
    result = execute_cleaning({"orders": df}, [res])
    pd.testing.assert_frame_equal(result.tables["orders"], df)
    assert result.step_results[0].status == ExecutionStatus.skipped


# ---------------------------------------------------------------------------
# 9. Input DataFrame is not mutated
# ---------------------------------------------------------------------------


def test_input_not_mutated() -> None:
    df = pd.DataFrame({"country": ["US", None, "UK"]})
    original = df.copy()
    res = _resolution(
        CleaningOperationType.fill_missing,
        {"column": "country", "fill_value": "Unknown"},
    )
    execute_cleaning({"orders": df}, [res])
    pd.testing.assert_frame_equal(df, original)


def test_drop_rows_input_not_mutated() -> None:
    df = pd.DataFrame({"revenue": [1.0, None, 3.0]})
    original = df.copy()
    res = _resolution(CleaningOperationType.drop_rows, {"column": "revenue"})
    execute_cleaning({"orders": df}, [res])
    pd.testing.assert_frame_equal(df, original)


# ---------------------------------------------------------------------------
# 10. Execution log records row/column changes
# ---------------------------------------------------------------------------


def test_execution_log_records_changes() -> None:
    df = pd.DataFrame({"revenue": [100.0, None, None, 400.0]})
    res = _resolution(CleaningOperationType.drop_rows, {"column": "revenue"})
    result = execute_cleaning({"orders": df}, [res])
    sr = result.step_results[0]
    assert sr.rows_before == 4
    assert sr.rows_after == 2
    assert sr.rows_removed == 2
    assert "revenue" in sr.columns_changed


def test_skipped_steps_recorded() -> None:
    df = pd.DataFrame({"col": [1, 2]})
    res = _resolution(
        CleaningOperationType.strip_whitespace,
        {"column": "col"},
        outcome=StepOutcome.rejected,
    )
    result = execute_cleaning({"orders": df}, [res])
    assert result.step_results[0].status == ExecutionStatus.skipped
    assert len(result.tables["orders"]) == 2
