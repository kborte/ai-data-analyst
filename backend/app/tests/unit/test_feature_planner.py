"""Unit tests for M6A: feature schemas and planner."""

from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.common import DataType, FeatureOperationType
from app.schemas.features import FeatureDefinition
from app.schemas.profile import ColumnProfile, DataProfile
from app.tools.data.feature_planner import generate_feature_suggestions


def _profile(columns: list[ColumnProfile]) -> DataProfile:
    return DataProfile(
        profile_id=uuid4(),
        dataset_version_id=uuid4(),
        table_name="orders",
        row_count=100,
        column_count=len(columns),
        column_profiles=columns,
        created_at=datetime.now(tz=UTC),
    )


def _col(
    name: str,
    data_type: DataType = DataType.string,
    *,
    is_likely_date: bool = False,
    is_likely_categorical: bool = False,
    is_likely_metric: bool = False,
    is_likely_id: bool = False,
) -> ColumnProfile:
    return ColumnProfile(
        column_name=name,
        data_type=data_type,
        total_count=100,
        null_count=0,
        null_percent=0.0,
        unique_count=10,
        unique_percent=10.0,
        is_likely_date=is_likely_date,
        is_likely_categorical=is_likely_categorical,
        is_likely_metric=is_likely_metric,
        is_likely_id=is_likely_id,
    )


# ---------------------------------------------------------------------------
# 1. schemas validate ratio/window/aggregate features
# ---------------------------------------------------------------------------


def test_schema_validates_ratio():
    f = FeatureDefinition(
        feature_id=uuid4(),
        feature_name="aov",
        display_name="AOV",
        operation_type=FeatureOperationType.ratio,
        formula_display="revenue / order_id",
        input_table="orders",
        output_column="aov",
        required_columns=["revenue", "order_id"],
        parameters={"numerator": "revenue", "denominator": "order_id"},
    )
    assert f.operation_type == FeatureOperationType.ratio
    assert f.requires_human_approval is True


def test_schema_validates_window():
    f = FeatureDefinition(
        feature_id=uuid4(),
        feature_name="running_revenue",
        display_name="Running Revenue",
        operation_type=FeatureOperationType.window,
        formula_display="cumsum(revenue) order by date",
        input_table="orders",
        output_column="running_revenue",
        required_columns=["date", "revenue"],
    )
    assert f.operation_type == FeatureOperationType.window


def test_schema_validates_aggregate():
    f = FeatureDefinition(
        feature_id=uuid4(),
        feature_name="revenue_by_channel",
        display_name="Revenue by channel",
        operation_type=FeatureOperationType.aggregate,
        formula_display="sum(revenue) group by channel",
        input_table="orders",
        output_table="revenue_by_channel",
        required_columns=["channel", "revenue"],
    )
    assert f.output_table == "revenue_by_channel"
    assert f.output_column is None


# ---------------------------------------------------------------------------
# 2. custom_formula validates in schema but unsupported for execution
# ---------------------------------------------------------------------------


def test_custom_formula_validates_in_schema():
    f = FeatureDefinition(
        feature_id=uuid4(),
        feature_name="custom",
        display_name="Custom formula",
        operation_type=FeatureOperationType.custom_formula,
        formula_display="revenue * 1.1",
        input_table="orders",
        output_column="adjusted_revenue",
        required_columns=["revenue"],
        parameters={"formula": "revenue * 1.1"},
    )
    assert f.operation_type == FeatureOperationType.custom_formula


# ---------------------------------------------------------------------------
# 3. revenue + order_id suggests AOV
# ---------------------------------------------------------------------------


def test_suggests_aov_for_revenue_and_order():
    profile = _profile([
        _col("revenue", DataType.float_),
        _col("order_id", is_likely_id=True),
    ])
    suggestions = generate_feature_suggestions(profile)
    names = [s.feature_name for s in suggestions]
    assert "aov" in names
    aov = next(s for s in suggestions if s.feature_name == "aov")
    assert aov.operation_type == FeatureOperationType.ratio
    assert "revenue" in aov.required_columns
    assert "order_id" in aov.required_columns


# ---------------------------------------------------------------------------
# 4. date + revenue suggests running revenue
# ---------------------------------------------------------------------------


def test_suggests_running_revenue_for_date_and_revenue():
    profile = _profile([
        _col("date", DataType.date, is_likely_date=True),
        _col("revenue", DataType.float_),
    ])
    suggestions = generate_feature_suggestions(profile)
    names = [s.feature_name for s in suggestions]
    assert "running_revenue" in names
    rr = next(s for s in suggestions if s.feature_name == "running_revenue")
    assert rr.operation_type == FeatureOperationType.window


# ---------------------------------------------------------------------------
# 5. date + revenue + channel suggests grouped running revenue
# ---------------------------------------------------------------------------


def test_suggests_grouped_running_revenue_for_date_revenue_channel():
    profile = _profile([
        _col("date", DataType.date, is_likely_date=True),
        _col("revenue", DataType.float_),
        _col("channel", is_likely_categorical=True),
    ])
    suggestions = generate_feature_suggestions(profile)
    names = [s.feature_name for s in suggestions]
    assert any("running_revenue_by" in n for n in names)
    grouped = next(s for s in suggestions if "running_revenue_by" in s.feature_name)
    assert grouped.operation_type == FeatureOperationType.window
    assert "channel" in grouped.required_columns


# ---------------------------------------------------------------------------
# 6. all suggestions require approval
# ---------------------------------------------------------------------------


def test_all_suggestions_require_approval():
    profile = _profile([
        _col("date", DataType.date, is_likely_date=True),
        _col("revenue", DataType.float_),
        _col("order_id", is_likely_id=True),
        _col("customer_id", is_likely_id=True),
        _col("channel", is_likely_categorical=True),
        _col("segment", is_likely_categorical=True),
    ])
    suggestions = generate_feature_suggestions(profile)
    assert len(suggestions) > 0
    assert all(s.requires_human_approval for s in suggestions)


# ---------------------------------------------------------------------------
# 7. max suggestions respected
# ---------------------------------------------------------------------------


def test_max_suggestions_not_exceeded():
    profile = _profile([
        _col("date1", DataType.date, is_likely_date=True),
        _col("date2", DataType.date, is_likely_date=True),
        _col("date3", DataType.date, is_likely_date=True),
        _col("date4", DataType.date, is_likely_date=True),
        _col("date5", DataType.date, is_likely_date=True),
        _col("revenue", DataType.float_),
        _col("order_id"),
        _col("customer_id"),
        _col("channel", is_likely_categorical=True),
        _col("segment", is_likely_categorical=True),
    ])
    suggestions = generate_feature_suggestions(profile)
    assert len(suggestions) <= 8
