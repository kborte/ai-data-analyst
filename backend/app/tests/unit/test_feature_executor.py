"""Unit tests for M6B: deterministic feature executor."""

import math
from uuid import uuid4

import pandas as pd
import pytest

from app.schemas.common import ExecutionStatus, FeatureOperationType
from app.schemas.features import FeatureDefinition
from app.tools.data.feature_executor import execute_features


def _feat(
    op: FeatureOperationType,
    required: list[str],
    params: dict,
    *,
    output_column: str | None = None,
    output_table: str | None = None,
    input_table: str = "orders",
) -> FeatureDefinition:
    return FeatureDefinition(
        feature_id=uuid4(),
        feature_name=op.value,
        display_name=op.value,
        operation_type=op,
        formula_display="",
        input_table=input_table,
        output_column=output_column,
        output_table=output_table,
        required_columns=required,
        parameters=params,
    )


# ---------------------------------------------------------------------------
# 1. ratio creates AOV
# ---------------------------------------------------------------------------


def test_ratio_creates_aov():
    tables = {"orders": pd.DataFrame({"revenue": [100.0, 200.0], "order_count": [2.0, 4.0]})}
    feat = _feat(
        FeatureOperationType.ratio,
        ["revenue", "order_count"],
        {"numerator": "revenue", "denominator": "order_count"},
        output_column="aov",
    )
    result = execute_features(tables, [feat])
    assert "aov" in result.tables["orders"].columns
    assert result.tables["orders"]["aov"].iloc[0] == pytest.approx(50.0)
    assert result.tables["orders"]["aov"].iloc[1] == pytest.approx(50.0)
    assert result.step_results[0].status == ExecutionStatus.success


# ---------------------------------------------------------------------------
# 2. divide by zero is safe
# ---------------------------------------------------------------------------


def test_ratio_divide_by_zero_is_safe():
    tables = {"orders": pd.DataFrame({"revenue": [100.0], "order_count": [0.0]})}
    feat = _feat(
        FeatureOperationType.ratio,
        ["revenue", "order_count"],
        {"numerator": "revenue", "denominator": "order_count"},
        output_column="aov",
    )
    result = execute_features(tables, [feat])
    val = result.tables["orders"]["aov"].iloc[0]
    assert math.isnan(val) or val is pd.NA


# ---------------------------------------------------------------------------
# 3. arithmetic creates net revenue
# ---------------------------------------------------------------------------


def test_arithmetic_creates_net_revenue():
    tables = {"orders": pd.DataFrame({"revenue": [300.0, 500.0], "cost": [100.0, 200.0]})}
    feat = _feat(
        FeatureOperationType.arithmetic,
        ["revenue", "cost"],
        {"operator": "-", "left": "revenue", "right": "cost"},
        output_column="net_revenue",
    )
    result = execute_features(tables, [feat])
    assert "net_revenue" in result.tables["orders"].columns
    assert result.tables["orders"]["net_revenue"].iloc[0] == pytest.approx(200.0)
    assert result.tables["orders"]["net_revenue"].iloc[1] == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# 4. aggregate creates revenue_by_channel table
# ---------------------------------------------------------------------------


def test_aggregate_creates_revenue_by_channel_table():
    tables = {
        "orders": pd.DataFrame({
            "channel": ["email", "social", "email", "social"],
            "revenue": [100.0, 200.0, 50.0, 150.0],
        })
    }
    feat = _feat(
        FeatureOperationType.aggregate,
        ["channel", "revenue"],
        {"value_column": "revenue", "group_by": "channel", "aggregation": "sum"},
        output_table="revenue_by_channel",
    )
    result = execute_features(tables, [feat])
    assert "revenue_by_channel" in result.new_tables
    agg_df = result.new_tables["revenue_by_channel"]
    email_row = agg_df[agg_df["channel"] == "email"]
    assert email_row["revenue_sum"].iloc[0] == pytest.approx(150.0)
    assert result.step_results[0].status == ExecutionStatus.success


# ---------------------------------------------------------------------------
# 5. window creates running revenue
# ---------------------------------------------------------------------------


def test_window_creates_running_revenue():
    tables = {
        "orders": pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "revenue": [100.0, 200.0, 50.0],
        })
    }
    feat = _feat(
        FeatureOperationType.window,
        ["date", "revenue"],
        {"value_column": "revenue", "sort_column": "date"},
        output_column="running_revenue",
    )
    result = execute_features(tables, [feat])
    df = result.tables["orders"].sort_values("date").reset_index(drop=True)
    assert "running_revenue" in df.columns
    assert df["running_revenue"].iloc[0] == pytest.approx(100.0)
    assert df["running_revenue"].iloc[1] == pytest.approx(300.0)
    assert df["running_revenue"].iloc[2] == pytest.approx(350.0)


# ---------------------------------------------------------------------------
# 6. date_extract creates year/month/week/weekday
# ---------------------------------------------------------------------------


def test_date_extract_creates_year_month_week_weekday():
    tables = {"orders": pd.DataFrame({"order_date": ["2024-03-15"]})}
    feat = _feat(
        FeatureOperationType.date_extract,
        ["order_date"],
        {"source_column": "order_date", "parts": ["year", "month", "week", "weekday"]},
    )
    result = execute_features(tables, [feat])
    df = result.tables["orders"]
    assert "order_date_year" in df.columns
    assert "order_date_month" in df.columns
    assert "order_date_week" in df.columns
    assert "order_date_weekday" in df.columns
    assert int(df["order_date_year"].iloc[0]) == 2024
    assert int(df["order_date_month"].iloc[0]) == 3


# ---------------------------------------------------------------------------
# 7. bucketize creates bucket column
# ---------------------------------------------------------------------------


def test_bucketize_creates_bucket_column():
    tables = {"orders": pd.DataFrame({"revenue": [10.0, 75.0, 200.0]})}
    feat = _feat(
        FeatureOperationType.bucketize,
        ["revenue"],
        {"column": "revenue", "bins": [0, 50, 150, 300], "labels": ["low", "medium", "high"]},
        output_column="revenue_bucket",
    )
    result = execute_features(tables, [feat])
    df = result.tables["orders"]
    assert "revenue_bucket" in df.columns
    assert str(df["revenue_bucket"].iloc[0]) == "low"
    assert str(df["revenue_bucket"].iloc[1]) == "medium"
    assert str(df["revenue_bucket"].iloc[2]) == "high"


# ---------------------------------------------------------------------------
# 8. custom_formula returns failed result
# ---------------------------------------------------------------------------


def test_custom_formula_returns_failed_result():
    tables = {"orders": pd.DataFrame({"revenue": [100.0]})}
    feat = _feat(
        FeatureOperationType.custom_formula,
        ["revenue"],
        {"formula": "revenue * 1.1"},
        output_column="adjusted",
    )
    result = execute_features(tables, [feat])
    assert result.step_results[0].status == ExecutionStatus.failed
    assert "not supported" in (result.step_results[0].error or "")


# ---------------------------------------------------------------------------
# 9. input DataFrame is not mutated
# ---------------------------------------------------------------------------


def test_input_dataframe_is_not_mutated():
    original = pd.DataFrame({"revenue": [100.0, 200.0], "order_count": [2.0, 4.0]})
    tables = {"orders": original}
    feat = _feat(
        FeatureOperationType.ratio,
        ["revenue", "order_count"],
        {"numerator": "revenue", "denominator": "order_count"},
        output_column="aov",
    )
    execute_features(tables, [feat])
    assert "aov" not in original.columns
    assert list(original.columns) == ["revenue", "order_count"]
