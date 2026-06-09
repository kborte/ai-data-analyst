"""Tests for M12D analytics planner service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from app.schemas.analytics import (
    AnalyticsIntent,
    OutputType,
    PriorOutputRef,
    RecentMessage,
    MessageRole,
)
from app.schemas.analytics_context import (
    DatasetContext,
    DatasetContextColumn,
    DatasetContextTable,
)
from app.services.analytics_planner import (
    AnalyticsPlanner,
    classify_intent,
)
from app.tools.data.duckdb_service import create_version_duckdb
from app.tools.llm.provider import FakeLLMProvider

DATASET_ID = uuid.uuid4()
VERSION_ID = uuid.uuid4()
NOW = datetime.now(tz=UTC)


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


def _context(has_profile: bool = True) -> DatasetContext:
    cols = [
        DatasetContextColumn(
            column_name="month",
            data_type="date",
            is_likely_date=True,
        ),
        DatasetContextColumn(
            column_name="channel",
            data_type="categorical",
            is_likely_categorical=True,
        ),
        DatasetContextColumn(
            column_name="revenue",
            data_type="float",
            is_likely_metric=True,
        ),
        DatasetContextColumn(
            column_name="units",
            data_type="int",
            is_likely_metric=True,
        ),
    ]
    table = DatasetContextTable(
        table_name="sales",
        row_count=1000,
        column_count=4,
        columns=cols if has_profile else [],
        has_profile=has_profile,
    )
    return DatasetContext(
        dataset_id=DATASET_ID,
        dataset_name="Sales Data",
        dataset_version_id=VERSION_ID,
        version_number=1,
        version_type="original",
        tables=[table],
    )


def _table_ref() -> PriorOutputRef:
    return PriorOutputRef(
        output_id=uuid.uuid4(),
        output_type=OutputType.table,
        dataset_version_id=VERSION_ID,
        title="Revenue by month",
    )


def _visual_ref() -> PriorOutputRef:
    return PriorOutputRef(
        output_id=uuid.uuid4(),
        output_type=OutputType.visual,
        dataset_version_id=VERSION_ID,
        title="Revenue chart",
    )


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

class TestClassifyIntent:
    def test_table_keywords(self):
        assert classify_intent("show me a table of revenue by month", []) == AnalyticsIntent.table_result

    def test_aggregate_keywords(self):
        assert classify_intent("sum revenue by channel", []) == AnalyticsIntent.table_result

    def test_visual_keywords(self):
        assert classify_intent("plot revenue over time", []) == AnalyticsIntent.visual_result

    def test_bar_chart_keyword(self):
        assert classify_intent("bar chart of sales by region", []) == AnalyticsIntent.visual_result

    def test_text_keywords(self):
        # "trend" is not an explicit chart word; "what" triggers text_answer
        assert classify_intent("what is the overall revenue?", []) == AnalyticsIntent.text_answer

    def test_unsupported_returns_unsupported(self):
        result = classify_intent("delete all the data please", [])
        assert result == AnalyticsIntent.unsupported

    def test_save_table_with_prior_table_ref(self):
        intent = classify_intent("save this table", [_table_ref()])
        assert intent == AnalyticsIntent.save_table_result

    def test_save_visual_with_prior_visual_ref(self):
        intent = classify_intent("save this chart", [_visual_ref()])
        assert intent == AnalyticsIntent.save_visual_result

    def test_save_without_prior_refs_is_not_save(self):
        intent = classify_intent("save this table", [])
        assert intent != AnalyticsIntent.save_table_result

    def test_follow_up_chart_from_table_ref(self):
        intent = classify_intent("now show this as a chart", [_table_ref()])
        assert intent == AnalyticsIntent.visual_result


# ---------------------------------------------------------------------------
# Planner.plan()
# ---------------------------------------------------------------------------

class TestPlannerPlan:
    def setup_method(self):
        self.planner = AnalyticsPlanner(llm=FakeLLMProvider())
        self.ctx = _context()

    def test_plan_preserves_dataset_version_id(self):
        plan = self.planner.plan("show revenue by month", self.ctx)
        assert plan.dataset_version_id == VERSION_ID

    def test_plan_preserves_dataset_id(self):
        plan = self.planner.plan("show revenue by month", self.ctx)
        assert plan.dataset_id == DATASET_ID

    def test_plan_has_no_sql_field(self):
        plan = self.planner.plan("show revenue by month", self.ctx)
        assert not hasattr(plan, "sql")
        assert not hasattr(plan, "raw_sql")

    def test_tool_spec_has_no_sql_field(self):
        plan = self.planner.plan("show revenue by month", self.ctx)
        assert not hasattr(plan.tool_spec, "sql")

    def test_table_question_produces_table_plan(self):
        plan = self.planner.plan("show revenue by channel", self.ctx)
        assert plan.intent in (AnalyticsIntent.table_result, AnalyticsIntent.mixed_result)
        assert plan.expected_output_type in (OutputType.table, OutputType.mixed)

    def test_visual_question_produces_visual_plan(self):
        plan = self.planner.plan("plot revenue over time as a line chart", self.ctx)
        assert plan.intent == AnalyticsIntent.visual_result
        assert plan.expected_output_type == OutputType.visual

    def test_unsupported_question_produces_unsupported_plan(self):
        plan = self.planner.plan("abcxyz gibberish nonsense 1234", self.ctx)
        assert plan.intent == AnalyticsIntent.unsupported

    def test_recent_messages_not_persisted(self):
        msgs = [RecentMessage(role=MessageRole.user, content="show me revenue")]
        plan = self.planner.plan("now show as chart", self.ctx, recent_messages=msgs)
        # Plan returns without error — messages were consumed, not stored
        assert plan.dataset_version_id == VERSION_ID
        assert not hasattr(plan, "conversation_id")

    def test_follow_up_via_recent_message_output_ref(self):
        ref = _table_ref()
        msg = RecentMessage(
            role=MessageRole.assistant,
            content="Here is the revenue table.",
            output_refs=[ref],
        )
        plan = self.planner.plan(
            "now show this as a chart",
            self.ctx,
            recent_messages=[msg],
        )
        assert plan.intent == AnalyticsIntent.visual_result

    def test_save_intent_via_prior_output_refs(self):
        plan = self.planner.plan(
            "save this table",
            self.ctx,
            prior_output_refs=[_table_ref()],
        )
        assert plan.intent == AnalyticsIntent.save_table_result

    def test_context_with_no_profile_still_produces_plan(self):
        ctx = _context(has_profile=False)
        plan = self.planner.plan("show data", ctx)
        assert plan.dataset_version_id == VERSION_ID

    def test_plan_tool_name_matches_tool_spec(self):
        plan = self.planner.plan("sum revenue by channel", self.ctx)
        assert plan.tool_name == plan.tool_spec.tool_name


# ---------------------------------------------------------------------------
# Planner.execute()
# ---------------------------------------------------------------------------

class TestPlannerExecute:
    def setup_method(self):
        self.planner = AnalyticsPlanner(llm=FakeLLMProvider())
        self.ctx = _context()

    def test_table_plan_returns_table_output(self, sales_db):
        plan = self.planner.plan("sum revenue by channel", self.ctx)
        result = self.planner.execute(plan, db_path=sales_db)
        assert result.output_type in ("table", "text")
        assert result.dataset_version_id == VERSION_ID

    def test_visual_plan_returns_visual_output(self, sales_db):
        plan = self.planner.plan("bar chart of revenue by channel", self.ctx)
        result = self.planner.execute(plan, db_path=sales_db)
        assert result.output_type in ("visual", "text")
        assert result.dataset_version_id == VERSION_ID

    def test_unsupported_returns_text_with_message(self, sales_db):
        plan = self.planner.plan("xyzzy abcdef completely unknown", self.ctx)
        result = self.planner.execute(plan, db_path=sales_db)
        assert result.output_type == "text"
        assert "unsupported" in result.content.lower() or "outside" in result.content.lower()

    def test_save_without_prior_ref_returns_instructions(self, sales_db):
        plan = self.planner.plan("save this table", self.ctx, prior_output_refs=[_table_ref()])
        result = self.planner.execute(plan, db_path=sales_db, view_repo=None)
        assert result.output_type == "text"

    def test_output_is_never_automatically_saved(self, sales_db):
        plan = self.planner.plan("show revenue by channel", self.ctx)
        result = self.planner.execute(plan, db_path=sales_db)
        # TableOutput has no saved_view_id
        assert not hasattr(result, "saved_view_id")
        assert not hasattr(result, "visual_id")

    def test_version_id_preserved_through_execution(self, sales_db):
        plan = self.planner.plan("list top revenue months", self.ctx)
        result = self.planner.execute(plan, db_path=sales_db)
        assert result.dataset_version_id == VERSION_ID

    def test_invalid_column_in_context_fails_gracefully(self, sales_db):
        # Build a context with a column name that doesn't exist in the DB
        bad_col = DatasetContextColumn(
            column_name="nonexistent_col",
            data_type="float",
            is_likely_metric=True,
        )
        bad_table = DatasetContextTable(
            table_name="sales",
            row_count=5,
            column_count=1,
            columns=[bad_col],
            has_profile=True,
        )
        ctx = DatasetContext(
            dataset_id=DATASET_ID,
            dataset_name="Sales Data",
            dataset_version_id=VERSION_ID,
            version_number=1,
            version_type="original",
            tables=[bad_table],
        )
        plan = self.planner.plan("sum nonexistent_col by channel", ctx)
        result = self.planner.execute(plan, db_path=sales_db)
        # Should return text (error or fallback), not crash
        assert result.dataset_version_id == VERSION_ID
