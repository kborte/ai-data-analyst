"""
Deterministic chart spec executor.

Takes a dict of table_name -> DataFrame and a list of approved ChartSuggestions.
Returns a ChartExecutionResult per suggestion — never mutates input DataFrames.

Supported chart types: bar, line, pie, scatter.
Supported aggregations: sum, mean, count.
"""

import json

import pandas as pd

from app.schemas.common import ChartType, ExecutionStatus
from app.schemas.visualization import ChartExecutionResult, ChartSpec, ChartSuggestion, SeriesSpec

_MAX_DATA_POINTS = 500


class ChartExecutor:
    def execute(
        self,
        tables: dict[str, pd.DataFrame],
        suggestions: list[ChartSuggestion],
    ) -> list[ChartExecutionResult]:
        return [self._execute_one(tables, s) for s in suggestions]

    def _execute_one(
        self,
        tables: dict[str, pd.DataFrame],
        s: ChartSuggestion,
    ) -> ChartExecutionResult:
        if s.input_table not in tables:
            return self._fail(s, f"Table '{s.input_table}' not found.")

        df = tables[s.input_table].copy()

        missing = _missing_columns(df, s)
        if missing:
            return self._fail(s, f"Missing columns: {missing}")

        try:
            match s.chart_type:
                case ChartType.line:
                    spec = self._line(df, s)
                case ChartType.bar:
                    spec = self._bar(df, s)
                case ChartType.pie:
                    spec = self._pie(df, s)
                case ChartType.scatter:
                    spec = self._scatter(df, s)
                case _:
                    return self._fail(s, f"Unsupported chart type: {s.chart_type}")
        except Exception as exc:  # noqa: BLE001
            return self._fail(s, str(exc))

        return ChartExecutionResult(
            visualization_id=s.visualization_id,
            status=ExecutionStatus.success,
            chart_spec=spec,
        )

    # --- per-type builders ---

    def _line(self, df: pd.DataFrame, s: ChartSuggestion) -> ChartSpec:
        if not s.y_column:
            raise ValueError("Line chart requires y_column.")
        df = _aggregate(df, s.x_column, s.y_column, s.aggregation)
        df = _sort(df, s.x_column, s.sort or "asc")
        df = df.head(_MAX_DATA_POINTS)
        return ChartSpec(
            visualization_id=str(s.visualization_id),
            title=s.title,
            chart_type="line",
            x_key=s.x_column,
            series=[SeriesSpec(data_key=s.y_column, label=_label(s.y_column))],
            data=_to_records(df[[s.x_column, s.y_column]]),
            description=s.description,
        )

    def _bar(self, df: pd.DataFrame, s: ChartSuggestion) -> ChartSpec:
        if s.aggregation == "count" or s.y_column is None:
            agg_df = df.groupby(s.x_column).size().reset_index(name="count")
            y_key = "count"
        else:
            agg_df = _aggregate(df, s.x_column, s.y_column, s.aggregation)
            y_key = s.y_column
        agg_df = _sort(agg_df, y_key, s.sort or "desc")
        limit = s.limit or _MAX_DATA_POINTS
        agg_df = agg_df.head(limit)
        return ChartSpec(
            visualization_id=str(s.visualization_id),
            title=s.title,
            chart_type="bar",
            x_key=s.x_column,
            series=[SeriesSpec(data_key=y_key, label=_label(y_key))],
            data=_to_records(agg_df[[s.x_column, y_key]]),
            description=s.description,
        )

    def _pie(self, df: pd.DataFrame, s: ChartSuggestion) -> ChartSpec:
        if s.aggregation == "sum" and s.y_column:
            agg_df = _aggregate(df, s.x_column, s.y_column, "sum")
            y_key = s.y_column
        else:
            agg_df = df.groupby(s.x_column).size().reset_index(name="count")
            y_key = "count"
        agg_df = agg_df.head(_MAX_DATA_POINTS)
        return ChartSpec(
            visualization_id=str(s.visualization_id),
            title=s.title,
            chart_type="pie",
            x_key=s.x_column,
            series=[SeriesSpec(data_key=y_key, label=_label(y_key))],
            data=_to_records(agg_df[[s.x_column, y_key]]),
            description=s.description,
        )

    def _scatter(self, df: pd.DataFrame, s: ChartSuggestion) -> ChartSpec:
        if not s.y_column:
            raise ValueError("Scatter chart requires y_column.")
        df = df[[s.x_column, s.y_column]].dropna()
        df = df.head(_MAX_DATA_POINTS)
        return ChartSpec(
            visualization_id=str(s.visualization_id),
            title=s.title,
            chart_type="scatter",
            x_key=s.x_column,
            series=[SeriesSpec(data_key=s.y_column, label=_label(s.y_column))],
            data=_to_records(df),
            description=s.description,
        )

    @staticmethod
    def _fail(s: ChartSuggestion, error: str) -> ChartExecutionResult:
        return ChartExecutionResult(
            visualization_id=s.visualization_id,
            status=ExecutionStatus.failed,
            error=error,
        )


# --- helpers ---


def _missing_columns(df: pd.DataFrame, s: ChartSuggestion) -> list[str]:
    needed = [s.x_column]
    if s.y_column:
        needed.append(s.y_column)
    needed.extend(s.y_columns)
    return [c for c in needed if c not in df.columns]


def _aggregate(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    aggregation: str | None,
) -> pd.DataFrame:
    if aggregation == "sum":
        return df.groupby(x_col, as_index=False)[y_col].sum()
    if aggregation == "mean":
        return df.groupby(x_col, as_index=False)[y_col].mean()
    # no aggregation — keep rows as-is
    return df[[x_col, y_col]].copy()


def _sort(df: pd.DataFrame, col: str, direction: str) -> pd.DataFrame:
    if col not in df.columns:
        return df
    ascending = direction != "desc"
    return df.sort_values(col, ascending=ascending).reset_index(drop=True)


def _to_records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _label(col: str) -> str:
    return col.replace("_", " ").title()
