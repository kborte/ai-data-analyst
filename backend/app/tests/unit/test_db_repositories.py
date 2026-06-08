"""
M7C: Database repository tests using an in-memory SQLite database.

@compiles(JSONB, "sqlite") makes Base.metadata.create_all work; JSON
serialization is handled by SQLAlchemy's JSONB Python-level processor at
query time. FK constraints are unenforced (SQLite default), so parent
records need not be inserted when testing a single repository in isolation.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

import app.db.models  # noqa: F401 — register ORM models with Base.metadata
from app.db.base import Base
from app.repositories.database import (
    CleaningDecisionsRepository,
    CleaningPlanRepository,
    CleaningResultRepository,
    DataProfileRepository,
    DatasetRepository,
    DatasetSourceRepository,
    DatasetTableRepository,
    DatasetVersionRepository,
    DataSourceRepository,
    FeatureDecisionsRepository,
    FeaturePlanRepository,
    FeatureResultRepository,
)
from app.schemas.cleaning import (
    CleaningDecisionItem,
    CleaningDecisions,
    CleaningDecisionsJson,
    CleaningExecutionLogJson,
    CleaningIssue,
    CleaningOperation,
    CleaningPlan,
    CleaningPlanJson,
    CleaningPreview,
    CleaningRecommendation,
    CleaningResult,
    CleaningStep,
    CleaningStepResult,
)
from app.schemas.common import (
    ArtifactStatus,
    CleaningOperationType,
    DatasetSourceRole,
    DatasetVersionType,
    DataSourceKind,
    DataType,
    DefaultDecision,
    ExecutionStatus,
    FeatureOperationType,
    ImpactLevel,
    IssueType,
    UserDecision,
)
from app.schemas.dataset import Dataset, DatasetSource, DatasetTable, DatasetVersion
from app.schemas.features import (
    FeatureDecisionItem,
    FeatureDecisions,
    FeatureDecisionsJson,
    FeatureDefinition,
    FeatureExecutionLogJson,
    FeaturePlan,
    FeaturePlanJson,
    FeatureResult,
)
from app.schemas.profile import ColumnProfile, DataProfile, DataQualityIssue
from app.schemas.source import DataSource

NOW = datetime.now(tz=UTC)


@compiles(JSONB, "sqlite")
def _jsonb_to_text(element, compiler, **kw):
    return "TEXT"


@pytest.fixture(scope="module")
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    s = factory()
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Dataset + source + version + tables
# ---------------------------------------------------------------------------


def test_create_dataset_with_source_version_and_tables(session: Session) -> None:
    workspace_id = uuid4()
    user_id = uuid4()

    data_source = DataSource(
        data_source_id=uuid4(),
        workspace_id=workspace_id,
        source_kind=DataSourceKind.uploaded_file,
        display_name="Sales Q1",
        created_by_user_id=user_id,
        created_at=NOW,
    )
    DataSourceRepository(session).save(data_source)

    dataset = Dataset(
        dataset_id=uuid4(),
        workspace_id=workspace_id,
        name="Sales Q1 Dataset",
        created_by_user_id=user_id,
        created_at=NOW,
    )
    DatasetRepository(session).save(dataset)

    ds_source = DatasetSource(
        dataset_source_id=uuid4(),
        dataset_id=dataset.dataset_id,
        data_source_id=data_source.data_source_id,
        role=DatasetSourceRole.primary,
    )
    DatasetSourceRepository(session).save(ds_source)

    version = DatasetVersion(
        dataset_version_id=uuid4(),
        dataset_id=dataset.dataset_id,
        version_number=1,
        version_type=DatasetVersionType.original,
        display_name="Original upload",
        row_count=500,
        column_count=8,
        created_by_user_id=user_id,
        created_at=NOW,
    )
    DatasetVersionRepository(session).save(version)

    table1 = DatasetTable(
        table_id=uuid4(),
        dataset_version_id=version.dataset_version_id,
        table_name="sales",
        row_count=500,
        column_count=8,
    )
    table2 = DatasetTable(
        table_id=uuid4(),
        dataset_version_id=version.dataset_version_id,
        table_name="lookup",
        row_count=20,
        column_count=2,
    )
    tbl_repo = DatasetTableRepository(session)
    tbl_repo.save(table1)
    tbl_repo.save(table2)

    assert DatasetRepository(session).get(dataset.dataset_id) is not None
    assert DatasetVersionRepository(session).get(version.dataset_version_id) is not None
    tables = DatasetTableRepository(session).list_by_version(version.dataset_version_id)
    assert len(tables) == 2
    assert {t.table_name for t in tables} == {"sales", "lookup"}
    sources = DatasetSourceRepository(session).list_by_dataset(dataset.dataset_id)
    assert len(sources) == 1


# ---------------------------------------------------------------------------
# Data profile — JSON round-trip
# ---------------------------------------------------------------------------


def test_save_and_retrieve_data_profile(session: Session) -> None:
    vid = uuid4()
    col = ColumnProfile(
        column_name="revenue",
        data_type=DataType.float_,
        total_count=1000,
        null_count=5,
        null_percent=0.5,
        unique_count=850,
        unique_percent=85.0,
        is_likely_metric=True,
    )
    issue = DataQualityIssue(
        issue_type=IssueType.missing_values,
        table_name="sales",
        column_name="revenue",
        description="5 nulls in revenue",
        affected_rows_count=5,
        affected_rows_percent=0.5,
        impact_level=ImpactLevel.low,
    )
    profile = DataProfile(
        profile_id=uuid4(),
        dataset_version_id=vid,
        table_name="sales",
        row_count=1000,
        column_count=8,
        column_profiles=[col],
        quality_issues=[issue],
        likely_metric_columns=["revenue"],
        created_at=NOW,
    )
    DataProfileRepository(session).save(profile)
    got = DataProfileRepository(session).get(profile.profile_id)

    assert got is not None
    assert got.row_count == 1000
    assert len(got.column_profiles) == 1
    assert got.column_profiles[0].column_name == "revenue"
    assert got.column_profiles[0].is_likely_metric is True
    assert len(got.quality_issues) == 1
    assert got.quality_issues[0].issue_type == IssueType.missing_values
    assert got.likely_metric_columns == ["revenue"]


# ---------------------------------------------------------------------------
# Cleaning plan / decisions / result
# ---------------------------------------------------------------------------


def _make_cleaning_step() -> CleaningStep:
    return CleaningStep(
        step_id=uuid4(),
        sequence_order=1,
        issue=CleaningIssue(
            issue_type=IssueType.missing_values,
            table_name="sales",
            column_name="price",
            description="50 nulls",
            affected_rows_count=50,
            affected_rows_percent=5.0,
        ),
        recommendation=CleaningRecommendation(
            action_type="impute",
            recommended_action="Fill with median",
            rationale="Low impact",
            impact_level=ImpactLevel.low,
            affects_key_metrics=False,
            requires_human_approval=False,
            default_decision=DefaultDecision.approve,
        ),
        operation=CleaningOperation(
            operation_type=CleaningOperationType.fill_missing,
            parameters={"value": 0},
        ),
        preview=CleaningPreview(
            rows_before=1000,
            estimated_rows_after=1000,
            estimated_rows_removed=0,
            columns_changed=["price"],
        ),
    )


def test_save_and_retrieve_cleaning_plan(session: Session) -> None:
    vid = uuid4()
    step = _make_cleaning_step()
    plan = CleaningPlan(
        cleaning_plan_id=uuid4(),
        dataset_version_id=vid,
        status=ArtifactStatus.completed,
        plan_json=CleaningPlanJson(steps=[step]),
        created_at=NOW,
    )
    CleaningPlanRepository(session).save(plan)
    got = CleaningPlanRepository(session).get(plan.cleaning_plan_id)

    assert got is not None
    assert got.status == ArtifactStatus.completed
    assert len(got.plan_json.steps) == 1
    assert got.plan_json.steps[0].issue.column_name == "price"
    assert got.plan_json.steps[0].operation.parameters == {"value": 0}


def test_save_and_retrieve_cleaning_decisions(session: Session) -> None:
    plan_id = uuid4()
    step_id = uuid4()
    decisions = CleaningDecisions(
        cleaning_decisions_id=uuid4(),
        cleaning_plan_id=plan_id,
        decided_by_user_id=uuid4(),
        decisions_json=CleaningDecisionsJson(
            decisions=[
                CleaningDecisionItem(step_id=step_id, decision=UserDecision.approve)
            ]
        ),
        created_at=NOW,
    )
    CleaningDecisionsRepository(session).save(decisions)
    got = CleaningDecisionsRepository(session).get(decisions.cleaning_decisions_id)

    assert got is not None
    assert len(got.decisions_json.decisions) == 1
    assert got.decisions_json.decisions[0].step_id == step_id
    assert got.decisions_json.decisions[0].decision == UserDecision.approve

    listed = CleaningDecisionsRepository(session).list_by_plan(plan_id)
    assert any(d.cleaning_decisions_id == decisions.cleaning_decisions_id for d in listed)


def test_save_and_retrieve_cleaning_result(session: Session) -> None:
    plan_id = uuid4()
    decisions_id = uuid4()
    in_vid = uuid4()
    out_vid = uuid4()
    result = CleaningResult(
        cleaning_result_id=uuid4(),
        cleaning_plan_id=plan_id,
        cleaning_decisions_id=decisions_id,
        input_dataset_version_id=in_vid,
        output_dataset_version_id=out_vid,
        status=ArtifactStatus.completed,
        row_count_before=1000,
        row_count_after=995,
        columns_changed=["price"],
        execution_log_json=CleaningExecutionLogJson(
            step_results=[
                CleaningStepResult(step_id=uuid4(), status=ExecutionStatus.success, rows_affected=5)
            ]
        ),
        created_at=NOW,
    )
    CleaningResultRepository(session).save(result)
    got = CleaningResultRepository(session).get(result.cleaning_result_id)

    assert got is not None
    assert got.row_count_before == 1000
    assert got.row_count_after == 995
    assert got.columns_changed == ["price"]
    assert len(got.execution_log_json.step_results) == 1
    assert got.execution_log_json.step_results[0].status == ExecutionStatus.success


# ---------------------------------------------------------------------------
# Feature plan / decisions / result
# ---------------------------------------------------------------------------


def _make_feature_definition() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id=uuid4(),
        feature_name="revenue_per_unit",
        display_name="Revenue per Unit",
        description="Total revenue divided by units sold",
        operation_type=FeatureOperationType.ratio,
        formula_display="revenue / units_sold",
        required_columns=["revenue", "units_sold"],
    )


def test_save_and_retrieve_feature_plan(session: Session) -> None:
    vid = uuid4()
    feat = _make_feature_definition()
    plan = FeaturePlan(
        feature_plan_id=uuid4(),
        dataset_version_id=vid,
        status=ArtifactStatus.completed,
        plan_json=FeaturePlanJson(features=[feat]),
        created_at=NOW,
    )
    FeaturePlanRepository(session).save(plan)
    got = FeaturePlanRepository(session).get(plan.feature_plan_id)

    assert got is not None
    assert len(got.plan_json.features) == 1
    assert got.plan_json.features[0].feature_name == "revenue_per_unit"
    assert got.plan_json.features[0].required_columns == ["revenue", "units_sold"]


def test_save_and_retrieve_feature_decisions(session: Session) -> None:
    plan_id = uuid4()
    feat_id = uuid4()
    decisions = FeatureDecisions(
        feature_decisions_id=uuid4(),
        feature_plan_id=plan_id,
        decided_by_user_id=uuid4(),
        decisions_json=FeatureDecisionsJson(
            decisions=[
                FeatureDecisionItem(feature_id=feat_id, decision=UserDecision.approve)
            ]
        ),
        created_at=NOW,
    )
    FeatureDecisionsRepository(session).save(decisions)
    got = FeatureDecisionsRepository(session).get(decisions.feature_decisions_id)

    assert got is not None
    assert got.decisions_json.decisions[0].feature_id == feat_id
    assert got.decisions_json.decisions[0].decision == UserDecision.approve

    listed = FeatureDecisionsRepository(session).list_by_plan(plan_id)
    assert any(d.feature_decisions_id == decisions.feature_decisions_id for d in listed)


def test_save_and_retrieve_feature_result(session: Session) -> None:
    plan_id = uuid4()
    in_vid = uuid4()
    out_vid = uuid4()
    result = FeatureResult(
        feature_result_id=uuid4(),
        feature_plan_id=plan_id,
        feature_decisions_id=uuid4(),
        input_dataset_version_id=in_vid,
        output_dataset_version_id=out_vid,
        status=ArtifactStatus.completed,
        features_added=["revenue_per_unit"],
        execution_log_json=FeatureExecutionLogJson(
            feature_results=[{"feature": "revenue_per_unit", "rows": 1000}]
        ),
        created_at=NOW,
    )
    FeatureResultRepository(session).save(result)
    got = FeatureResultRepository(session).get(result.feature_result_id)

    assert got is not None
    assert got.features_added == ["revenue_per_unit"]
    assert got.execution_log_json.feature_results[0]["feature"] == "revenue_per_unit"
    assert got.execution_status == ExecutionStatus.success


# ---------------------------------------------------------------------------
# Dataset version parent/child relationship
# ---------------------------------------------------------------------------


def test_dataset_version_parent_child_relationship(session: Session) -> None:
    did = uuid4()
    user_id = uuid4()

    parent = DatasetVersion(
        dataset_version_id=uuid4(),
        dataset_id=did,
        version_number=1,
        version_type=DatasetVersionType.original,
        created_by_user_id=user_id,
        created_at=NOW,
    )
    child = DatasetVersion(
        dataset_version_id=uuid4(),
        dataset_id=did,
        parent_version_id=parent.dataset_version_id,
        version_number=2,
        version_type=DatasetVersionType.cleaned,
        created_by_user_id=user_id,
        created_at=NOW,
    )
    repo = DatasetVersionRepository(session)
    repo.save(parent)
    repo.save(child)

    got_parent = repo.get(parent.dataset_version_id)
    got_child = repo.get(child.dataset_version_id)

    assert got_parent is not None
    assert got_parent.parent_version_id is None
    assert got_child is not None
    assert got_child.parent_version_id == parent.dataset_version_id


# ---------------------------------------------------------------------------
# Version numbers preserved
# ---------------------------------------------------------------------------


def test_version_numbers_preserved(session: Session) -> None:
    did = uuid4()
    user_id = uuid4()
    repo = DatasetVersionRepository(session)

    versions = [
        DatasetVersion(
            dataset_version_id=uuid4(),
            dataset_id=did,
            version_number=n,
            version_type=DatasetVersionType.original if n == 1 else DatasetVersionType.cleaned,
            created_by_user_id=user_id,
            created_at=NOW,
        )
        for n in (1, 2, 3)
    ]
    for v in versions:
        repo.save(v)

    listed = repo.list_by_dataset(did)
    nums = {v.version_number for v in listed}
    assert nums == {1, 2, 3}


# ---------------------------------------------------------------------------
# JSON fields deep round-trip
# ---------------------------------------------------------------------------


def test_json_fields_round_trip(session: Session) -> None:
    nested_metadata = {
        "source_file": "sales_2024.csv",
        "tags": ["q1", "revenue"],
        "options": {"delimiter": ",", "header": True},
    }
    version = DatasetVersion(
        dataset_version_id=uuid4(),
        dataset_id=uuid4(),
        version_number=1,
        version_type=DatasetVersionType.original,
        metadata=nested_metadata,
        created_by_user_id=uuid4(),
        created_at=NOW,
    )
    DatasetVersionRepository(session).save(version)
    got = DatasetVersionRepository(session).get(version.dataset_version_id)

    assert got is not None
    assert got.metadata["source_file"] == "sales_2024.csv"
    assert got.metadata["tags"] == ["q1", "revenue"]
    assert got.metadata["options"]["delimiter"] == ","


# ---------------------------------------------------------------------------
# Missing returns None
# ---------------------------------------------------------------------------


def test_get_missing_returns_none(session: Session) -> None:
    assert DataSourceRepository(session).get(uuid4()) is None
    assert DatasetRepository(session).get(uuid4()) is None
    assert DatasetVersionRepository(session).get(uuid4()) is None
    assert DataProfileRepository(session).get(uuid4()) is None
    assert CleaningPlanRepository(session).get(uuid4()) is None
    assert FeaturePlanRepository(session).get(uuid4()) is None
