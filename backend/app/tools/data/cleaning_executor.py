"""
Deterministic cleaning executor.

Applies approved CleaningOperations to pandas DataFrames.
Never mutates input data. Returns cleaned copies and per-step results.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pandas as pd

from app.schemas.common import CleaningOperationType, ExecutionStatus
from app.tools.data.cleaning_decision_resolver import StepOutcome, StepResolution

_EXECUTE_OUTCOMES: frozenset[StepOutcome] = frozenset(
    {StepOutcome.approved, StepOutcome.auto_approved, StepOutcome.modified}
)


@dataclass
class StepExecutionResult:
    step_id: UUID
    operation_type: CleaningOperationType
    status: ExecutionStatus
    rows_before: int
    rows_after: int
    rows_changed: int
    rows_removed: int
    columns_changed: list[str] = field(default_factory=list)
    message: str = ""
    error: str | None = None


@dataclass
class ExecutionResult:
    tables: dict[str, pd.DataFrame]
    step_results: list[StepExecutionResult]


# ---------------------------------------------------------------------------
# Operation handlers — each receives the working copy and parameters,
# returns the (possibly new) DataFrame for that table.
# ---------------------------------------------------------------------------


def _handle_ignore(_df: pd.DataFrame, _params: dict[str, Any]) -> pd.DataFrame:
    return _df


def _handle_drop_rows(df: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    col = params.get("column")
    if not col or col not in df.columns:
        return df
    return df.dropna(subset=[col]).reset_index(drop=True)


def _handle_fill_missing(df: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    col = params.get("column")
    fill_value = params.get("fill_value", "Unknown")
    if not col or col not in df.columns:
        return df
    result = df.copy()
    result[col] = result[col].fillna(fill_value)
    return result


def _handle_deduplicate(df: pd.DataFrame, _params: dict[str, Any]) -> pd.DataFrame:
    return df.drop_duplicates().reset_index(drop=True)


def _handle_strip_whitespace(df: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    col = params.get("column")
    if not col or col not in df.columns:
        return df
    result = df.copy()
    result[col] = result[col].astype(str).str.strip().where(df[col].notna(), other=None)
    return result


def _handle_cast_type(df: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    col = params.get("column")
    if not col or col not in df.columns:
        return df
    result = df.copy()
    result[col] = pd.to_numeric(result[col], errors="coerce")
    return result


def _handle_parse_dates(df: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    col = params.get("column")
    if not col or col not in df.columns:
        return df
    result = df.copy()
    result[col] = pd.to_datetime(result[col], errors="coerce", format="mixed")
    return result


def _handle_normalize_format(df: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    col = params.get("column")
    mapping: dict[str, str] = params.get("mapping", {})
    if not col or col not in df.columns or not mapping:
        return df
    result = df.copy()
    result[col] = result[col].replace(mapping)
    return result


_HANDLERS = {
    CleaningOperationType.ignore_issue: _handle_ignore,
    CleaningOperationType.drop_rows: _handle_drop_rows,
    CleaningOperationType.fill_missing: _handle_fill_missing,
    CleaningOperationType.deduplicate: _handle_deduplicate,
    CleaningOperationType.strip_whitespace: _handle_strip_whitespace,
    CleaningOperationType.cast_type: _handle_cast_type,
    CleaningOperationType.parse_dates: _handle_parse_dates,
    CleaningOperationType.normalize_format: _handle_normalize_format,
}


def execute_cleaning(
    tables: dict[str, pd.DataFrame],
    resolutions: list[StepResolution],
) -> ExecutionResult:
    """
    Apply approved cleaning operations to tables.

    Input DataFrames are never mutated; all changes are applied to copies.
    """
    working: dict[str, pd.DataFrame] = {name: df.copy() for name, df in tables.items()}
    step_results: list[StepExecutionResult] = []

    for resolution in resolutions:
        step = resolution.step
        op = resolution.effective_operation
        table_name = step.issue.table_name
        rows_before = len(working.get(table_name, pd.DataFrame()))

        if resolution.outcome not in _EXECUTE_OUTCOMES:
            step_results.append(
                StepExecutionResult(
                    step_id=step.step_id,
                    operation_type=op.operation_type,
                    status=ExecutionStatus.skipped,
                    rows_before=rows_before,
                    rows_after=rows_before,
                    rows_changed=0,
                    rows_removed=0,
                    message=f"Step {resolution.outcome}",
                )
            )
            continue

        handler = _HANDLERS.get(op.operation_type)
        if handler is None:
            step_results.append(
                StepExecutionResult(
                    step_id=step.step_id,
                    operation_type=op.operation_type,
                    status=ExecutionStatus.failed,
                    rows_before=rows_before,
                    rows_after=rows_before,
                    rows_changed=0,
                    rows_removed=0,
                    error=f"Unsupported operation: {op.operation_type}",
                )
            )
            continue

        df = working.get(table_name)
        if df is None:
            step_results.append(
                StepExecutionResult(
                    step_id=step.step_id,
                    operation_type=op.operation_type,
                    status=ExecutionStatus.failed,
                    rows_before=0,
                    rows_after=0,
                    rows_changed=0,
                    rows_removed=0,
                    error=f"Table '{table_name}' not found",
                )
            )
            continue

        try:
            new_df = handler(df, op.parameters)
        except Exception as exc:  # noqa: BLE001
            step_results.append(
                StepExecutionResult(
                    step_id=step.step_id,
                    operation_type=op.operation_type,
                    status=ExecutionStatus.failed,
                    rows_before=rows_before,
                    rows_after=rows_before,
                    rows_changed=0,
                    rows_removed=0,
                    error=str(exc),
                )
            )
            continue

        rows_after = len(new_df)
        col = op.parameters.get("column")
        working[table_name] = new_df
        step_results.append(
            StepExecutionResult(
                step_id=step.step_id,
                operation_type=op.operation_type,
                status=ExecutionStatus.success
                if op.operation_type != CleaningOperationType.ignore_issue
                else ExecutionStatus.skipped,
                rows_before=rows_before,
                rows_after=rows_after,
                rows_changed=rows_before - rows_after,
                rows_removed=max(rows_before - rows_after, 0),
                columns_changed=[col] if col else [],
                message=f"{op.operation_type} applied",
            )
        )

    return ExecutionResult(tables=working, step_results=step_results)
