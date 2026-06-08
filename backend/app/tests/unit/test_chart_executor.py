from uuid import uuid4

import pandas as pd

from app.schemas.common import ChartType, ExecutionStatus
from app.schemas.visualization import ChartSuggestion
from app.tools.charts.chart_executor import ChartExecutor

executor = ChartExecutor()


def _suggestion(**kwargs) -> ChartSuggestion:
    defaults = dict(
        visualization_id=uuid4(),
        title="Test Chart",
        description="A test chart.",
        chart_type=ChartType.line,
        input_table="sales",
        x_column="date",
        y_column="revenue",
        aggregation="sum",
        user_facing_explanation="Test.",
    )
    defaults.update(kwargs)
    return ChartSuggestion(**defaults)


def test_line_chart_spec_generated() -> None:
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=6, freq="ME"),
        "revenue": [100, 120, 90, 150, 130, 110],
    })
    result = executor.execute({"sales": df}, [_suggestion()])[0]

    assert result.status == ExecutionStatus.success
    assert result.chart_spec is not None
    assert result.chart_spec.chart_type == "line"
    assert result.chart_spec.x_key == "date"
    assert result.chart_spec.series[0].data_key == "revenue"
    assert len(result.chart_spec.data) == 6
    assert "date" in result.chart_spec.data[0]
    assert "revenue" in result.chart_spec.data[0]


def test_bar_chart_spec_generated() -> None:
    df = pd.DataFrame({
        "region": ["North", "South", "East", "North", "South"],
        "revenue": [200, 150, 180, 220, 130],
    })
    s = _suggestion(
        chart_type=ChartType.bar,
        x_column="region",
        y_column="revenue",
        aggregation="sum",
        sort="desc",
    )
    result = executor.execute({"sales": df}, [s])[0]

    assert result.status == ExecutionStatus.success
    spec = result.chart_spec
    assert spec.chart_type == "bar"
    assert spec.x_key == "region"
    assert spec.series[0].data_key == "revenue"
    # North total = 420, South = 280, East = 180 → desc order
    assert spec.data[0]["region"] == "North"
    assert spec.data[0]["revenue"] == 420


def test_scatter_chart_spec_generated() -> None:
    df = pd.DataFrame({
        "revenue": [100, 200, 150, 300, 250],
        "cost":    [80,  160, 110, 240, 190],
    })
    s = _suggestion(
        chart_type=ChartType.scatter,
        x_column="revenue",
        y_column="cost",
        aggregation=None,
    )
    result = executor.execute({"sales": df}, [s])[0]

    assert result.status == ExecutionStatus.success
    spec = result.chart_spec
    assert spec.chart_type == "scatter"
    assert spec.x_key == "revenue"
    assert spec.series[0].data_key == "cost"
    assert len(spec.data) == 5
    assert "revenue" in spec.data[0] and "cost" in spec.data[0]


def test_pie_chart_spec_generated() -> None:
    df = pd.DataFrame({
        "status": ["active", "inactive", "active", "pending", "active", "inactive"],
    })
    s = _suggestion(
        chart_type=ChartType.pie,
        x_column="status",
        y_column=None,
        aggregation="count",
    )
    result = executor.execute({"sales": df}, [s])[0]

    assert result.status == ExecutionStatus.success
    spec = result.chart_spec
    assert spec.chart_type == "pie"
    assert spec.x_key == "status"
    assert spec.series[0].data_key == "count"
    counts = {row["status"]: row["count"] for row in spec.data}
    assert counts["active"] == 3
    assert counts["inactive"] == 2
    assert counts["pending"] == 1


def test_missing_column_returns_failed_result() -> None:
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=3, freq="ME")})
    s = _suggestion(y_column="revenue")  # revenue not in df
    result = executor.execute({"sales": df}, [s])[0]

    assert result.status == ExecutionStatus.failed
    assert result.chart_spec is None
    assert "revenue" in (result.error or "")


def test_input_dataframe_not_mutated() -> None:
    df = pd.DataFrame({
        "region": ["A", "B", "A", "B"],
        "revenue": [10, 20, 30, 40],
    })
    original_cols = list(df.columns)
    original_shape = df.shape
    original_values = df.copy()

    s = _suggestion(
        chart_type=ChartType.bar,
        x_column="region",
        y_column="revenue",
        aggregation="sum",
    )
    executor.execute({"sales": df}, [s])

    assert list(df.columns) == original_cols
    assert df.shape == original_shape
    pd.testing.assert_frame_equal(df, original_values)
