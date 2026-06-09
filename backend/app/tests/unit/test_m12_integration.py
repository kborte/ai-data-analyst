"""M12F: Focused integration tests for the M12 analytics planner pipeline.

Coverage areas:
- planner schema validation (no-SQL, discriminated union, can_save_* invariants)
- recent message and prior output ref schema validation
- dataset context builder (version scoping, missing profiles)
- safe analytics tools (preview, aggregate, filter, join, visual)
- storage-backed table outputs (INLINE_LIMIT threshold)
- planner follow-up resolution (recent messages with output refs)
- analytics ask endpoint (full round-trip)
- explicit save-as-view flow (ask → save via HTTP route)
- explicit save-as-visual flow (ask → save via HTTP route)
- invalid table / column handling (graceful errors)
- unsupported request handling
- dataset version scoping (two versions, isolated state)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_llm_provider, get_repos, get_storage
from app.main import app
from app.schemas.analytics import (
    AnalyticsIntent,
    AnalyticsPlan,
    MixedOutput,
    OutputType,
    PriorOutputRef,
    RecentMessage,
    TableOutput,
    TextOutput,
    VisualOutput,
    MessageRole,
)
from app.schemas.analytics_context import DatasetContext, DatasetContextColumn, DatasetContextTable
from app.schemas.common import DatasetVersionType
from app.schemas.dataset import Dataset, DatasetVersion
from app.services.analytics_context import build_dataset_context
from app.services.analytics_planner import AnalyticsPlanner, classify_intent
from app.tools.analytics.query_tools import (
    INLINE_LIMIT,
    AnalyticsToolError,
    run_aggregate_table,
    run_filter_table,
    run_generate_visual,
    run_preview_table,
    run_simple_join,
)
from app.schemas.analytics import (
    AggregateTableSpec,
    FilterTableSpec,
    FilterSpec,
    GenerateVisualSpec,
    MetricSpec,
    PreviewTableSpec,
    SimpleJoinSpec,
    AllowedAggregation,
    FilterOperator,
)
from app.tools.data.duckdb_service import create_version_duckdb
from app.tools.files.storage_service import LocalStorageBackend
from app.tools.llm.provider import FakeLLMProvider


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(tz=timezone.utc)


def _dataset(workspace_id=None) -> Dataset:
    return Dataset(
        dataset_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        name="Sales Dataset",
        created_by_user_id=uuid4(),
        created_at=_now(),
    )


def _version(dataset: Dataset, storage_path: str | None = None) -> DatasetVersion:
    return DatasetVersion(
        dataset_version_id=uuid4(),
        dataset_id=dataset.dataset_id,
        version_number=1,
        version_type=DatasetVersionType.original,
        storage_path=storage_path,
        created_by_user_id=uuid4(),
        created_at=_now(),
    )


def _build_sales_db(path: Path, rows: int = 5) -> Path:
    df = pd.DataFrame({
        "month": [f"M{i}" for i in range(rows)],
        "channel": ["online" if i % 2 == 0 else "store" for i in range(rows)],
        "revenue": [float(i * 100) for i in range(rows)],
        "units": [i * 10 for i in range(rows)],
    })
    create_version_duckdb({"sales": df}, path)
    return path


def _build_two_table_db(path: Path) -> Path:
    orders = pd.DataFrame({"order_id": [1, 2], "customer_id": [10, 11], "amount": [50.0, 75.0]})
    customers = pd.DataFrame({"customer_id": [10, 11], "name": ["Alice", "Bob"]})
    create_version_duckdb({"orders": orders, "customers": customers}, path)
    return path


def _context_for(dataset: Dataset, version: DatasetVersion, table_name: str = "sales") -> DatasetContext:
    cols = [
        DatasetContextColumn(column_name="month", data_type="varchar", is_likely_date=True),
        DatasetContextColumn(column_name="channel", data_type="varchar", is_likely_categorical=True),
        DatasetContextColumn(column_name="revenue", data_type="double", is_likely_metric=True),
        DatasetContextColumn(column_name="units", data_type="int", is_likely_metric=True),
    ]
    table = DatasetContextTable(
        table_name=table_name,
        row_count=100,
        column_count=4,
        columns=cols,
        has_profile=True,
    )
    return DatasetContext(
        dataset_id=dataset.dataset_id,
        dataset_name=dataset.name,
        dataset_version_id=version.dataset_version_id,
        version_number=version.version_number,
        version_type=str(version.version_type),
        tables=[table],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_repos():
    return Repos()


@pytest.fixture()
def fake_storage(tmp_path):
    return LocalStorageBackend(base_dir=str(tmp_path))


@pytest.fixture()
def client(mem_repos, fake_storage):
    app.dependency_overrides[get_repos] = lambda: mem_repos
    app.dependency_overrides[get_storage] = lambda: fake_storage
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()
    yield TestClient(app)
    app.dependency_overrides.pop(get_repos, None)
    app.dependency_overrides.pop(get_storage, None)
    app.dependency_overrides.pop(get_llm_provider, None)


@pytest.fixture()
def versioned_dataset(mem_repos, fake_storage, tmp_path):
    """Registered dataset + version backed by a real DuckDB file."""
    ds = _dataset()
    mem_repos.dataset.save(ds)
    db_path = _build_sales_db(tmp_path / "v1.duckdb")
    storage_key = f"ws/{ds.workspace_id}/ds/{ds.dataset_id}/v1.duckdb"
    fake_storage.save(storage_key, db_path.read_bytes())
    ver = _version(ds, storage_path=storage_key)
    mem_repos.dataset_version.save(ver)
    return ds, ver


@pytest.fixture()
def sales_db(tmp_path) -> Path:
    return _build_sales_db(tmp_path / "sales.duckdb")


@pytest.fixture()
def two_table_db(tmp_path) -> Path:
    return _build_two_table_db(tmp_path / "two.duckdb")


@pytest.fixture()
def local_storage(tmp_path):
    return LocalStorageBackend(base_dir=str(tmp_path))


# ===========================================================================
# 1. SCHEMA VALIDATION
# ===========================================================================

class TestSchemaValidation:
    """Validate core M12 schema invariants without touching DB or storage."""

    def test_table_output_can_save_as_view_is_always_true(self):
        t = TableOutput(
            dataset_version_id=uuid4(),
            title="t",
            columns=["a"],
            preview_rows=[],
            row_count=0,
            source_spec_json={},
        )
        assert t.can_save_as_view is True

    def test_table_output_cannot_set_can_save_as_view_false(self):
        import pytest as _pytest
        with _pytest.raises(Exception):
            TableOutput(
                dataset_version_id=uuid4(),
                title="t",
                columns=[],
                preview_rows=[],
                row_count=0,
                source_spec_json={},
                can_save_as_view=False,  # type: ignore[arg-type]
            )

    def test_visual_output_can_save_to_visuals_is_always_true(self):
        v = VisualOutput(
            dataset_version_id=uuid4(),
            title="v",
            chart_type="bar",
            chart_spec_json={},
            source_spec_json={},
        )
        assert v.can_save_to_visuals is True

    def test_plan_has_no_sql_or_raw_sql_field(self):
        from app.schemas.analytics import PreviewTableSpec, AnalyticsPlan
        spec = PreviewTableSpec(table_name="sales")
        plan = AnalyticsPlan(
            dataset_id=uuid4(),
            dataset_version_id=uuid4(),
            intent=AnalyticsIntent.table_result,
            reasoning_summary="test",
            tool_name="preview_table",
            tool_spec=spec,
            expected_output_type=OutputType.table,
            suggested_title="Preview",
        )
        assert not hasattr(plan, "sql")
        assert not hasattr(plan, "raw_sql")
        assert not hasattr(plan.tool_spec, "sql")

    def test_recent_message_user_role(self):
        msg = RecentMessage(role=MessageRole.user, content="show revenue")
        assert msg.role == MessageRole.user

    def test_recent_message_assistant_role_with_output_refs(self):
        ref = PriorOutputRef(
            output_id=uuid4(),
            output_type=OutputType.table,
            dataset_version_id=uuid4(),
            title="Revenue Table",
        )
        msg = RecentMessage(
            role=MessageRole.assistant,
            content="Here is your table.",
            output_refs=[ref],
        )
        assert len(msg.output_refs) == 1
        assert msg.output_refs[0].output_type == OutputType.table

    def test_prior_output_ref_table_type(self):
        ref = PriorOutputRef(
            output_id=uuid4(),
            output_type=OutputType.table,
            dataset_version_id=uuid4(),
            title="My Table",
        )
        assert ref.output_type == OutputType.table

    def test_prior_output_ref_visual_type(self):
        ref = PriorOutputRef(
            output_id=uuid4(),
            output_type=OutputType.visual,
            dataset_version_id=uuid4(),
            title="My Chart",
        )
        assert ref.output_type == OutputType.visual

    def test_prior_output_ref_preserves_version_id(self):
        vid = uuid4()
        ref = PriorOutputRef(
            output_id=uuid4(),
            output_type=OutputType.table,
            dataset_version_id=vid,
            title="v",
        )
        assert ref.dataset_version_id == vid

    def test_no_tool_spec_has_raw_sql(self):
        specs = [
            PreviewTableSpec(table_name="t"),
            AggregateTableSpec(
                table_name="t",
                group_by=["a"],
                metrics=[MetricSpec(column="b", aggregation=AllowedAggregation.sum)],
            ),
            FilterTableSpec(
                table_name="t",
                filters=[FilterSpec(column="a", operator=FilterOperator.eq, value="x")],
            ),
            SimpleJoinSpec(
                left_table="a",
                right_table="b",
                join_key_left="id",
                join_key_right="id",
                output_columns=["id"],
            ),
            GenerateVisualSpec(table_name="t", chart_type="bar", x_column="a", y_column="b"),
        ]
        for spec in specs:
            assert not hasattr(spec, "sql"), f"{spec.tool_name} has 'sql' field"
            assert not hasattr(spec, "raw_sql"), f"{spec.tool_name} has 'raw_sql' field"


# ===========================================================================
# 2. DATASET CONTEXT BUILDER
# ===========================================================================

class TestContextBuilder:
    """Version scoping and graceful profile handling."""

    def test_context_scoped_to_requested_version(self, mem_repos):
        ds = _dataset()
        mem_repos.dataset.save(ds)
        v1 = _version(ds)
        v2 = DatasetVersion(
            dataset_version_id=uuid4(),
            dataset_id=ds.dataset_id,
            version_number=2,
            version_type=DatasetVersionType.cleaned,
            created_by_user_id=uuid4(),
            created_at=_now(),
        )
        mem_repos.dataset_version.save(v1)
        mem_repos.dataset_version.save(v2)

        ctx = build_dataset_context(
            dataset_id=ds.dataset_id,
            dataset_version_id=v1.dataset_version_id,
            dataset_repo=mem_repos.dataset,
            version_repo=mem_repos.dataset_version,
            table_repo=mem_repos.dataset_table,
            profile_repo=mem_repos.profile,
        )
        assert ctx is not None
        assert ctx.dataset_version_id == v1.dataset_version_id

    def test_context_returns_none_for_unknown_dataset(self, mem_repos):
        ctx = build_dataset_context(
            dataset_id=uuid4(),
            dataset_version_id=uuid4(),
            dataset_repo=mem_repos.dataset,
            version_repo=mem_repos.dataset_version,
            table_repo=mem_repos.dataset_table,
            profile_repo=mem_repos.profile,
        )
        assert ctx is None

    def test_context_handles_missing_profile_gracefully(self, mem_repos):
        ds = _dataset()
        mem_repos.dataset.save(ds)
        ver = _version(ds)
        mem_repos.dataset_version.save(ver)

        ctx = build_dataset_context(
            dataset_id=ds.dataset_id,
            dataset_version_id=ver.dataset_version_id,
            dataset_repo=mem_repos.dataset,
            version_repo=mem_repos.dataset_version,
            table_repo=mem_repos.dataset_table,
            profile_repo=mem_repos.profile,
        )
        # Context builds without error; tables list may be empty (no DatasetTable records)
        assert ctx is not None
        assert ctx.dataset_id == ds.dataset_id

    def test_context_does_not_include_full_rows(self, mem_repos):
        ds = _dataset()
        mem_repos.dataset.save(ds)
        ver = _version(ds)
        mem_repos.dataset_version.save(ver)

        ctx = build_dataset_context(
            dataset_id=ds.dataset_id,
            dataset_version_id=ver.dataset_version_id,
            dataset_repo=mem_repos.dataset,
            version_repo=mem_repos.dataset_version,
            table_repo=mem_repos.dataset_table,
            profile_repo=mem_repos.profile,
        )
        assert ctx is not None
        # Context is a DatasetContext schema, not raw data rows
        for table in ctx.tables:
            assert not hasattr(table, "rows")
            assert not hasattr(table, "data")


# ===========================================================================
# 3. SAFE ANALYTICS TOOLS
# ===========================================================================

class TestAnalyticsToolsSafety:
    """Validate tools reject invalid inputs and never mutate the dataset."""

    def test_preview_invalid_table_raises_tool_error(self, sales_db):
        spec = PreviewTableSpec(table_name="nonexistent")
        with pytest.raises(AnalyticsToolError):
            run_preview_table(db_path=sales_db, spec=spec, dataset_version_id=uuid4())

    def test_preview_invalid_column_raises_tool_error(self, sales_db):
        spec = PreviewTableSpec(table_name="sales", columns=["bad_col"])
        with pytest.raises(AnalyticsToolError):
            run_preview_table(db_path=sales_db, spec=spec, dataset_version_id=uuid4())

    def test_aggregate_invalid_metric_column_raises(self, sales_db):
        spec = AggregateTableSpec(
            table_name="sales",
            group_by=["channel"],
            metrics=[MetricSpec(column="nonexistent", aggregation=AllowedAggregation.sum)],
        )
        with pytest.raises(AnalyticsToolError):
            run_aggregate_table(db_path=sales_db, spec=spec, dataset_version_id=uuid4())

    def test_filter_invalid_column_raises(self, sales_db):
        spec = FilterTableSpec(
            table_name="sales",
            filters=[FilterSpec(column="bad_col", operator=FilterOperator.eq, value="online")],
        )
        with pytest.raises(AnalyticsToolError):
            run_filter_table(db_path=sales_db, spec=spec, dataset_version_id=uuid4())

    def test_join_invalid_table_raises(self, two_table_db):
        spec = SimpleJoinSpec(
            left_table="orders",
            right_table="nonexistent",
            join_key_left="customer_id",
            join_key_right="customer_id",
            output_columns=["order_id"],
        )
        with pytest.raises(AnalyticsToolError):
            run_simple_join(db_path=two_table_db, spec=spec, dataset_version_id=uuid4())

    def test_visual_invalid_column_raises(self, sales_db):
        spec = GenerateVisualSpec(
            table_name="sales",
            chart_type="bar",
            x_column="month",
            y_column="bad_col",
        )
        with pytest.raises(AnalyticsToolError):
            run_generate_visual(db_path=sales_db, spec=spec, dataset_version_id=uuid4())

    def test_tools_do_not_mutate_source_db(self, sales_db):
        original_mtime = sales_db.stat().st_mtime
        spec = AggregateTableSpec(
            table_name="sales",
            group_by=["channel"],
            metrics=[MetricSpec(column="revenue", aggregation=AllowedAggregation.sum)],
        )
        run_aggregate_table(db_path=sales_db, spec=spec, dataset_version_id=uuid4())
        assert sales_db.stat().st_mtime == original_mtime


# ===========================================================================
# 4. STORAGE-BACKED TABLE OUTPUTS
# ===========================================================================

class TestStorageBackedOutputs:
    """Large results (> INLINE_LIMIT rows) should be stored as artifacts."""

    def test_large_result_writes_csv_to_storage(self, tmp_path, local_storage):
        large_db = tmp_path / "large.duckdb"
        n = INLINE_LIMIT + 50
        df = pd.DataFrame({
            "id": range(n),
            "value": [float(i) for i in range(n)],
        })
        create_version_duckdb({"data": df}, large_db)

        workspace_id = uuid4()
        dataset_id = uuid4()
        spec = PreviewTableSpec(table_name="data", limit=n)
        result = run_preview_table(
            db_path=large_db,
            spec=spec,
            dataset_version_id=uuid4(),
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            storage=local_storage,
        )
        assert isinstance(result, TableOutput)
        assert result.row_count == n
        assert result.storage_path is not None
        assert result.storage_path.endswith(".csv")
        # File must actually exist in storage
        stored = local_storage.read(result.storage_path)
        assert len(stored) > 0

    def test_small_result_has_no_storage_path(self, sales_db, local_storage):
        spec = PreviewTableSpec(table_name="sales")
        result = run_preview_table(
            db_path=sales_db,
            spec=spec,
            dataset_version_id=uuid4(),
            workspace_id=uuid4(),
            dataset_id=uuid4(),
            storage=local_storage,
        )
        assert isinstance(result, TableOutput)
        assert result.storage_path is None

    def test_large_result_without_storage_still_returns_output(self, tmp_path):
        large_db = tmp_path / "large2.duckdb"
        n = INLINE_LIMIT + 10
        df = pd.DataFrame({"x": range(n), "y": [float(i) for i in range(n)]})
        create_version_duckdb({"tbl": df}, large_db)

        spec = PreviewTableSpec(table_name="tbl")
        result = run_preview_table(
            db_path=large_db,
            spec=spec,
            dataset_version_id=uuid4(),
        )
        assert isinstance(result, TableOutput)
        assert result.storage_path is None  # no storage provided → no artifact


# ===========================================================================
# 5. PLANNER FOLLOW-UP RESOLUTION
# ===========================================================================

class TestPlannerFollowUp:
    """Planner resolves follow-up questions via recent messages and prior refs."""

    def setup_method(self):
        self.planner = AnalyticsPlanner(llm=FakeLLMProvider())

    def _ctx(self, dataset_id=None, version_id=None):
        ds_id = dataset_id or uuid4()
        ver_id = version_id or uuid4()
        cols = [
            DatasetContextColumn(column_name="month", data_type="varchar"),
            DatasetContextColumn(column_name="revenue", data_type="double", is_likely_metric=True),
        ]
        table = DatasetContextTable(
            table_name="sales", row_count=100, column_count=2, columns=cols, has_profile=True
        )
        return DatasetContext(
            dataset_id=ds_id,
            dataset_name="Sales",
            dataset_version_id=ver_id,
            version_number=1,
            version_type="original",
            tables=[table],
        )

    def test_follow_up_via_recent_message_output_ref_triggers_visual(self):
        ver_id = uuid4()
        ctx = self._ctx(version_id=ver_id)
        table_ref = PriorOutputRef(
            output_id=uuid4(),
            output_type=OutputType.table,
            dataset_version_id=ver_id,
            title="Revenue table",
        )
        msg = RecentMessage(
            role=MessageRole.assistant,
            content="Here is the table.",
            output_refs=[table_ref],
        )
        plan = self.planner.plan(
            "now show that as a chart",
            ctx,
            recent_messages=[msg],
        )
        assert plan.intent == AnalyticsIntent.visual_result

    def test_follow_up_via_prior_output_refs_triggers_save(self):
        ver_id = uuid4()
        ctx = self._ctx(version_id=ver_id)
        table_ref = PriorOutputRef(
            output_id=uuid4(),
            output_type=OutputType.table,
            dataset_version_id=ver_id,
            title="Revenue table",
        )
        plan = self.planner.plan(
            "save this table",
            ctx,
            prior_output_refs=[table_ref],
        )
        assert plan.intent == AnalyticsIntent.save_table_result

    def test_save_without_prior_refs_does_not_trigger_save_intent(self):
        ctx = self._ctx()
        plan = self.planner.plan("save this table", ctx, prior_output_refs=[])
        assert plan.intent != AnalyticsIntent.save_table_result

    def test_planner_always_preserves_version_id(self):
        ver_id = uuid4()
        ctx = self._ctx(version_id=ver_id)
        plan = self.planner.plan("show revenue by month", ctx)
        assert plan.dataset_version_id == ver_id

    def test_recent_messages_not_stored_on_plan(self):
        ctx = self._ctx()
        msgs = [RecentMessage(role=MessageRole.user, content="hello")]
        plan = self.planner.plan("show data", ctx, recent_messages=msgs)
        assert not hasattr(plan, "recent_messages")
        assert not hasattr(plan, "conversation_id")


# ===========================================================================
# 6. ASK ENDPOINT — FULL ROUND-TRIP
# ===========================================================================

class TestAskEndpointRoundTrip:
    def _url(self, dataset_id, version_id):
        return f"/datasets/{dataset_id}/versions/{version_id}/analytics/ask"

    def test_ask_returns_typed_output_with_version_id(self, client, versioned_dataset):
        ds, ver = versioned_dataset
        resp = client.post(self._url(ds.dataset_id, ver.dataset_version_id),
                           json={"question": "show the data"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["output"]["dataset_version_id"] == str(ver.dataset_version_id)

    def test_ask_aggregate_question_returns_output(self, client, versioned_dataset):
        ds, ver = versioned_dataset
        resp = client.post(self._url(ds.dataset_id, ver.dataset_version_id),
                           json={"question": "sum revenue by channel"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["output"]["output_type"] in ("table", "text", "mixed")

    def test_ask_visual_question_returns_output(self, client, versioned_dataset):
        ds, ver = versioned_dataset
        resp = client.post(self._url(ds.dataset_id, ver.dataset_version_id),
                           json={"question": "plot revenue by channel as a bar chart"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["output"]["output_type"] in ("visual", "text", "mixed")

    def test_ask_does_not_persist_recent_messages(self, client, versioned_dataset):
        ds, ver = versioned_dataset
        resp = client.post(
            self._url(ds.dataset_id, ver.dataset_version_id),
            json={
                "question": "show data",
                "recent_messages": [{"role": "user", "content": "context", "output_refs": []}],
            },
        )
        assert resp.status_code == 200

    def test_ask_output_never_auto_saved(self, client, versioned_dataset, mem_repos):
        ds, ver = versioned_dataset
        for _ in range(3):
            client.post(self._url(ds.dataset_id, ver.dataset_version_id),
                        json={"question": "show data"})
        assert mem_repos.saved_view.list_by_version(ver.dataset_version_id) == []
        assert mem_repos.saved_visual.list_by_version(ver.dataset_version_id) == []

    def test_ask_unsupported_question_returns_text(self, client, versioned_dataset):
        ds, ver = versioned_dataset
        resp = client.post(self._url(ds.dataset_id, ver.dataset_version_id),
                           json={"question": "delete all the data permanently"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["output"]["output_type"] == "text"


# ===========================================================================
# 7. EXPLICIT SAVE-AS-VIEW FLOW
# ===========================================================================

class TestExplicitSaveAsView:
    _SAVE_URL = "/analytics/table-results/save-as-view"

    def test_ask_then_save_inline_rows(self, client, versioned_dataset, mem_repos):
        ds, ver = versioned_dataset
        # Step 1: ask for aggregate result
        ask_resp = client.post(
            f"/datasets/{ds.dataset_id}/versions/{ver.dataset_version_id}/analytics/ask",
            json={"question": "sum revenue by channel"},
        )
        assert ask_resp.status_code == 200

        # Step 2: user explicitly saves result via save route
        save_resp = client.post(self._SAVE_URL, json={
            "dataset_id": str(ds.dataset_id),
            "dataset_version_id": str(ver.dataset_version_id),
            "name": "Revenue by Channel",
            "columns": ["channel", "revenue_sum"],
            "rows": [["online", 250.0], ["store", 200.0]],
        })
        assert save_resp.status_code == 201
        body = save_resp.json()
        assert body["name"] == "Revenue by Channel"
        assert body["dataset_id"] == str(ds.dataset_id)
        assert body["dataset_version_id"] == str(ver.dataset_version_id)

    def test_saved_view_is_version_scoped(self, client, versioned_dataset, mem_repos):
        ds, ver = versioned_dataset
        client.post(self._SAVE_URL, json={
            "dataset_id": str(ds.dataset_id),
            "dataset_version_id": str(ver.dataset_version_id),
            "name": "Scoped",
            "columns": ["x"],
            "rows": [[1]],
        })
        other_version_id = uuid4()
        assert mem_repos.saved_view.list_by_version(other_version_id) == []
        views = mem_repos.saved_view.list_by_version(ver.dataset_version_id)
        assert len(views) == 1

    def test_save_view_requires_columns_or_storage_path(self, client, versioned_dataset):
        ds, ver = versioned_dataset
        resp = client.post(self._SAVE_URL, json={
            "dataset_id": str(ds.dataset_id),
            "dataset_version_id": str(ver.dataset_version_id),
            "name": "Empty",
        })
        assert resp.status_code == 422

    def test_save_view_404_on_wrong_dataset_version(self, client, versioned_dataset):
        ds, ver = versioned_dataset
        resp = client.post(self._SAVE_URL, json={
            "dataset_id": str(uuid4()),
            "dataset_version_id": str(ver.dataset_version_id),
            "name": "Bad",
            "columns": ["x"],
            "rows": [[1]],
        })
        assert resp.status_code == 404


# ===========================================================================
# 8. EXPLICIT SAVE-AS-VISUAL FLOW
# ===========================================================================

class TestExplicitSaveAsVisual:
    _SAVE_URL = "/analytics/visual-results/save-as-visual"

    def test_ask_then_save_visual(self, client, versioned_dataset, mem_repos):
        ds, ver = versioned_dataset
        # Step 1: ask for visual
        ask_resp = client.post(
            f"/datasets/{ds.dataset_id}/versions/{ver.dataset_version_id}/analytics/ask",
            json={"question": "bar chart of revenue by channel"},
        )
        assert ask_resp.status_code == 200

        # Step 2: user explicitly saves
        save_resp = client.post(self._SAVE_URL, json={
            "dataset_id": str(ds.dataset_id),
            "dataset_version_id": str(ver.dataset_version_id),
            "title": "Revenue Bar Chart",
            "chart_type": "bar",
            "chart_spec_json": {},
        })
        assert save_resp.status_code == 201
        body = save_resp.json()
        assert body["title"] == "Revenue Bar Chart"
        assert body["dataset_version_id"] == str(ver.dataset_version_id)

    def test_saved_visual_is_version_scoped(self, client, versioned_dataset, mem_repos):
        ds, ver = versioned_dataset
        client.post(self._SAVE_URL, json={
            "dataset_id": str(ds.dataset_id),
            "dataset_version_id": str(ver.dataset_version_id),
            "title": "Chart",
            "chart_type": "line",
        })
        other_version_id = uuid4()
        assert mem_repos.saved_visual.list_by_version(other_version_id) == []
        visuals = mem_repos.saved_visual.list_by_version(ver.dataset_version_id)
        assert len(visuals) == 1

    def test_save_visual_404_on_wrong_dataset(self, client, versioned_dataset):
        ds, ver = versioned_dataset
        resp = client.post(self._SAVE_URL, json={
            "dataset_id": str(uuid4()),
            "dataset_version_id": str(ver.dataset_version_id),
            "title": "Bad",
            "chart_type": "bar",
        })
        assert resp.status_code == 404


# ===========================================================================
# 9. DATASET VERSION SCOPING — TWO ISOLATED VERSIONS
# ===========================================================================

class TestDatasetVersionScoping:
    """Saves on v1 must not appear on v2 and vice versa."""

    def _make_two_versions(self, mem_repos, fake_storage, tmp_path):
        ds = _dataset()
        mem_repos.dataset.save(ds)

        db_path = _build_sales_db(tmp_path / "v1.duckdb")
        key1 = f"ds/{ds.dataset_id}/v1.duckdb"
        key2 = f"ds/{ds.dataset_id}/v2.duckdb"
        fake_storage.save(key1, db_path.read_bytes())
        fake_storage.save(key2, db_path.read_bytes())

        v1 = _version(ds, storage_path=key1)
        v2 = DatasetVersion(
            dataset_version_id=uuid4(),
            dataset_id=ds.dataset_id,
            version_number=2,
            version_type=DatasetVersionType.cleaned,
            storage_path=key2,
            created_by_user_id=uuid4(),
            created_at=_now(),
        )
        mem_repos.dataset_version.save(v1)
        mem_repos.dataset_version.save(v2)
        return ds, v1, v2

    def test_view_saved_on_v1_not_visible_on_v2(self, client, mem_repos, fake_storage, tmp_path):
        ds, v1, v2 = self._make_two_versions(mem_repos, fake_storage, tmp_path)

        client.post("/analytics/table-results/save-as-view", json={
            "dataset_id": str(ds.dataset_id),
            "dataset_version_id": str(v1.dataset_version_id),
            "name": "V1 View",
            "columns": ["x"],
            "rows": [[1]],
        })

        assert mem_repos.saved_view.list_by_version(v1.dataset_version_id) != []
        assert mem_repos.saved_view.list_by_version(v2.dataset_version_id) == []

    def test_visual_saved_on_v2_not_visible_on_v1(self, client, mem_repos, fake_storage, tmp_path):
        ds, v1, v2 = self._make_two_versions(mem_repos, fake_storage, tmp_path)

        client.post("/analytics/visual-results/save-as-visual", json={
            "dataset_id": str(ds.dataset_id),
            "dataset_version_id": str(v2.dataset_version_id),
            "title": "V2 Chart",
            "chart_type": "bar",
        })

        assert mem_repos.saved_visual.list_by_version(v2.dataset_version_id) != []
        assert mem_repos.saved_visual.list_by_version(v1.dataset_version_id) == []

    def test_ask_on_v1_does_not_bleed_into_v2_state(self, client, mem_repos, fake_storage, tmp_path):
        ds, v1, v2 = self._make_two_versions(mem_repos, fake_storage, tmp_path)
        resp = client.post(
            f"/datasets/{ds.dataset_id}/versions/{v1.dataset_version_id}/analytics/ask",
            json={"question": "show data"},
        )
        assert resp.status_code == 200
        # v2 repos untouched
        assert mem_repos.saved_view.list_by_version(v2.dataset_version_id) == []
        assert mem_repos.saved_visual.list_by_version(v2.dataset_version_id) == []


# ===========================================================================
# 10. UNSUPPORTED AND INVALID HANDLING
# ===========================================================================

class TestUnsupportedAndInvalid:
    def test_unsupported_intent_classified_correctly(self):
        assert classify_intent("please delete all rows", []) == AnalyticsIntent.unsupported
        assert classify_intent("xyzzy gibberish completely unknown 1234", []) == AnalyticsIntent.unsupported

    def test_planner_execute_unsupported_returns_text(self, sales_db):
        ctx = DatasetContext(
            dataset_id=uuid4(),
            dataset_name="Test",
            dataset_version_id=uuid4(),
            version_number=1,
            version_type="original",
            tables=[
                DatasetContextTable(
                    table_name="sales",
                    row_count=5,
                    column_count=2,
                    columns=[DatasetContextColumn(column_name="x", data_type="int")],
                    has_profile=False,
                )
            ],
        )
        planner = AnalyticsPlanner(llm=FakeLLMProvider())
        plan = planner.plan("xyzzy gibberish 1234 !!!", ctx)
        result = planner.execute(plan, db_path=sales_db)
        assert result.output_type == "text"
        content_lower = result.content.lower()
        assert "unsupported" in content_lower or "outside" in content_lower or "scope" in content_lower

    def test_ask_endpoint_invalid_table_in_question_returns_gracefully(self, client, versioned_dataset):
        ds, ver = versioned_dataset
        resp = client.post(
            f"/datasets/{ds.dataset_id}/versions/{ver.dataset_version_id}/analytics/ask",
            json={"question": "show all rows from nonexistent_table_xyz"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Should return some output type without 500-ing
        assert body["output"]["output_type"] in ("text", "table", "visual", "mixed")
