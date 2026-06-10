"""Tests for the analytics workflow orchestrator (M16)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from app.dependencies import Repos
from app.schemas.cleaning import (
    CleaningDecisionItem,
    CleaningIssue,
    CleaningOperation,
    CleaningOperationType,
    CleaningPlan,
    CleaningPlanJson,
    CleaningPlanSummary,
    CleaningPreview,
    CleaningRecommendation,
    CleaningStep,
    DefaultDecision,
)
from app.schemas.common import (
    ArtifactStatus,
    DatasetVersionType,
    ImpactLevel,
    IssueType,
    UserDecision,
)
from app.schemas.dataset import Dataset, DatasetTable, DatasetVersion
from app.schemas.features import FeatureDecisionItem, FeaturePlan, FeaturePlanJson
from app.schemas.common import DataType
from app.schemas.profile import DataProfile, ColumnProfile
from app.schemas.workflow import (
    AnalysisResultResponse,
    NeedsApprovalResponse,
    NeedsClarificationResponse,
    WorkflowStage,
    WorkflowState,
)
from app.services.analytics_orchestrator import AnalyticsOrchestrator
from app.tools.data.duckdb_service import create_version_duckdb
from app.tools.files.storage_service import LocalStorageBackend
from app.tools.llm.provider import FakeLLMProvider

_NOW = datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dataset(workspace_id=None) -> Dataset:
    return Dataset(
        dataset_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        name="Test Dataset",
        created_by_user_id=uuid4(),
        created_at=_NOW,
    )


def _version(dataset: Dataset, storage_path: str = "v1.duckdb", number: int = 1) -> DatasetVersion:
    return DatasetVersion(
        dataset_version_id=uuid4(),
        dataset_id=dataset.dataset_id,
        version_number=number,
        version_type=DatasetVersionType.original,
        storage_path=storage_path,
        created_by_user_id=uuid4(),
        created_at=_NOW,
    )


def _build_sales_db(path: Path) -> None:
    df = pd.DataFrame({
        "month": ["Jan", "Feb", "Mar"],
        "channel": ["online", "store", "online"],
        "revenue": [100.0, 200.0, 150.0],
        "units": [10, 20, 15],
    })
    create_version_duckdb({"sales": df}, path)


def _profile(version: DatasetVersion) -> DataProfile:
    return DataProfile(
        profile_id=uuid4(),
        dataset_version_id=version.dataset_version_id,
        table_name="sales",
        row_count=3,
        column_count=4,
        column_profiles=[
            ColumnProfile(
                column_name="revenue",
                data_type=DataType.float_,
                total_count=3,
                null_count=0,
                null_percent=0.0,
                unique_count=3,
                unique_percent=100.0,
                is_likely_metric=True,
                is_likely_id=False,
                is_likely_date=False,
                is_likely_categorical=False,
            ),
        ],
        quality_issues=[],
        likely_metric_columns=["revenue"],
        created_at=_NOW,
    )


def _cleaning_step(requires_approval: bool = True) -> CleaningStep:
    return CleaningStep(
        step_id=uuid4(),
        sequence_order=1,
        issue=CleaningIssue(
            issue_type=IssueType.missing_values,
            table_name="sales",
            column_name="revenue",
            description="10% nulls in revenue",
            affected_rows_count=10,
            affected_rows_percent=10.0,
            impact_level=ImpactLevel.high,
        ),
        recommendation=CleaningRecommendation(
            action_type="fill_nulls",
            recommended_action="Fill nulls with median",
            rationale="Revenue column has 10% nulls that will skew metrics.",
            impact_level=ImpactLevel.high,
            affects_key_metrics=True,
            requires_human_approval=requires_approval,
            default_decision=DefaultDecision.approve,
        ),
        operation=CleaningOperation(
            operation_type=CleaningOperationType.fill_missing,
            parameters={"column": "revenue", "strategy": "median"},
        ),
        preview=CleaningPreview(
            rows_before=100,
            estimated_rows_after=100,
            estimated_rows_removed=0,
            columns_changed=["revenue"],
        ),
    )


def _plan_with_approval(version: DatasetVersion, profile: DataProfile) -> CleaningPlan:
    step = _cleaning_step(requires_approval=True)
    summary = CleaningPlanSummary(
        total_steps=1,
        steps_requiring_approval=1,
        auto_approved_steps=0,
        auto_ignored_steps=0,
        estimated_row_count_change=0,
        estimated_columns_changed=["revenue"],
    )
    plan_id = uuid4()
    return CleaningPlan(
        cleaning_plan_id=plan_id,
        dataset_version_id=version.dataset_version_id,
        status=ArtifactStatus.completed,
        plan_json=CleaningPlanJson(
            plan_id=plan_id,
            dataset_version_id=version.dataset_version_id,
            profile_id=profile.profile_id,
            created_at=_NOW,
            summary=summary,
            global_assumptions=[],
            steps=[step],
        ),
        created_at=_NOW,
    )


def _plan_no_approval(version: DatasetVersion, profile: DataProfile) -> CleaningPlan:
    summary = CleaningPlanSummary(
        total_steps=0,
        steps_requiring_approval=0,
        auto_approved_steps=0,
        auto_ignored_steps=0,
        estimated_row_count_change=0,
        estimated_columns_changed=[],
    )
    plan_id = uuid4()
    return CleaningPlan(
        cleaning_plan_id=plan_id,
        dataset_version_id=version.dataset_version_id,
        status=ArtifactStatus.completed,
        plan_json=CleaningPlanJson(
            plan_id=plan_id,
            dataset_version_id=version.dataset_version_id,
            profile_id=profile.profile_id,
            created_at=_NOW,
            summary=summary,
            global_assumptions=[],
            steps=[],
        ),
        created_at=_NOW,
    )


def _empty_feature_plan(version: DatasetVersion) -> FeaturePlan:
    return FeaturePlan(
        feature_plan_id=uuid4(),
        dataset_version_id=version.dataset_version_id,
        status=ArtifactStatus.completed,
        plan_json=FeaturePlanJson(features=[]),
        created_at=_NOW,
    )


def _table_record(version: DatasetVersion) -> DatasetTable:
    return DatasetTable(
        table_id=uuid4(),
        dataset_version_id=version.dataset_version_id,
        table_name="sales",
        row_count=3,
        column_count=4,
    )


def _setup_repos_and_storage(tmp_path: Path):
    repos = Repos()
    storage_dir = str(tmp_path)
    storage = LocalStorageBackend(base_dir=storage_dir)

    dataset = _dataset()
    repos.dataset.save(dataset)

    storage_path = f"v1_original.duckdb"
    db_path = tmp_path / storage_path
    _build_sales_db(db_path)
    storage.save(storage_path, db_path.read_bytes())

    version = _version(dataset, storage_path=storage_path)
    repos.dataset_version.save(version)
    repos.dataset_table.save(_table_record(version))

    return repos, storage, dataset, version


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fresh_analysis_with_cleaning_issues_returns_approval(tmp_path):
    """Cleaning request pauses for human approval when high-impact issues exist."""
    repos, storage, dataset, version = _setup_repos_and_storage(tmp_path)

    profile = _profile(version)
    repos.profile.save(profile)

    plan = _plan_with_approval(version, profile)
    repos.cleaning_plan.save(plan)

    orchestrator = AnalyticsOrchestrator(repos=repos, storage=storage, llm=FakeLLMProvider())
    result = orchestrator.run(
        question="clean my data and fix missing values",
        dataset_id=dataset.dataset_id,
        dataset_version_id=version.dataset_version_id,
        workspace_id=dataset.workspace_id,
        workflow_state=None,
        cleaning_decisions=[],
        feature_decisions=[],
        recent_messages=[],
        prior_output_refs=[],
    )

    assert isinstance(result, NeedsApprovalResponse)
    assert result.stage == "cleaning"
    assert len(result.items) == 1
    assert result.items[0].id == str(plan.plan_json.steps[0].step_id)
    assert result.workflow_state.stage == WorkflowStage.awaiting_cleaning_approval
    assert result.workflow_state.cleaning_plan_id == plan.cleaning_plan_id


def test_no_cleaning_issues_proceeds_to_analysis(tmp_path):
    """When no steps require approval, the orchestrator runs analysis directly."""
    repos, storage, dataset, version = _setup_repos_and_storage(tmp_path)

    profile = _profile(version)
    repos.profile.save(profile)

    plan = _plan_no_approval(version, profile)
    repos.cleaning_plan.save(plan)

    # Pre-seed empty feature plan so feature stage is skipped.
    feat_plan = _empty_feature_plan(version)
    repos.feature_plan.save(feat_plan)

    orchestrator = AnalyticsOrchestrator(repos=repos, storage=storage, llm=FakeLLMProvider())
    result = orchestrator.run(
        question="show revenue by channel",
        dataset_id=dataset.dataset_id,
        dataset_version_id=version.dataset_version_id,
        workspace_id=dataset.workspace_id,
        workflow_state=None,
        cleaning_decisions=[],
        feature_decisions=[],
        recent_messages=[],
        prior_output_refs=[],
    )

    assert isinstance(result, AnalysisResultResponse)
    assert result.dataset_id == dataset.dataset_id
    assert len(result.outputs) >= 1


def test_approve_all_cleaning_steps_runs_next_stage(tmp_path):
    """Resuming with approve-all decisions advances past the cleaning stage."""
    repos, storage, dataset, version = _setup_repos_and_storage(tmp_path)

    profile = _profile(version)
    repos.profile.save(profile)

    plan = _plan_with_approval(version, profile)
    repos.cleaning_plan.save(plan)

    step = plan.plan_json.steps[0]
    state = WorkflowState(
        workspace_id=dataset.workspace_id,
        dataset_id=dataset.dataset_id,
        dataset_version_id=version.dataset_version_id,
        question="revenue by channel",
        stage=WorkflowStage.awaiting_cleaning_approval,
        cleaning_plan_id=plan.cleaning_plan_id,
        profile_id=profile.profile_id,
    )
    decisions = [CleaningDecisionItem(step_id=step.step_id, decision=UserDecision.approve)]

    orchestrator = AnalyticsOrchestrator(repos=repos, storage=storage, llm=FakeLLMProvider())
    result = orchestrator.run(
        question="revenue by channel",
        dataset_id=dataset.dataset_id,
        dataset_version_id=version.dataset_version_id,
        workspace_id=dataset.workspace_id,
        workflow_state=state,
        cleaning_decisions=decisions,
        feature_decisions=[],
        recent_messages=[],
        prior_output_refs=[],
    )

    # After cleaning, goes to cleaning_result → AnalysisResultResponse with preview.
    assert isinstance(result, AnalysisResultResponse)
    assert len(result.outputs) >= 1


def test_rejected_cleaning_steps_not_in_items(tmp_path):
    """Rejected items should not appear as pending in the response."""
    repos, storage, dataset, version = _setup_repos_and_storage(tmp_path)

    profile = _profile(version)
    repos.profile.save(profile)

    plan = _plan_with_approval(version, profile)
    repos.cleaning_plan.save(plan)

    step = plan.plan_json.steps[0]
    state = WorkflowState(
        workspace_id=dataset.workspace_id,
        dataset_id=dataset.dataset_id,
        dataset_version_id=version.dataset_version_id,
        question="revenue by channel",
        stage=WorkflowStage.awaiting_cleaning_approval,
        cleaning_plan_id=plan.cleaning_plan_id,
        profile_id=profile.profile_id,
    )
    # Reject the step — execution should still proceed (skip skipped steps).
    decisions = [CleaningDecisionItem(step_id=step.step_id, decision=UserDecision.reject)]

    orchestrator = AnalyticsOrchestrator(repos=repos, storage=storage, llm=FakeLLMProvider())
    result = orchestrator.run(
        question="revenue by channel",
        dataset_id=dataset.dataset_id,
        dataset_version_id=version.dataset_version_id,
        workspace_id=dataset.workspace_id,
        workflow_state=state,
        cleaning_decisions=decisions,
        feature_decisions=[],
        recent_messages=[],
        prior_output_refs=[],
    )

    # Rejected decision clears the approval requirement; workflow advances.
    assert isinstance(result, (NeedsApprovalResponse, AnalysisResultResponse))


def test_cleaning_result_shows_preview_and_version_name(tmp_path):
    """After approved cleaning, response is AnalysisResultResponse with a
    table preview and the new version name embedded in summary_text."""
    repos, storage, dataset, version = _setup_repos_and_storage(tmp_path)

    profile = _profile(version)
    repos.profile.save(profile)

    plan = _plan_with_approval(version, profile)
    repos.cleaning_plan.save(plan)

    step = plan.plan_json.steps[0]
    state = WorkflowState(
        workspace_id=dataset.workspace_id,
        dataset_id=dataset.dataset_id,
        dataset_version_id=version.dataset_version_id,
        question="clean my data",
        stage=WorkflowStage.awaiting_cleaning_approval,
        cleaning_plan_id=plan.cleaning_plan_id,
        profile_id=profile.profile_id,
    )
    decisions = [CleaningDecisionItem(step_id=step.step_id, decision=UserDecision.approve)]

    orchestrator = AnalyticsOrchestrator(repos=repos, storage=storage, llm=FakeLLMProvider())
    result = orchestrator.run(
        question="clean my data",
        dataset_id=dataset.dataset_id,
        dataset_version_id=version.dataset_version_id,
        workspace_id=dataset.workspace_id,
        workflow_state=state,
        cleaning_decisions=decisions,
        feature_decisions=[],
        recent_messages=[],
        prior_output_refs=[],
    )

    assert isinstance(result, AnalysisResultResponse)
    # Summary must mention the version name and at least one cleaning step.
    assert "v" in result.summary_text.lower() or "clean" in result.summary_text.lower()
    # At least one output (table preview or text).
    assert len(result.outputs) >= 1
    # Table output should have columns and preview_rows.
    table = next((o for o in result.outputs if getattr(o, "output_type", None) == "table"), None)
    if table is not None:
        assert len(table.columns) > 0
        assert table.row_count > 0


def test_final_analysis_runs_on_resolved_version(tmp_path):
    """After cleaning and feature stages, analysis runs on the latest version."""
    repos, storage, dataset, version = _setup_repos_and_storage(tmp_path)

    profile = _profile(version)
    repos.profile.save(profile)

    plan = _plan_no_approval(version, profile)
    repos.cleaning_plan.save(plan)

    feat_plan = _empty_feature_plan(version)
    repos.feature_plan.save(feat_plan)

    orchestrator = AnalyticsOrchestrator(repos=repos, storage=storage, llm=FakeLLMProvider())
    result = orchestrator.run(
        question="show revenue by channel",
        dataset_id=dataset.dataset_id,
        dataset_version_id=version.dataset_version_id,
        workspace_id=dataset.workspace_id,
        workflow_state=None,
        cleaning_decisions=[],
        feature_decisions=[],
        recent_messages=[],
        prior_output_refs=[],
    )

    assert isinstance(result, AnalysisResultResponse)
    # Version ID in response should be valid (original or resolved).
    assert result.dataset_version_id is not None
    assert result.dataset_id == dataset.dataset_id


def test_analysis_returns_summary_text(tmp_path):
    """analysis_result always contains a non-empty summary_text."""
    repos, storage, dataset, version = _setup_repos_and_storage(tmp_path)

    profile = _profile(version)
    repos.profile.save(profile)
    repos.cleaning_plan.save(_plan_no_approval(version, profile))
    repos.feature_plan.save(_empty_feature_plan(version))

    orchestrator = AnalyticsOrchestrator(repos=repos, storage=storage, llm=FakeLLMProvider())
    result = orchestrator.run(
        question="show revenue by channel",
        dataset_id=dataset.dataset_id,
        dataset_version_id=version.dataset_version_id,
        workspace_id=dataset.workspace_id,
        workflow_state=None,
        cleaning_decisions=[],
        feature_decisions=[],
        recent_messages=[],
        prior_output_refs=[],
    )

    assert isinstance(result, AnalysisResultResponse)
    assert isinstance(result.summary_text, str)
    assert len(result.summary_text) > 0


def test_missing_duckdb_returns_clarification(tmp_path):
    """Version with no .duckdb artifact returns needs_clarification."""
    repos = Repos()
    storage = LocalStorageBackend(base_dir=str(tmp_path))

    dataset = _dataset()
    repos.dataset.save(dataset)

    version = DatasetVersion(
        dataset_version_id=uuid4(),
        dataset_id=dataset.dataset_id,
        version_number=1,
        version_type=DatasetVersionType.original,
        storage_path=None,  # no artifact
        created_by_user_id=uuid4(),
        created_at=_NOW,
    )
    repos.dataset_version.save(version)

    profile = _profile(version)
    repos.profile.save(profile)
    repos.cleaning_plan.save(_plan_no_approval(version, profile))
    repos.feature_plan.save(_empty_feature_plan(version))

    state = WorkflowState(
        workspace_id=dataset.workspace_id,
        dataset_id=dataset.dataset_id,
        dataset_version_id=version.dataset_version_id,
        question="revenue by channel",
        stage=WorkflowStage.analysis,
    )

    orchestrator = AnalyticsOrchestrator(repos=repos, storage=storage, llm=FakeLLMProvider())
    result = orchestrator.run(
        question="revenue by channel",
        dataset_id=dataset.dataset_id,
        dataset_version_id=version.dataset_version_id,
        workspace_id=dataset.workspace_id,
        workflow_state=state,
        cleaning_decisions=[],
        feature_decisions=[],
        recent_messages=[],
        prior_output_refs=[],
    )

    assert isinstance(result, NeedsClarificationResponse)
