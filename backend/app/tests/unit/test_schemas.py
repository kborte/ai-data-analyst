"""Schema construction tests — deterministic, no external services required."""

from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.analysis_run import AnalysisRun
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
    AnalysisRunStatus,
    ApprovalStatus,
    ArtifactStatus,
    ChartType,
    CleaningOperationType,
    DatasetSourceRole,
    DatasetVersionType,
    DataSourceKind,
    DataType,
    DefaultDecision,
    ExecutionStatus,
    FeatureOperationType,
    ImpactLevel,
    InsightSeverity,
    IssueType,
    UploadedFileKind,
    UserDecision,
    WorkspaceRole,
)
from app.schemas.context_document import ContextDocument
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
from app.schemas.insights import Insight, InsightReport
from app.schemas.profile import ColumnProfile, DataProfile, DataQualityIssue, NumericSummary
from app.schemas.source import DataSource, UploadedFile
from app.schemas.user import User
from app.schemas.visualization import VisualizationSpec
from app.schemas.workspace import Workspace, WorkspaceMembership

NOW = datetime.now(tz=UTC)


def test_user_schema() -> None:
    user = User(
        user_id=uuid4(),
        email="analyst@example.com",
        display_name="Test Analyst",
        created_at=NOW,
    )
    assert user.display_name == "Test Analyst"


def test_workspace_schema() -> None:
    ws = Workspace(
        workspace_id=uuid4(),
        name="Q2 Analysis",
        created_by_user_id=uuid4(),
        created_at=NOW,
    )
    assert ws.name == "Q2 Analysis"
    assert ws.description is None


def test_workspace_membership_schema() -> None:
    m = WorkspaceMembership(
        membership_id=uuid4(),
        workspace_id=uuid4(),
        user_id=uuid4(),
        role=WorkspaceRole.editor,
        joined_at=NOW,
    )
    assert m.role == WorkspaceRole.editor


def test_data_source_schema() -> None:
    ds = DataSource(
        data_source_id=uuid4(),
        workspace_id=uuid4(),
        source_kind=DataSourceKind.uploaded_file,
        display_name="May Revenue CSV",
        created_by_user_id=uuid4(),
        created_at=NOW,
    )
    assert ds.source_kind == DataSourceKind.uploaded_file


def test_uploaded_file_schema() -> None:
    uf = UploadedFile(
        file_id=uuid4(),
        workspace_id=uuid4(),
        data_source_id=uuid4(),
        file_kind=UploadedFileKind.csv,
        original_filename="revenue_may.csv",
        storage_path="storage/uploads/workspaces/w1/sources/s1/original/f1__revenue_may.csv",
        size_bytes=204800,
        uploaded_by_user_id=uuid4(),
        uploaded_at=NOW,
    )
    assert uf.file_kind == UploadedFileKind.csv


def test_dataset_schema() -> None:
    d = Dataset(
        dataset_id=uuid4(),
        workspace_id=uuid4(),
        name="May Revenue Analysis",
        created_by_user_id=uuid4(),
        created_at=NOW,
    )
    assert d.name == "May Revenue Analysis"


def test_dataset_source_schema() -> None:
    ds = DatasetSource(
        dataset_source_id=uuid4(),
        dataset_id=uuid4(),
        data_source_id=uuid4(),
        role=DatasetSourceRole.primary,
    )
    assert ds.role == DatasetSourceRole.primary


def test_dataset_version_schema() -> None:
    v = DatasetVersion(
        dataset_version_id=uuid4(),
        dataset_id=uuid4(),
        parent_version_id=None,
        version_number=1,
        version_type=DatasetVersionType.original,
        display_name="Original upload",
        created_by_user_id=uuid4(),
        created_at=NOW,
    )
    assert v.version_number == 1
    assert v.parent_version_id is None
    assert v.metadata == {}


def test_dataset_version_multiple_cleaned_same_type() -> None:
    """Multiple versions may share version_type = cleaned."""
    dataset_id = uuid4()
    user_id = uuid4()
    v1_id = uuid4()
    v2_id = uuid4()

    v1 = DatasetVersion(
        dataset_version_id=v1_id,
        dataset_id=dataset_id,
        version_number=2,
        version_type=DatasetVersionType.cleaned,
        display_name="Removed duplicates",
        created_by_user_id=user_id,
        created_at=NOW,
    )
    v2 = DatasetVersion(
        dataset_version_id=v2_id,
        dataset_id=dataset_id,
        parent_version_id=v1_id,
        version_number=3,
        version_type=DatasetVersionType.cleaned,
        display_name="Standardized country labels",
        created_by_user_id=user_id,
        created_at=NOW,
    )
    assert v1.version_type == v2.version_type == DatasetVersionType.cleaned
    assert v1.version_number != v2.version_number


def test_dataset_table_schema() -> None:
    t = DatasetTable(
        table_id=uuid4(),
        dataset_version_id=uuid4(),
        table_name="sheet1",
    )
    assert t.table_name == "sheet1"


def test_context_document_schema() -> None:
    cd = ContextDocument(
        context_document_id=uuid4(),
        workspace_id=uuid4(),
        title="Company KPIs",
        storage_path="storage/uploads/workspaces/w1/context_documents/c1/raw.txt",
        created_by_user_id=uuid4(),
        created_at=NOW,
    )
    assert cd.title == "Company KPIs"


def _make_column_profile() -> ColumnProfile:
    return ColumnProfile(
        column_name="revenue",
        data_type=DataType.float_,
        total_count=1000,
        null_count=5,
        null_percent=0.5,
        unique_count=980,
        unique_percent=98.0,
        numeric_summary=NumericSummary(min=0.0, max=50000.0, mean=1200.0),
    )


def test_data_profile_schema() -> None:
    profile = DataProfile(
        profile_id=uuid4(),
        dataset_version_id=uuid4(),
        table_name="revenue_may",
        row_count=1000,
        column_count=8,
        column_profiles=[_make_column_profile()],
        quality_issues=[
            DataQualityIssue(
                issue_type=IssueType.missing_values,
                table_name="revenue_may",
                column_name="revenue",
                description="5 missing values in revenue column",
                affected_rows_count=5,
                affected_rows_percent=0.5,
                impact_level=ImpactLevel.low,
            )
        ],
        created_at=NOW,
    )
    assert profile.row_count == 1000
    assert len(profile.column_profiles) == 1
    assert len(profile.quality_issues) == 1


def _make_cleaning_step(step_id: None = None) -> CleaningStep:
    return CleaningStep(
        step_id=uuid4() if step_id is None else step_id,
        sequence_order=1,
        issue=CleaningIssue(
            issue_type=IssueType.missing_values,
            table_name="revenue_may",
            column_name="revenue",
            description="5 missing values",
            affected_rows_count=5,
            affected_rows_percent=0.5,
        ),
        recommendation=CleaningRecommendation(
            action_type="fill_missing",
            recommended_action="Fill with column median",
            rationale="Low impact, non-key column",
            impact_level=ImpactLevel.low,
            affects_key_metrics=False,
            requires_human_approval=False,
            default_decision=DefaultDecision.approve,
        ),
        operation=CleaningOperation(
            operation_type=CleaningOperationType.fill_missing,
            parameters={"strategy": "median"},
        ),
        preview=CleaningPreview(
            rows_before=1000,
            estimated_rows_after=1000,
            estimated_rows_removed=0,
            columns_changed=["revenue"],
        ),
    )


def test_cleaning_plan_schema() -> None:
    step = _make_cleaning_step()
    plan = CleaningPlan(
        cleaning_plan_id=uuid4(),
        dataset_version_id=uuid4(),
        status=ArtifactStatus.pending,
        plan_json=CleaningPlanJson(steps=[step]),
        created_at=NOW,
    )
    assert len(plan.plan_json.steps) == 1
    assert plan.plan_json.steps[0].sequence_order == 1


def test_cleaning_decisions_schema() -> None:
    step_id = uuid4()
    decisions = CleaningDecisions(
        cleaning_decisions_id=uuid4(),
        cleaning_plan_id=uuid4(),
        decided_by_user_id=uuid4(),
        decisions_json=CleaningDecisionsJson(
            decisions=[
                CleaningDecisionItem(
                    step_id=step_id,
                    decision=UserDecision.approve,
                )
            ]
        ),
        created_at=NOW,
    )
    assert decisions.decisions_json.decisions[0].decision == UserDecision.approve


def test_cleaning_result_schema() -> None:
    result = CleaningResult(
        cleaning_result_id=uuid4(),
        cleaning_plan_id=uuid4(),
        cleaning_decisions_id=uuid4(),
        input_dataset_version_id=uuid4(),
        status=ArtifactStatus.completed,
        row_count_before=1000,
        row_count_after=995,
        columns_changed=["revenue"],
        execution_log_json=CleaningExecutionLogJson(
            step_results=[
                CleaningStepResult(
                    step_id=uuid4(),
                    status=ExecutionStatus.success,
                    rows_affected=5,
                )
            ]
        ),
        created_at=NOW,
        approval_status=ApprovalStatus.approved,
    )
    assert result.row_count_after == 995
    assert result.approval_status == ApprovalStatus.approved


def test_feature_plan_schema() -> None:
    feature_id = uuid4()
    plan = FeaturePlan(
        feature_plan_id=uuid4(),
        dataset_version_id=uuid4(),
        status=ArtifactStatus.pending,
        plan_json=FeaturePlanJson(
            features=[
                FeatureDefinition(
                    feature_id=feature_id,
                    feature_name="running_revenue",
                    description="Cumulative sum of revenue ordered by date",
                    operation_type=FeatureOperationType.window,
                    formula_display="cumsum(revenue ORDER BY date)",
                    required_columns=["revenue", "date"],
                    sort_columns=["date"],
                )
            ]
        ),
        created_at=NOW,
    )
    assert plan.plan_json.features[0].feature_name == "running_revenue"


def test_feature_decisions_and_result_schema() -> None:
    feature_id = uuid4()
    feature_plan_id = uuid4()
    decisions = FeatureDecisions(
        feature_decisions_id=uuid4(),
        feature_plan_id=feature_plan_id,
        decided_by_user_id=uuid4(),
        decisions_json=FeatureDecisionsJson(
            decisions=[FeatureDecisionItem(feature_id=feature_id, decision=UserDecision.approve)]
        ),
        created_at=NOW,
    )
    result = FeatureResult(
        feature_result_id=uuid4(),
        feature_plan_id=feature_plan_id,
        feature_decisions_id=decisions.feature_decisions_id,
        input_dataset_version_id=uuid4(),
        status=ArtifactStatus.completed,
        features_added=["running_revenue"],
        execution_log_json=FeatureExecutionLogJson(),
        created_at=NOW,
    )
    assert result.features_added == ["running_revenue"]
    assert decisions.decisions_json.decisions[0].decision == UserDecision.approve


def test_visualization_spec_schema() -> None:
    spec = VisualizationSpec(
        visualization_id=uuid4(),
        dataset_version_id=uuid4(),
        chart_type=ChartType.line,
        title="Revenue Over Time",
        x_axis="date",
        y_axis="revenue",
        rationale="Shows revenue trend over the analysis period",
        created_at=NOW,
    )
    assert spec.chart_type == ChartType.line


def test_insight_report_schema() -> None:
    report = InsightReport(
        report_id=uuid4(),
        dataset_version_id=uuid4(),
        executive_summary="Revenue grew 12% MoM. Data quality issues may affect precision.",
        key_observations=["Revenue peaked mid-month", "High-value segment drives 60% of total"],
        insights=[
            Insight(
                insight_id=uuid4(),
                title="Mid-month revenue spike",
                observation="Revenue is consistently higher in the middle of each month",
                possible_explanations=["Billing cycles", "Campaign timing"],
                evidence=["Revenue on day 15 is 2x average"],
                caveats=["Only 3 months of data available"],
                severity=InsightSeverity.info,
                recommended_followups=["Confirm with 12 months of data"],
            )
        ],
        status=ArtifactStatus.completed,
        created_at=NOW,
    )
    assert len(report.insights) == 1
    assert report.insights[0].severity == InsightSeverity.info


def test_analysis_run_schema() -> None:
    run = AnalysisRun(
        analysis_run_id=uuid4(),
        workspace_id=uuid4(),
        dataset_id=uuid4(),
        input_dataset_version_id=uuid4(),
        name="May Revenue — Full Analysis",
        status=AnalysisRunStatus.created,
        created_by_user_id=uuid4(),
        created_at=NOW,
        updated_at=NOW,
    )
    assert run.status == AnalysisRunStatus.created
    assert run.artifact_refs == []
    assert run.final_dataset_version_id is None
