"""
Deterministic feature executor.

Applies approved FeatureDefinitions to pandas DataFrames.
Never mutates input data. Returns enriched copies and per-feature results.
"""

from dataclasses import dataclass, field
from uuid import UUID

import pandas as pd

from app.schemas.common import ExecutionStatus, FeatureOperationType
from app.schemas.features import FeatureDefinition


@dataclass
class FeatureStepResult:
    feature_id: UUID
    feature_name: str
    operation_type: FeatureOperationType
    status: ExecutionStatus
    output_columns: list[str] = field(default_factory=list)
    output_table: str | None = None
    message: str = ""
    error: str | None = None


@dataclass
class FeatureExecutionResult:
    tables: dict[str, pd.DataFrame]      # enriched input tables (copies)
    new_tables: dict[str, pd.DataFrame]  # new tables created by aggregate
    step_results: list[FeatureStepResult]


# ---------------------------------------------------------------------------
# Column-op handlers — return (new_df, added_column_names)
# ---------------------------------------------------------------------------


def _apply_ratio(df: pd.DataFrame, feature: FeatureDefinition) -> tuple[pd.DataFrame, list[str]]:
    p = feature.parameters
    num = p["numerator"]
    den = p["denominator"]
    out = feature.output_column or f"{num}_per_{den}"
    result = df.copy()
    denom = df[den].astype(float)
    result[out] = df[num].astype(float) / denom.where(denom != 0)
    return result, [out]


def _apply_arithmetic(df: pd.DataFrame, feature: FeatureDefinition) -> tuple[pd.DataFrame, list[str]]:
    p = feature.parameters
    left = df[p["left"]].astype(float)
    right = df[p["right"]].astype(float)
    op = p.get("operator", "+")
    out = feature.output_column or "result"
    result = df.copy()
    if op == "+":
        result[out] = left + right
    elif op == "-":
        result[out] = left - right
    elif op == "*":
        result[out] = left * right
    elif op == "/":
        result[out] = left / right.where(right != 0)
    else:
        raise ValueError(f"Unknown operator: {op}")
    return result, [out]


def _apply_window(df: pd.DataFrame, feature: FeatureDefinition) -> tuple[pd.DataFrame, list[str]]:
    p = feature.parameters
    val = p["value_column"]
    sort = p["sort_column"]
    partition = p.get("partition_column")
    out = feature.output_column or f"running_{val}"
    result = df.copy()
    if partition:
        result[out] = (
            df.sort_values(sort)
            .groupby(partition)[val]
            .cumsum()
            .reindex(df.index)
        )
    else:
        result[out] = df.sort_values(sort)[val].cumsum().reindex(df.index)
    return result, [out]


def _apply_period_change(df: pd.DataFrame, feature: FeatureDefinition) -> tuple[pd.DataFrame, list[str]]:
    p = feature.parameters
    val = p["value_column"]
    sort = p.get("sort_column")
    periods = int(p.get("periods", 1))
    out = feature.output_column or f"{val}_pct_change"
    result = df.copy()
    series = df.sort_values(sort)[val] if sort else df[val]
    result[out] = series.pct_change(periods=periods).reindex(df.index)
    return result, [out]


def _apply_date_extract(df: pd.DataFrame, feature: FeatureDefinition) -> tuple[pd.DataFrame, list[str]]:
    p = feature.parameters
    col = p["source_column"]
    parts = p.get("parts", ["year", "month", "week", "weekday"])
    result = df.copy()
    dt = pd.to_datetime(df[col], errors="coerce")
    added: list[str] = []
    for part in parts:
        out_col = f"{col}_{part}"
        if part == "year":
            result[out_col] = dt.dt.year
        elif part == "month":
            result[out_col] = dt.dt.month
        elif part == "week":
            result[out_col] = dt.dt.isocalendar().week.astype("Int64")
        elif part == "weekday":
            result[out_col] = dt.dt.weekday
        elif part == "day":
            result[out_col] = dt.dt.day
        added.append(out_col)
    return result, added


def _apply_bucketize(df: pd.DataFrame, feature: FeatureDefinition) -> tuple[pd.DataFrame, list[str]]:
    p = feature.parameters
    col = p["column"]
    bins = p["bins"]
    labels = p.get("labels")
    out = feature.output_column or f"{col}_bucket"
    result = df.copy()
    result[out] = pd.cut(df[col], bins=bins, labels=labels)
    return result, [out]


def _apply_aggregate(df: pd.DataFrame, feature: FeatureDefinition) -> tuple[pd.DataFrame, str]:
    p = feature.parameters
    val = p["value_column"]
    group_by = p["group_by"]
    agg = p.get("aggregation", "sum")
    out_table = feature.output_table or f"{group_by}_{val}_agg"
    grouped = df.groupby(group_by, as_index=False)[val].agg(agg)
    grouped = grouped.rename(columns={val: f"{val}_{agg}"})
    return grouped, out_table


_COLUMN_HANDLERS = {
    FeatureOperationType.ratio: _apply_ratio,
    FeatureOperationType.arithmetic: _apply_arithmetic,
    FeatureOperationType.window: _apply_window,
    FeatureOperationType.period_change: _apply_period_change,
    FeatureOperationType.date_extract: _apply_date_extract,
    FeatureOperationType.bucketize: _apply_bucketize,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def execute_features(
    tables: dict[str, pd.DataFrame],
    features: list[FeatureDefinition],
) -> FeatureExecutionResult:
    """
    Apply approved feature definitions to tables.

    Input DataFrames are never mutated; all changes are applied to copies.
    custom_formula always returns a failed result.
    """
    working: dict[str, pd.DataFrame] = {name: df.copy() for name, df in tables.items()}
    new_tables: dict[str, pd.DataFrame] = {}
    step_results: list[FeatureStepResult] = []

    for feature in features:
        fid = feature.feature_id
        fname = feature.feature_name
        op = feature.operation_type

        if op == FeatureOperationType.custom_formula:
            step_results.append(FeatureStepResult(
                feature_id=fid,
                feature_name=fname,
                operation_type=op,
                status=ExecutionStatus.failed,
                error="custom_formula is not supported for execution",
            ))
            continue

        table_name = feature.input_table
        df = working.get(table_name)
        if df is None:
            step_results.append(FeatureStepResult(
                feature_id=fid,
                feature_name=fname,
                operation_type=op,
                status=ExecutionStatus.failed,
                error=f"Table '{table_name}' not found",
            ))
            continue

        missing = [c for c in feature.required_columns if c not in df.columns]
        if missing:
            step_results.append(FeatureStepResult(
                feature_id=fid,
                feature_name=fname,
                operation_type=op,
                status=ExecutionStatus.failed,
                error=f"Missing required columns: {missing}",
            ))
            continue

        try:
            if op == FeatureOperationType.aggregate:
                new_df, out_table = _apply_aggregate(df, feature)
                new_tables[out_table] = new_df
                step_results.append(FeatureStepResult(
                    feature_id=fid,
                    feature_name=fname,
                    operation_type=op,
                    status=ExecutionStatus.success,
                    output_table=out_table,
                    message=f"aggregate saved as '{out_table}'",
                ))
            else:
                handler = _COLUMN_HANDLERS.get(op)
                if handler is None:
                    step_results.append(FeatureStepResult(
                        feature_id=fid,
                        feature_name=fname,
                        operation_type=op,
                        status=ExecutionStatus.failed,
                        error=f"Unsupported operation: {op}",
                    ))
                    continue
                new_df, added_cols = handler(df, feature)
                working[table_name] = new_df
                step_results.append(FeatureStepResult(
                    feature_id=fid,
                    feature_name=fname,
                    operation_type=op,
                    status=ExecutionStatus.success,
                    output_columns=added_cols,
                    message=f"{op} applied",
                ))
        except Exception as exc:  # noqa: BLE001
            step_results.append(FeatureStepResult(
                feature_id=fid,
                feature_name=fname,
                operation_type=op,
                status=ExecutionStatus.failed,
                error=str(exc),
            ))

    return FeatureExecutionResult(tables=working, new_tables=new_tables, step_results=step_results)
