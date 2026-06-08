"""
Deterministic DataFrame profiler. No LLM calls. No data mutation.
"""

from typing import Any

import pandas as pd

from app.schemas.common import DataType, ImpactLevel, IssueType
from app.schemas.profile import ColumnProfile, DataQualityIssue, DateSummary, NumericSummary

_METRIC_KEYWORDS = {"revenue", "sales", "amount", "price", "cost", "spend", "orders", "quantity", "users", "count", "profit", "margin"}
_CATEGORY_KEYWORDS = {"country", "region", "channel", "campaign", "product", "status", "segment", "category", "type", "tier"}
_DATE_KEYWORDS = {"date", "time", "created_at", "updated_at", "timestamp", "created", "updated", "at"}

_CATEGORICAL_MAX_UNIQUE = 15
_CATEGORICAL_MAX_UNIQUE_PCT = 0.05
_HIGH_CARDINALITY_THRESHOLD = 50
_NUMERIC_TEXT_THRESHOLD = 0.70
_DATE_TEXT_THRESHOLD = 0.70
_ID_UNIQUE_PCT_THRESHOLD = 0.90


def _name_contains(col: str, keywords: set[str]) -> bool:
    low = col.lower()
    return any(kw in low for kw in keywords)


def _infer_type(series: pd.Series) -> tuple[DataType, bool, bool]:
    """Return (inferred_type, is_numeric_as_text, is_date_as_text)."""
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return DataType.boolean, False, False
    if pd.api.types.is_integer_dtype(dtype):
        return DataType.integer, False, False
    if pd.api.types.is_float_dtype(dtype):
        return DataType.float_, False, False
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return DataType.datetime, False, False

    non_null = series.dropna()
    n = len(non_null)
    if n == 0:
        return DataType.unknown, False, False

    # Check numeric-parseable
    num_frac = pd.to_numeric(non_null, errors="coerce").notna().sum() / n
    if num_frac >= _NUMERIC_TEXT_THRESHOLD:
        return DataType.float_, True, False

    # Check date-parseable (skip columns where numeric fraction was also high)
    try:
        date_frac = pd.to_datetime(non_null, errors="coerce", format="mixed").notna().sum() / n
    except Exception:
        date_frac = 0.0
    if date_frac >= _DATE_TEXT_THRESHOLD:
        return DataType.date, False, True

    unique_count = series.nunique()
    unique_pct = unique_count / max(len(series), 1)
    if unique_count <= _CATEGORICAL_MAX_UNIQUE or unique_pct <= _CATEGORICAL_MAX_UNIQUE_PCT:
        return DataType.categorical, False, False

    return DataType.string, False, False


def _numeric_summary(series: pd.Series) -> NumericSummary:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return NumericSummary()
    return NumericSummary(
        min=float(s.min()),
        max=float(s.max()),
        mean=float(s.mean()),
        median=float(s.median()),
        std=float(s.std()) if len(s) > 1 else None,
    )


def _date_summary(series: pd.Series) -> DateSummary:
    parsed = pd.to_datetime(series, errors="coerce", format="mixed").dropna()
    if parsed.empty:
        return DateSummary()
    return DateSummary(
        min_date=str(parsed.min().date()),
        max_date=str(parsed.max().date()),
        n_unique=int(parsed.nunique()),
    )


def _top_values(series: pd.Series, n: int = 5) -> list[Any]:
    try:
        return [v for v in series.dropna().value_counts().head(n).index.tolist()]
    except Exception:
        return []


def _mixed_type_fracs(series: pd.Series) -> tuple[float, float]:
    """Return (numeric_frac, date_frac) for object columns."""
    non_null = series.dropna().astype(str)
    n = len(non_null)
    if n == 0:
        return 0.0, 0.0
    num_mask = pd.to_numeric(non_null, errors="coerce").notna()
    num_frac = num_mask.sum() / n
    # Exclude purely numeric values from date fraction
    date_frac_adjusted = (pd.to_datetime(non_null[~num_mask], errors="coerce", format="mixed").notna().sum() / n) if (~num_mask).sum() > 0 else 0.0
    return num_frac, date_frac_adjusted


def profile_dataframe(
    df: pd.DataFrame,
    table_name: str,
) -> tuple[list[ColumnProfile], list[DataQualityIssue]]:
    """Profile a single DataFrame. Returns (column_profiles, quality_issues)."""
    issues: list[DataQualityIssue] = []
    column_profiles: list[ColumnProfile] = []
    total_rows = len(df)

    # Duplicate-row issue (table-level)
    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        dup_pct = round(dup_count / max(total_rows, 1) * 100, 2)
        issues.append(
            DataQualityIssue(
                issue_type=IssueType.duplicate_rows,
                table_name=table_name,
                description=f"{dup_count} duplicate rows ({dup_pct}%)",
                affected_rows_count=dup_count,
                affected_rows_percent=dup_pct,
                impact_level=ImpactLevel.high if dup_pct > 10 else ImpactLevel.medium,
            )
        )

    for col in df.columns:
        series = df[col]
        inferred_type, is_num_text, is_date_text = _infer_type(series)

        null_count = int(series.isna().sum())
        null_pct = round(null_count / max(total_rows, 1) * 100, 2)
        unique_count = int(series.nunique())
        unique_pct = round(unique_count / max(total_rows, 1) * 100, 2)

        # Heuristics
        is_metric = inferred_type in (DataType.integer, DataType.float_) and _name_contains(col, _METRIC_KEYWORDS)
        is_date_col = inferred_type in (DataType.date, DataType.datetime) or _name_contains(col, _DATE_KEYWORDS)
        is_categorical = inferred_type == DataType.categorical or _name_contains(col, _CATEGORY_KEYWORDS)
        is_id = ("id" in col.lower()) or (unique_pct >= _ID_UNIQUE_PCT_THRESHOLD * 100 and not is_metric)

        # Numeric / date summaries
        num_summary: NumericSummary | None = None
        date_sum: DateSummary | None = None
        if inferred_type in (DataType.integer, DataType.float_):
            num_summary = _numeric_summary(series)
        if inferred_type in (DataType.date, DataType.datetime) or is_date_col:
            date_sum = _date_summary(series)

        column_profiles.append(
            ColumnProfile(
                column_name=col,
                data_type=inferred_type,
                total_count=total_rows,
                null_count=null_count,
                null_percent=null_pct,
                unique_count=unique_count,
                unique_percent=unique_pct,
                top_values=_top_values(series),
                numeric_summary=num_summary,
                date_summary=date_sum,
                is_likely_id=is_id,
                is_likely_metric=is_metric,
                is_likely_categorical=is_categorical,
                is_likely_date=is_date_col,
            )
        )

        sample = [str(v) for v in series.dropna().head(3).tolist()]

        # Missing values issue
        if null_count > 0:
            if is_metric or is_date_col or is_id:
                impact = ImpactLevel.high
            elif is_categorical:
                impact = ImpactLevel.medium
            else:
                impact = ImpactLevel.low
            issues.append(
                DataQualityIssue(
                    issue_type=IssueType.missing_values,
                    table_name=table_name,
                    column_name=col,
                    description=f"Column '{col}' has {null_count} missing values ({null_pct}%)",
                    affected_rows_count=null_count,
                    affected_rows_percent=null_pct,
                    impact_level=impact,
                    sample_values=sample,
                )
            )

        # Numeric stored as text
        if is_num_text:
            issues.append(
                DataQualityIssue(
                    issue_type=IssueType.numeric_stored_as_text,
                    table_name=table_name,
                    column_name=col,
                    description=f"Column '{col}' appears to be numeric but is stored as text",
                    affected_rows_count=total_rows - null_count,
                    affected_rows_percent=round((total_rows - null_count) / max(total_rows, 1) * 100, 2),
                    impact_level=ImpactLevel.medium,
                    sample_values=sample,
                )
            )

        # Date stored as text
        if is_date_text:
            issues.append(
                DataQualityIssue(
                    issue_type=IssueType.date_stored_as_text,
                    table_name=table_name,
                    column_name=col,
                    description=f"Column '{col}' appears to be a date but is stored as text",
                    affected_rows_count=total_rows - null_count,
                    affected_rows_percent=round((total_rows - null_count) / max(total_rows, 1) * 100, 2),
                    impact_level=ImpactLevel.medium,
                    sample_values=sample,
                )
            )

        # High-cardinality category
        if is_categorical and unique_count > _HIGH_CARDINALITY_THRESHOLD:
            issues.append(
                DataQualityIssue(
                    issue_type=IssueType.high_cardinality_category,
                    table_name=table_name,
                    column_name=col,
                    description=f"Column '{col}' is categorical but has {unique_count} unique values",
                    affected_rows_count=total_rows,
                    affected_rows_percent=100.0,
                    impact_level=ImpactLevel.low,
                )
            )

        # Mixed types (object columns only)
        if series.dtype == object and not is_num_text and not is_date_text:
            num_frac, date_frac = _mixed_type_fracs(series)
            if num_frac > 0.1 and date_frac > 0.1:
                issues.append(
                    DataQualityIssue(
                        issue_type=IssueType.mixed_types,
                        table_name=table_name,
                        column_name=col,
                        description=f"Column '{col}' contains a mix of numeric and date-like values",
                        affected_rows_count=total_rows,
                        affected_rows_percent=100.0,
                        impact_level=ImpactLevel.medium,
                        sample_values=sample,
                    )
                )

    return column_profiles, issues
