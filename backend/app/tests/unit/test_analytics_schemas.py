"""Tests for M12A analytics schemas and plan contracts."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.analytics import (
    AggregateTableSpec,
    AllowedAggregation,
    AnalyticsIntent,
    AnalyticsPlan,
    AnalyticsRequest,
    FilterOperator,
    FilterSpec,
    FilterTableSpec,
    GenerateVisualSpec,
    MessageRole,
    MetricSpec,
    MixedOutput,
    OutputType,
    PreviewTableSpec,
    PriorOutputRef,
    RecentMessage,
    SaveAsViewPayload,
    SaveAsVisualPayload,
    SaveTableResultSpec,
    SaveVisualResultSpec,
    SimpleJoinSpec,
    TableOutput,
    TextOutput,
    VisualOutput,
)

DATASET_ID = uuid.uuid4()
VERSION_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_output(**kw) -> TableOutput:
    defaults = dict(
        dataset_version_id=VERSION_ID,
        title="Revenue by month",
        columns=["month", "revenue"],
        preview_rows=[["Jan", 100]],
        row_count=1,
    )
    return TableOutput(**{**defaults, **kw})


def _visual_output(**kw) -> VisualOutput:
    defaults = dict(
        dataset_version_id=VERSION_ID,
        title="Revenue chart",
        chart_type="line",
    )
    return VisualOutput(**{**defaults, **kw})


def _text_output(**kw) -> TextOutput:
    defaults = dict(
        dataset_version_id=VERSION_ID,
        title="Answer",
        content="Revenue was highest in Q4.",
    )
    return TextOutput(**{**defaults, **kw})


def _prior_ref(output_type: OutputType = OutputType.table) -> PriorOutputRef:
    return PriorOutputRef(
        output_id=uuid.uuid4(),
        output_type=output_type,
        dataset_version_id=VERSION_ID,
    )


def _aggregate_spec() -> AggregateTableSpec:
    return AggregateTableSpec(
        table_name="sales",
        group_by=["month"],
        metrics=[MetricSpec(column="revenue", aggregation=AllowedAggregation.sum)],
    )


def _plan(tool_spec=None, intent=AnalyticsIntent.table_result) -> AnalyticsPlan:
    spec = tool_spec or _aggregate_spec()
    return AnalyticsPlan(
        intent=intent,
        question="What was total revenue by month?",
        dataset_id=DATASET_ID,
        dataset_version_id=VERSION_ID,
        reasoning_summary="Group sales by month and sum revenue.",
        tool_name=spec.tool_name,
        tool_spec=spec,
        expected_output_type=OutputType.table,
        suggested_title="Revenue by month",
    )


# ---------------------------------------------------------------------------
# Output type invariants
# ---------------------------------------------------------------------------

class TestTableOutput:
    def test_preserves_dataset_version_id(self):
        out = _table_output()
        assert out.dataset_version_id == VERSION_ID

    def test_can_save_as_view_always_true(self):
        out = _table_output()
        assert out.can_save_as_view is True

    def test_can_save_as_view_cannot_be_false(self):
        with pytest.raises(ValidationError):
            TableOutput(
                dataset_version_id=VERSION_ID,
                title="T",
                columns=[],
                preview_rows=[],
                row_count=0,
                can_save_as_view=False,  # type: ignore[arg-type]
            )

    def test_storage_fields_optional(self):
        out = _table_output()
        assert out.storage_path is None
        assert out.storage_backend is None


class TestVisualOutput:
    def test_preserves_dataset_version_id(self):
        out = _visual_output()
        assert out.dataset_version_id == VERSION_ID

    def test_can_save_to_visuals_always_true(self):
        out = _visual_output()
        assert out.can_save_to_visuals is True

    def test_can_save_to_visuals_cannot_be_false(self):
        with pytest.raises(ValidationError):
            VisualOutput(
                dataset_version_id=VERSION_ID,
                title="V",
                chart_type="bar",
                can_save_to_visuals=False,  # type: ignore[arg-type]
            )


class TestTextOutput:
    def test_preserves_dataset_version_id(self):
        out = _text_output()
        assert out.dataset_version_id == VERSION_ID

    def test_output_type_is_text(self):
        assert _text_output().output_type == "text"


class TestMixedOutput:
    def test_preserves_dataset_version_id(self):
        out = MixedOutput(
            dataset_version_id=VERSION_ID,
            title="Summary",
            summary="Here is the breakdown.",
            outputs=[_text_output(), _table_output()],
        )
        assert out.dataset_version_id == VERSION_ID

    def test_outputs_can_contain_table_and_visual(self):
        out = MixedOutput(
            dataset_version_id=VERSION_ID,
            title="Mixed",
            summary="Explanation plus chart.",
            outputs=[_text_output(), _visual_output()],
        )
        assert len(out.outputs) == 2

    def test_empty_outputs_allowed(self):
        out = MixedOutput(
            dataset_version_id=VERSION_ID,
            title="Empty",
            summary="Nothing yet.",
        )
        assert out.outputs == []


# ---------------------------------------------------------------------------
# Prior output reference
# ---------------------------------------------------------------------------

class TestPriorOutputRef:
    def test_table_ref(self):
        ref = _prior_ref(OutputType.table)
        assert ref.output_type == OutputType.table

    def test_visual_ref(self):
        ref = _prior_ref(OutputType.visual)
        assert ref.output_type == OutputType.visual

    def test_preserves_dataset_version_id(self):
        v = uuid.uuid4()
        ref = PriorOutputRef(
            output_id=uuid.uuid4(),
            output_type=OutputType.table,
            dataset_version_id=v,
        )
        assert ref.dataset_version_id == v

    def test_optional_storage_fields(self):
        ref = _prior_ref()
        assert ref.storage_path is None
        assert ref.chart_spec_json == {}


# ---------------------------------------------------------------------------
# Recent messages
# ---------------------------------------------------------------------------

class TestRecentMessage:
    def test_user_role_accepted(self):
        msg = RecentMessage(role=MessageRole.user, content="Show revenue by month.")
        assert msg.role == MessageRole.user

    def test_assistant_role_accepted(self):
        msg = RecentMessage(role=MessageRole.assistant, content="Here is the table.")
        assert msg.role == MessageRole.assistant

    def test_output_refs_optional(self):
        msg = RecentMessage(role=MessageRole.user, content="ok")
        assert msg.output_refs == []

    def test_message_carries_output_refs(self):
        ref = _prior_ref(OutputType.visual)
        msg = RecentMessage(
            role=MessageRole.assistant,
            content="Here is your chart.",
            output_refs=[ref],
        )
        assert len(msg.output_refs) == 1
        assert msg.output_refs[0].output_type == OutputType.visual

    def test_recent_message_has_no_persistence_field(self):
        msg = RecentMessage(role=MessageRole.user, content="hello")
        assert not hasattr(msg, "id")
        assert not hasattr(msg, "created_at")
        assert not hasattr(msg, "conversation_id")


# ---------------------------------------------------------------------------
# Analytics request
# ---------------------------------------------------------------------------

class TestAnalyticsRequest:
    def test_minimal_request(self):
        req = AnalyticsRequest(
            question="What was total revenue last month?",
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
        )
        assert req.recent_messages == []
        assert req.prior_output_refs == []

    def test_accepts_recent_messages(self):
        req = AnalyticsRequest(
            question="Now show as a chart.",
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            recent_messages=[
                RecentMessage(role=MessageRole.user, content="Show revenue by month.")
            ],
        )
        assert len(req.recent_messages) == 1

    def test_accepts_prior_output_refs(self):
        req = AnalyticsRequest(
            question="Save this table.",
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            prior_output_refs=[_prior_ref(OutputType.table)],
        )
        assert len(req.prior_output_refs) == 1

    def test_question_required(self):
        with pytest.raises(ValidationError):
            AnalyticsRequest(dataset_id=DATASET_ID, dataset_version_id=VERSION_ID)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Tool specs — no raw SQL anywhere
# ---------------------------------------------------------------------------

class TestToolSpecs:
    def test_preview_table_spec(self):
        spec = PreviewTableSpec(table_name="sales")
        assert spec.tool_name == "preview_table"
        assert not hasattr(spec, "sql")
        assert not hasattr(spec, "raw_sql")
        assert not hasattr(spec, "query")

    def test_aggregate_table_spec(self):
        spec = _aggregate_spec()
        assert spec.tool_name == "aggregate_table"
        assert not hasattr(spec, "sql")
        assert spec.metrics[0].aggregation == AllowedAggregation.sum

    def test_aggregate_only_allows_declared_aggregations(self):
        with pytest.raises(ValidationError):
            MetricSpec(column="revenue", aggregation="arbitrary_func")  # type: ignore[arg-type]

    def test_filter_table_spec(self):
        spec = FilterTableSpec(
            table_name="sales",
            filters=[FilterSpec(column="revenue", operator=FilterOperator.gt, value=100)],
        )
        assert spec.tool_name == "filter_table"
        assert not hasattr(spec, "sql")

    def test_simple_join_spec(self):
        spec = SimpleJoinSpec(
            left_table="orders",
            right_table="customers",
            join_key_left="customer_id",
            join_key_right="id",
            output_columns=["order_id", "name", "total"],
        )
        assert spec.tool_name == "simple_join"
        assert not hasattr(spec, "sql")

    def test_generate_visual_spec(self):
        spec = GenerateVisualSpec(
            table_name="sales",
            chart_type="line",
            x_column="month",
            y_column="revenue",
        )
        assert spec.tool_name == "generate_visual"
        assert not hasattr(spec, "sql")

    def test_save_table_result_spec(self):
        spec = SaveTableResultSpec(output_id=uuid.uuid4(), name="Revenue View")
        assert spec.tool_name == "save_table_result"

    def test_save_visual_result_spec(self):
        spec = SaveVisualResultSpec(output_id=uuid.uuid4(), title="Revenue Chart")
        assert spec.tool_name == "save_visual_result"


# ---------------------------------------------------------------------------
# Analytics plan
# ---------------------------------------------------------------------------

class TestAnalyticsPlan:
    def test_valid_plan(self):
        plan = _plan()
        assert plan.intent == AnalyticsIntent.table_result
        assert plan.dataset_version_id == VERSION_ID

    def test_preserves_dataset_version_id(self):
        v = uuid.uuid4()
        plan = AnalyticsPlan(
            intent=AnalyticsIntent.text_answer,
            question="What was Q4 revenue?",
            dataset_id=DATASET_ID,
            dataset_version_id=v,
            reasoning_summary="Direct answer.",
            tool_name="preview_table",
            tool_spec=PreviewTableSpec(table_name="sales"),
            expected_output_type=OutputType.text,
            suggested_title="Q4 Revenue",
        )
        assert plan.dataset_version_id == v

    def test_invalid_intent_rejected(self):
        with pytest.raises(ValidationError):
            AnalyticsPlan(
                intent="drop_table",  # type: ignore[arg-type]
                dataset_id=DATASET_ID,
                dataset_version_id=VERSION_ID,
                reasoning_summary="bad",
                tool_name="preview_table",
                tool_spec=PreviewTableSpec(table_name="sales"),
                expected_output_type=OutputType.text,
                suggested_title="Bad",
            )

    def test_plan_does_not_have_sql_field(self):
        plan = _plan()
        assert not hasattr(plan, "sql")
        assert not hasattr(plan, "raw_sql")

    def test_unsupported_intent_allowed(self):
        plan = _plan(intent=AnalyticsIntent.unsupported)
        assert plan.intent == AnalyticsIntent.unsupported

    def test_prior_output_ref_optional(self):
        plan = _plan()
        assert plan.prior_output_ref is None

    def test_prior_output_ref_accepted(self):
        plan = _plan()
        plan2 = plan.model_copy(update={"prior_output_ref": _prior_ref(OutputType.visual)})
        assert plan2.prior_output_ref is not None
        assert plan2.prior_output_ref.output_type == OutputType.visual


# ---------------------------------------------------------------------------
# Explicit save payloads
# ---------------------------------------------------------------------------

class TestSavePayloads:
    def test_save_as_view_payload(self):
        payload = SaveAsViewPayload(
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            name="Revenue View",
            output_id=uuid.uuid4(),
        )
        assert payload.dataset_version_id == VERSION_ID

    def test_save_as_visual_payload(self):
        payload = SaveAsVisualPayload(
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            title="Revenue Chart",
            output_id=uuid.uuid4(),
        )
        assert payload.dataset_version_id == VERSION_ID

    def test_save_view_requires_name(self):
        with pytest.raises(ValidationError):
            SaveAsViewPayload(
                dataset_id=DATASET_ID,
                dataset_version_id=VERSION_ID,
                output_id=uuid.uuid4(),
            )  # type: ignore[call-arg]

    def test_save_visual_requires_title(self):
        with pytest.raises(ValidationError):
            SaveAsVisualPayload(
                dataset_id=DATASET_ID,
                dataset_version_id=VERSION_ID,
                output_id=uuid.uuid4(),
            )  # type: ignore[call-arg]
