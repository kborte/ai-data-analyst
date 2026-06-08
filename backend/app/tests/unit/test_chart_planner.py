from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.common import ChartType, DataType
from app.schemas.profile import ColumnProfile, DataProfile
from app.tools.charts.chart_planner import MAX_SUGGESTIONS, ChartPlanner

NOW = datetime.now(tz=UTC)


def _profile(*columns: ColumnProfile, table: str = "sales") -> DataProfile:
    return DataProfile(
        profile_id=uuid4(),
        dataset_version_id=uuid4(),
        table_name=table,
        row_count=1000,
        column_count=len(columns),
        column_profiles=list(columns),
        quality_issues=[],
        created_at=NOW,
    )


def _date(name: str) -> ColumnProfile:
    return ColumnProfile(
        column_name=name,
        data_type=DataType.date,
        total_count=1000,
        null_count=0,
        null_percent=0.0,
        unique_count=365,
        unique_percent=36.5,
        is_likely_date=True,
    )


def _metric(name: str) -> ColumnProfile:
    return ColumnProfile(
        column_name=name,
        data_type=DataType.float_,
        total_count=1000,
        null_count=0,
        null_percent=0.0,
        unique_count=800,
        unique_percent=80.0,
        is_likely_metric=True,
    )


def _cat(name: str, unique_count: int = 10) -> ColumnProfile:
    return ColumnProfile(
        column_name=name,
        data_type=DataType.categorical,
        total_count=1000,
        null_count=0,
        null_percent=0.0,
        unique_count=unique_count,
        unique_percent=unique_count / 10.0,
        is_likely_categorical=True,
    )


planner = ChartPlanner()


def test_date_revenue_suggests_line_chart() -> None:
    profile = _profile(_date("order_date"), _metric("revenue"))
    suggestions = planner.suggest(profile)
    line_suggestions = [s for s in suggestions if s.chart_type == ChartType.line]
    assert len(line_suggestions) >= 1
    s = line_suggestions[0]
    assert s.x_column == "order_date"
    assert s.y_column == "revenue"


def test_category_revenue_suggests_bar_chart() -> None:
    profile = _profile(_cat("region"), _metric("revenue"))
    suggestions = planner.suggest(profile)
    bar_with_metric = [
        s for s in suggestions
        if s.chart_type == ChartType.bar and s.y_column == "revenue"
    ]
    assert len(bar_with_metric) >= 1
    s = bar_with_metric[0]
    assert s.x_column == "region"


def test_category_count_suggests_bar_chart() -> None:
    profile = _profile(_cat("category"))
    suggestions = planner.suggest(profile)
    count_bars = [
        s for s in suggestions
        if s.chart_type == ChartType.bar and s.aggregation == "count"
    ]
    assert len(count_bars) >= 1
    assert count_bars[0].x_column == "category"


def test_two_numeric_suggests_scatter() -> None:
    profile = _profile(_metric("revenue"), _metric("cost"))
    suggestions = planner.suggest(profile)
    scatters = [s for s in suggestions if s.chart_type == ChartType.scatter]
    assert len(scatters) >= 1
    cols = {scatters[0].x_column, scatters[0].y_column}
    assert cols == {"revenue", "cost"}


def test_pie_only_for_low_cardinality() -> None:
    # high cardinality — no pie
    profile_high = _profile(_cat("region", unique_count=20))
    high_pies = [s for s in planner.suggest(profile_high) if s.chart_type == ChartType.pie]
    assert high_pies == []

    # low cardinality — pie expected
    profile_low = _profile(_cat("status", unique_count=3))
    low_pies = [s for s in planner.suggest(profile_low) if s.chart_type == ChartType.pie]
    assert len(low_pies) >= 1
    assert low_pies[0].x_column == "status"


def test_max_suggestions_respected() -> None:
    # many columns to generate far more than 8 candidates
    columns = (
        [_date(f"date_{i}") for i in range(3)]
        + [_metric(f"metric_{i}") for i in range(4)]
        + [_cat(f"cat_{i}", unique_count=2) for i in range(4)]
    )
    profile = _profile(*columns)
    suggestions = planner.suggest(profile)
    assert len(suggestions) <= MAX_SUGGESTIONS


def test_all_suggestions_require_approval() -> None:
    profile = _profile(
        _date("order_date"),
        _metric("revenue"),
        _cat("region", unique_count=4),
    )
    suggestions = planner.suggest(profile)
    assert len(suggestions) > 0
    assert all(s.requires_human_approval for s in suggestions)
