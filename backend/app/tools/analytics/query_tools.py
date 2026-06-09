"""M12C: Deterministic safe analytics tools for the dataset analytics planner.

Each tool:
- validates table and column names against the DuckDB schema
- applies pandas operations (no raw user SQL accepted or executed)
- returns a typed M12A output (TableOutput or VisualOutput)
- stores large table results as CSV artifacts when a storage backend is provided
- never mutates the dataset version or saves views/visuals automatically
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd

from app.schemas.analytics import (
    AllowedAggregation,
    FilterOperator,
    FilterTableSpec,
    GenerateVisualSpec,
    PreviewTableSpec,
    AggregateTableSpec,
    SimpleJoinSpec,
    TableOutput,
    VisualOutput,
)
from app.schemas.common import ChartType
from app.schemas.visualization import ChartSuggestion
from app.tools.charts.chart_executor import ChartExecutor
from app.tools.data.duckdb_service import list_tables
from app.tools.files.storage_service import result_path

# Rows shown inline in the response.
PREVIEW_LIMIT = 100

# Results larger than this are written to storage (if backend provided).
INLINE_LIMIT = 500

_CHART_EXECUTOR = ChartExecutor()

# Map AllowedAggregation → pandas aggfunc string
_AGG_PANDAS: dict[AllowedAggregation, str] = {
    AllowedAggregation.count: "count",
    AllowedAggregation.sum: "sum",
    AllowedAggregation.avg: "mean",
    AllowedAggregation.min: "min",
    AllowedAggregation.max: "max",
    AllowedAggregation.median: "median",
}

_SUPPORTED_CHART_TYPES = {ct.value for ct in ChartType}


class AnalyticsToolError(Exception):
    """Raised when a tool cannot execute due to invalid or unsupported input."""


# ---------------------------------------------------------------------------
# Public tools
# ---------------------------------------------------------------------------

def run_preview_table(
    *,
    db_path: Path,
    spec: PreviewTableSpec,
    dataset_version_id: UUID,
    title: str = "",
    workspace_id: UUID | None = None,
    dataset_id: UUID | None = None,
    storage: Any = None,
) -> TableOutput:
    df = _load_validated_table(db_path, spec.table_name)

    if spec.columns:
        _check_columns(df, spec.columns, spec.table_name)
        df = df[spec.columns]

    df = df.head(spec.limit)
    return _to_table_output(
        df,
        dataset_version_id=dataset_version_id,
        title=title or f"Preview: {spec.table_name}",
        source_spec_json=spec.model_dump(),
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        storage=storage,
    )


def run_aggregate_table(
    *,
    db_path: Path,
    spec: AggregateTableSpec,
    dataset_version_id: UUID,
    title: str = "",
    workspace_id: UUID | None = None,
    dataset_id: UUID | None = None,
    storage: Any = None,
) -> TableOutput:
    df = _load_validated_table(db_path, spec.table_name)
    _check_columns(df, spec.group_by, spec.table_name)
    _check_columns(df, [m.column for m in spec.metrics], spec.table_name)

    if spec.group_by:
        named_aggs = {
            (m.alias or f"{m.aggregation}_{m.column}"): pd.NamedAgg(
                column=m.column,
                aggfunc=_AGG_PANDAS[m.aggregation],
            )
            for m in spec.metrics
        }
        result = df.groupby(spec.group_by).agg(**named_aggs).reset_index()
    else:
        result = pd.DataFrame(
            {
                (m.alias or f"{m.aggregation}_{m.column}"): [
                    df[m.column].agg(_AGG_PANDAS[m.aggregation])
                ]
                for m in spec.metrics
            }
        )

    if spec.sort_by:
        if spec.sort_by not in result.columns:
            raise AnalyticsToolError(
                f"sort_by column '{spec.sort_by}' not in aggregation result."
            )
        result = result.sort_values(spec.sort_by, ascending=not spec.sort_desc)

    result = result.head(spec.limit)
    return _to_table_output(
        result,
        dataset_version_id=dataset_version_id,
        title=title or f"Aggregation: {spec.table_name}",
        source_spec_json=spec.model_dump(),
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        storage=storage,
    )


def run_filter_table(
    *,
    db_path: Path,
    spec: FilterTableSpec,
    dataset_version_id: UUID,
    title: str = "",
    workspace_id: UUID | None = None,
    dataset_id: UUID | None = None,
    storage: Any = None,
) -> TableOutput:
    df = _load_validated_table(db_path, spec.table_name)
    filter_cols = [f.column for f in spec.filters]
    _check_columns(df, filter_cols, spec.table_name)
    if spec.columns:
        _check_columns(df, spec.columns, spec.table_name)

    mask = pd.Series([True] * len(df), index=df.index)
    for f in spec.filters:
        mask &= _apply_filter(df, f)

    result = df[mask].reset_index(drop=True)

    if spec.columns:
        result = result[spec.columns]

    if spec.sort_by:
        if spec.sort_by not in result.columns:
            raise AnalyticsToolError(
                f"sort_by column '{spec.sort_by}' not present in result."
            )
        result = result.sort_values(spec.sort_by, ascending=not spec.sort_desc)

    result = result.head(spec.limit)
    return _to_table_output(
        result,
        dataset_version_id=dataset_version_id,
        title=title or f"Filter: {spec.table_name}",
        source_spec_json=spec.model_dump(),
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        storage=storage,
    )


def run_simple_join(
    *,
    db_path: Path,
    spec: SimpleJoinSpec,
    dataset_version_id: UUID,
    title: str = "",
    workspace_id: UUID | None = None,
    dataset_id: UUID | None = None,
    storage: Any = None,
) -> TableOutput:
    tables_in_db = list_tables(db_path)
    for tname in (spec.left_table, spec.right_table):
        if tname not in tables_in_db:
            raise AnalyticsToolError(f"Table '{tname}' not found in dataset version.")

    left = _load_table_df(db_path, spec.left_table)
    right = _load_table_df(db_path, spec.right_table)

    for col, tbl, df in [
        (spec.join_key_left, spec.left_table, left),
        (spec.join_key_right, spec.right_table, right),
    ]:
        if col not in df.columns:
            raise AnalyticsToolError(
                f"Join key '{col}' not found in table '{tbl}'."
            )

    merged = left.merge(
        right,
        left_on=spec.join_key_left,
        right_on=spec.join_key_right,
        how="inner",
    )

    if spec.output_columns:
        bad = [c for c in spec.output_columns if c not in merged.columns]
        if bad:
            raise AnalyticsToolError(
                f"output_columns not found in join result: {bad}"
            )
        merged = merged[spec.output_columns]

    merged = merged.head(spec.limit)
    return _to_table_output(
        merged,
        dataset_version_id=dataset_version_id,
        title=title or f"Join: {spec.left_table} + {spec.right_table}",
        source_spec_json=spec.model_dump(),
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        storage=storage,
    )


def run_generate_visual(
    *,
    db_path: Path,
    spec: GenerateVisualSpec,
    dataset_version_id: UUID,
    title: str = "",
) -> VisualOutput:
    if spec.chart_type not in _SUPPORTED_CHART_TYPES:
        raise AnalyticsToolError(
            f"Unsupported chart_type '{spec.chart_type}'. "
            f"Allowed: {sorted(_SUPPORTED_CHART_TYPES)}"
        )

    df = _load_validated_table(db_path, spec.table_name)
    _check_columns(df, [spec.x_column], spec.table_name)
    if spec.y_column:
        _check_columns(df, [spec.y_column], spec.table_name)

    suggestion = ChartSuggestion(
        visualization_id=uuid.uuid4(),
        title=title or spec.table_name,
        description="",
        chart_type=ChartType(spec.chart_type),
        input_table=spec.table_name,
        x_column=spec.x_column,
        y_column=spec.y_column,
        aggregation=spec.aggregation.value if spec.aggregation else None,
        user_facing_explanation="",
        requires_human_approval=False,
    )

    results = _CHART_EXECUTOR.execute({spec.table_name: df}, [suggestion])
    result = results[0]

    if result.chart_spec is None:
        raise AnalyticsToolError(
            f"Chart generation failed: {result.error or 'unknown error'}"
        )

    return VisualOutput(
        dataset_version_id=dataset_version_id,
        title=title or f"Chart: {spec.table_name}",
        chart_type=result.chart_spec.chart_type,
        chart_spec_json=result.chart_spec.model_dump(),
        source_spec_json=spec.model_dump(),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_validated_table(db_path: Path, table_name: str) -> pd.DataFrame:
    tables_in_db = list_tables(db_path)
    if table_name not in tables_in_db:
        raise AnalyticsToolError(
            f"Table '{table_name}' not found. Available: {tables_in_db}"
        )
    return _load_table_df(db_path, table_name)


def _load_table_df(db_path: Path, table_name: str) -> pd.DataFrame:
    import duckdb
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(f'SELECT * FROM "{table_name}"').df()  # noqa: S608
    finally:
        con.close()


def _check_columns(df: pd.DataFrame, columns: list[str], table_name: str) -> None:
    bad = [c for c in columns if c not in df.columns]
    if bad:
        raise AnalyticsToolError(
            f"Unknown column(s) in '{table_name}': {bad}. "
            f"Available: {list(df.columns)}"
        )


def _apply_filter(df: pd.DataFrame, f: "FilterSpec") -> pd.Series:  # type: ignore[name-defined]
    col = df[f.column]
    match f.operator:
        case FilterOperator.eq:
            return col == f.value
        case FilterOperator.ne:
            return col != f.value
        case FilterOperator.gt:
            return col > f.value
        case FilterOperator.lt:
            return col < f.value
        case FilterOperator.gte:
            return col >= f.value
        case FilterOperator.lte:
            return col <= f.value
        case FilterOperator.in_:
            return col.isin(f.value if isinstance(f.value, list) else [f.value])
        case FilterOperator.not_in:
            return ~col.isin(f.value if isinstance(f.value, list) else [f.value])
        case FilterOperator.is_null:
            return col.isna()
        case FilterOperator.is_not_null:
            return col.notna()
        case FilterOperator.contains:
            return col.astype(str).str.contains(str(f.value), na=False)
        case _:
            raise AnalyticsToolError(f"Unsupported filter operator: {f.operator}")


def _serialize_val(v: Any) -> Any:
    """Convert numpy/pandas scalars to JSON-safe Python primitives."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def _df_to_rows(df: pd.DataFrame) -> list[list[Any]]:
    return [[_serialize_val(v) for v in row] for row in df.values.tolist()]


def _to_table_output(
    df: pd.DataFrame,
    *,
    dataset_version_id: UUID,
    title: str,
    source_spec_json: dict[str, Any],
    workspace_id: UUID | None,
    dataset_id: UUID | None,
    storage: Any,
) -> TableOutput:
    all_rows = _df_to_rows(df)
    row_count = len(all_rows)
    preview_rows = all_rows[:PREVIEW_LIMIT]

    storage_backend = None
    storage_bucket = None
    storage_path_val = None
    storage_format = None

    if (
        row_count > INLINE_LIMIT
        and storage is not None
        and workspace_id is not None
        and dataset_id is not None
    ):
        artifact_id = uuid.uuid4()
        path = result_path(workspace_id, dataset_id, artifact_id, "csv")
        csv_bytes = df.to_csv(index=False).encode()
        stored = storage.save(path, csv_bytes)
        storage_backend = stored.storage_backend
        storage_bucket = stored.storage_bucket
        storage_path_val = stored.storage_path
        storage_format = "csv"

    return TableOutput(
        dataset_version_id=dataset_version_id,
        title=title,
        columns=list(df.columns),
        preview_rows=preview_rows,
        row_count=row_count,
        source_spec_json=source_spec_json,
        storage_backend=storage_backend,
        storage_bucket=storage_bucket,
        storage_path=storage_path_val,
        storage_format=storage_format,
    )
