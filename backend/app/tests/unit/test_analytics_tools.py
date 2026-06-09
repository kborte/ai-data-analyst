"""Tests for M12C deterministic safe analytics tools."""

from __future__ import annotations

import uuid
from pathlib import Path

import pandas as pd
import pytest

from app.schemas.analytics import (
    AggregateTableSpec,
    AllowedAggregation,
    FilterOperator,
    FilterSpec,
    FilterTableSpec,
    GenerateVisualSpec,
    MetricSpec,
    PreviewTableSpec,
    SimpleJoinSpec,
)
from app.tools.analytics.query_tools import (
    INLINE_LIMIT,
    PREVIEW_LIMIT,
    AnalyticsToolError,
    run_aggregate_table,
    run_filter_table,
    run_generate_visual,
    run_preview_table,
    run_simple_join,
)
from app.tools.data.duckdb_service import create_version_duckdb
from app.tools.files.storage_service import LocalStorageBackend

VERSION_ID = uuid.uuid4()
DATASET_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sales_db(tmp_path: Path) -> Path:
    db = tmp_path / "v1.duckdb"
    df = pd.DataFrame({
        "month": ["Jan", "Feb", "Mar", "Apr", "May"],
        "channel": ["online", "store", "online", "store", "online"],
        "revenue": [100.0, 200.0, 150.0, 300.0, 250.0],
        "units": [10, 20, 15, 30, 25],
    })
    create_version_duckdb({"sales": df}, db)
    return db


@pytest.fixture()
def two_table_db(tmp_path: Path) -> Path:
    db = tmp_path / "v2.duckdb"
    orders = pd.DataFrame({
        "order_id": [1, 2, 3],
        "customer_id": [10, 20, 10],
        "total": [50.0, 80.0, 120.0],
    })
    customers = pd.DataFrame({
        "id": [10, 20],
        "name": ["Alice", "Bob"],
    })
    create_version_duckdb({"orders": orders, "customers": customers}, db)
    return db


@pytest.fixture()
def local_storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(str(tmp_path / "storage"))


# ---------------------------------------------------------------------------
# run_preview_table
# ---------------------------------------------------------------------------

class TestPreviewTable:
    def test_returns_table_output(self, sales_db):
        spec = PreviewTableSpec(table_name="sales")
        out = run_preview_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        assert out.output_type == "table"
        assert out.dataset_version_id == VERSION_ID
        assert "month" in out.columns
        assert out.row_count == 5

    def test_can_save_as_view_always_true(self, sales_db):
        spec = PreviewTableSpec(table_name="sales")
        out = run_preview_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        assert out.can_save_as_view is True

    def test_column_selection(self, sales_db):
        spec = PreviewTableSpec(table_name="sales", columns=["month", "revenue"])
        out = run_preview_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        assert out.columns == ["month", "revenue"]

    def test_limit_respected(self, sales_db):
        spec = PreviewTableSpec(table_name="sales", limit=3)
        out = run_preview_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        assert out.row_count == 3

    def test_invalid_table_raises(self, sales_db):
        spec = PreviewTableSpec(table_name="nonexistent")
        with pytest.raises(AnalyticsToolError, match="nonexistent"):
            run_preview_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)

    def test_invalid_column_raises(self, sales_db):
        spec = PreviewTableSpec(table_name="sales", columns=["month", "bad_col"])
        with pytest.raises(AnalyticsToolError, match="bad_col"):
            run_preview_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)

    def test_preview_rows_capped_at_preview_limit(self, tmp_path):
        db = tmp_path / "big.duckdb"
        df = pd.DataFrame({"x": range(PREVIEW_LIMIT + 50)})
        create_version_duckdb({"t": df}, db)
        spec = PreviewTableSpec(table_name="t", limit=PREVIEW_LIMIT + 50)
        out = run_preview_table(db_path=db, spec=spec, dataset_version_id=VERSION_ID)
        assert len(out.preview_rows) <= PREVIEW_LIMIT
        assert out.row_count == PREVIEW_LIMIT + 50


# ---------------------------------------------------------------------------
# run_aggregate_table
# ---------------------------------------------------------------------------

class TestAggregateTable:
    def test_sum_by_channel(self, sales_db):
        spec = AggregateTableSpec(
            table_name="sales",
            group_by=["channel"],
            metrics=[MetricSpec(column="revenue", aggregation=AllowedAggregation.sum)],
        )
        out = run_aggregate_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        assert "channel" in out.columns
        assert "sum_revenue" in out.columns
        assert out.row_count == 2  # online, store

    def test_metric_alias_used(self, sales_db):
        spec = AggregateTableSpec(
            table_name="sales",
            group_by=["channel"],
            metrics=[MetricSpec(column="revenue", aggregation=AllowedAggregation.sum, alias="total_rev")],
        )
        out = run_aggregate_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        assert "total_rev" in out.columns

    def test_sort_desc(self, sales_db):
        spec = AggregateTableSpec(
            table_name="sales",
            group_by=["channel"],
            metrics=[MetricSpec(column="revenue", aggregation=AllowedAggregation.sum, alias="rev")],
            sort_by="rev",
            sort_desc=True,
        )
        out = run_aggregate_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        revs = [row[out.columns.index("rev")] for row in out.preview_rows]
        assert revs == sorted(revs, reverse=True)

    def test_invalid_table_raises(self, sales_db):
        spec = AggregateTableSpec(
            table_name="bad",
            group_by=["x"],
            metrics=[MetricSpec(column="y", aggregation=AllowedAggregation.sum)],
        )
        with pytest.raises(AnalyticsToolError):
            run_aggregate_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)

    def test_invalid_metric_column_raises(self, sales_db):
        spec = AggregateTableSpec(
            table_name="sales",
            group_by=["channel"],
            metrics=[MetricSpec(column="nonexistent", aggregation=AllowedAggregation.sum)],
        )
        with pytest.raises(AnalyticsToolError, match="nonexistent"):
            run_aggregate_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)

    def test_count_aggregation(self, sales_db):
        spec = AggregateTableSpec(
            table_name="sales",
            group_by=["channel"],
            metrics=[MetricSpec(column="units", aggregation=AllowedAggregation.count, alias="n")],
        )
        out = run_aggregate_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        assert "n" in out.columns


# ---------------------------------------------------------------------------
# run_filter_table
# ---------------------------------------------------------------------------

class TestFilterTable:
    def test_eq_filter(self, sales_db):
        spec = FilterTableSpec(
            table_name="sales",
            filters=[FilterSpec(column="channel", operator=FilterOperator.eq, value="online")],
        )
        out = run_filter_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        channels = [row[out.columns.index("channel")] for row in out.preview_rows]
        assert all(c == "online" for c in channels)

    def test_gt_filter(self, sales_db):
        spec = FilterTableSpec(
            table_name="sales",
            filters=[FilterSpec(column="revenue", operator=FilterOperator.gt, value=150.0)],
        )
        out = run_filter_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        revs = [row[out.columns.index("revenue")] for row in out.preview_rows]
        assert all(r > 150 for r in revs)

    def test_in_filter(self, sales_db):
        spec = FilterTableSpec(
            table_name="sales",
            filters=[FilterSpec(column="month", operator=FilterOperator.in_, value=["Jan", "Feb"])],
        )
        out = run_filter_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        assert out.row_count == 2

    def test_is_null_filter(self, tmp_path):
        db = tmp_path / "nulls.duckdb"
        df = pd.DataFrame({"x": [1.0, None, 3.0], "y": ["a", "b", "c"]})
        create_version_duckdb({"t": df}, db)
        spec = FilterTableSpec(
            table_name="t",
            filters=[FilterSpec(column="x", operator=FilterOperator.is_null)],
        )
        out = run_filter_table(db_path=db, spec=spec, dataset_version_id=VERSION_ID)
        assert out.row_count == 1

    def test_column_selection(self, sales_db):
        spec = FilterTableSpec(
            table_name="sales",
            filters=[FilterSpec(column="channel", operator=FilterOperator.eq, value="online")],
            columns=["month", "revenue"],
        )
        out = run_filter_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        assert out.columns == ["month", "revenue"]

    def test_invalid_filter_column_raises(self, sales_db):
        spec = FilterTableSpec(
            table_name="sales",
            filters=[FilterSpec(column="bad", operator=FilterOperator.eq, value="x")],
        )
        with pytest.raises(AnalyticsToolError, match="bad"):
            run_filter_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)

    def test_no_mutation(self, sales_db):
        spec = FilterTableSpec(
            table_name="sales",
            filters=[FilterSpec(column="channel", operator=FilterOperator.eq, value="online")],
        )
        run_filter_table(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        # original table still has 5 rows
        spec2 = PreviewTableSpec(table_name="sales")
        out2 = run_preview_table(db_path=sales_db, spec=spec2, dataset_version_id=VERSION_ID)
        assert out2.row_count == 5


# ---------------------------------------------------------------------------
# run_simple_join
# ---------------------------------------------------------------------------

class TestSimpleJoin:
    def test_join_returns_merged_result(self, two_table_db):
        spec = SimpleJoinSpec(
            left_table="orders",
            right_table="customers",
            join_key_left="customer_id",
            join_key_right="id",
            output_columns=["order_id", "name", "total"],
        )
        out = run_simple_join(db_path=two_table_db, spec=spec, dataset_version_id=VERSION_ID)
        assert "name" in out.columns
        assert "order_id" in out.columns
        assert out.row_count == 3  # customer 10 appears twice

    def test_invalid_left_table_raises(self, two_table_db):
        spec = SimpleJoinSpec(
            left_table="nonexistent",
            right_table="customers",
            join_key_left="id",
            join_key_right="id",
            output_columns=[],
        )
        with pytest.raises(AnalyticsToolError, match="nonexistent"):
            run_simple_join(db_path=two_table_db, spec=spec, dataset_version_id=VERSION_ID)

    def test_invalid_join_key_raises(self, two_table_db):
        spec = SimpleJoinSpec(
            left_table="orders",
            right_table="customers",
            join_key_left="bad_key",
            join_key_right="id",
            output_columns=[],
        )
        with pytest.raises(AnalyticsToolError, match="bad_key"):
            run_simple_join(db_path=two_table_db, spec=spec, dataset_version_id=VERSION_ID)

    def test_invalid_output_column_raises(self, two_table_db):
        spec = SimpleJoinSpec(
            left_table="orders",
            right_table="customers",
            join_key_left="customer_id",
            join_key_right="id",
            output_columns=["nonexistent_col"],
        )
        with pytest.raises(AnalyticsToolError, match="nonexistent_col"):
            run_simple_join(db_path=two_table_db, spec=spec, dataset_version_id=VERSION_ID)

    def test_limit_respected(self, two_table_db):
        spec = SimpleJoinSpec(
            left_table="orders",
            right_table="customers",
            join_key_left="customer_id",
            join_key_right="id",
            output_columns=["order_id", "name", "total"],
            limit=2,
        )
        out = run_simple_join(db_path=two_table_db, spec=spec, dataset_version_id=VERSION_ID)
        assert out.row_count == 2


# ---------------------------------------------------------------------------
# run_generate_visual
# ---------------------------------------------------------------------------

class TestGenerateVisual:
    def test_returns_visual_output(self, sales_db):
        spec = GenerateVisualSpec(
            table_name="sales",
            chart_type="bar",
            x_column="channel",
            y_column="revenue",
            aggregation=AllowedAggregation.sum,
        )
        out = run_generate_visual(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        assert out.output_type == "visual"
        assert out.dataset_version_id == VERSION_ID
        assert out.chart_type == "bar"
        assert out.can_save_to_visuals is True

    def test_chart_spec_json_populated(self, sales_db):
        spec = GenerateVisualSpec(
            table_name="sales",
            chart_type="line",
            x_column="month",
            y_column="revenue",
        )
        out = run_generate_visual(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        assert "data" in out.chart_spec_json
        assert "x_key" in out.chart_spec_json

    def test_invalid_table_raises(self, sales_db):
        spec = GenerateVisualSpec(
            table_name="bad_table",
            chart_type="bar",
            x_column="x",
        )
        with pytest.raises(AnalyticsToolError, match="bad_table"):
            run_generate_visual(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)

    def test_invalid_column_raises(self, sales_db):
        spec = GenerateVisualSpec(
            table_name="sales",
            chart_type="bar",
            x_column="nonexistent",
        )
        with pytest.raises(AnalyticsToolError, match="nonexistent"):
            run_generate_visual(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)

    def test_unsupported_chart_type_raises(self, sales_db):
        spec = GenerateVisualSpec(
            table_name="sales",
            chart_type="treemap",
            x_column="channel",
        )
        with pytest.raises(AnalyticsToolError, match="treemap"):
            run_generate_visual(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)

    def test_does_not_mutate_dataset(self, sales_db):
        spec = GenerateVisualSpec(
            table_name="sales",
            chart_type="bar",
            x_column="channel",
            y_column="revenue",
        )
        run_generate_visual(db_path=sales_db, spec=spec, dataset_version_id=VERSION_ID)
        out = run_preview_table(
            db_path=sales_db,
            spec=PreviewTableSpec(table_name="sales"),
            dataset_version_id=VERSION_ID,
        )
        assert out.row_count == 5


# ---------------------------------------------------------------------------
# Large result storage
# ---------------------------------------------------------------------------

class TestLargeResultStorage:
    def test_small_result_not_stored(self, sales_db, local_storage):
        spec = PreviewTableSpec(table_name="sales")
        out = run_preview_table(
            db_path=sales_db,
            spec=spec,
            dataset_version_id=VERSION_ID,
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            storage=local_storage,
        )
        assert out.storage_path is None

    def test_large_result_stored_as_csv(self, tmp_path, local_storage):
        db = tmp_path / "big.duckdb"
        df = pd.DataFrame({"x": range(INLINE_LIMIT + 10), "y": range(INLINE_LIMIT + 10)})
        create_version_duckdb({"big": df}, db)

        spec = PreviewTableSpec(table_name="big", limit=INLINE_LIMIT + 10)
        out = run_preview_table(
            db_path=db,
            spec=spec,
            dataset_version_id=VERSION_ID,
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            storage=local_storage,
        )

        assert out.storage_path is not None
        assert out.storage_format == "csv"
        assert out.storage_backend == "local"
        assert len(out.preview_rows) <= PREVIEW_LIMIT
        assert out.row_count == INLINE_LIMIT + 10

    def test_large_result_not_stored_without_storage(self, tmp_path):
        db = tmp_path / "big.duckdb"
        df = pd.DataFrame({"x": range(INLINE_LIMIT + 10)})
        create_version_duckdb({"big": df}, db)

        spec = PreviewTableSpec(table_name="big", limit=INLINE_LIMIT + 10)
        out = run_preview_table(db_path=db, spec=spec, dataset_version_id=VERSION_ID)

        assert out.storage_path is None

    def test_no_raw_sql_field_on_any_tool_spec(self):
        specs = [
            PreviewTableSpec(table_name="t"),
            AggregateTableSpec(
                table_name="t",
                group_by=["x"],
                metrics=[MetricSpec(column="y", aggregation=AllowedAggregation.sum)],
            ),
            FilterTableSpec(
                table_name="t",
                filters=[FilterSpec(column="x", operator=FilterOperator.eq, value=1)],
            ),
        ]
        for spec in specs:
            assert not hasattr(spec, "sql")
            assert not hasattr(spec, "raw_sql")
            assert not hasattr(spec, "query")
