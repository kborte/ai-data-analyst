"""Unit tests for CleaningExecutionService (M5C)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from app.repositories.memory import (
    CleaningPlanRepository,
    CleaningResultRepository,
    DatasetTableRepository,
    DatasetVersionRepository,
)
from app.schemas.cleaning import (
    CleaningDecisionItem,
    CleaningDecisions,
    CleaningDecisionsJson,
    CleaningIssue,
    CleaningOperation,
    CleaningPlan,
    CleaningPlanJson,
    CleaningPreview,
    CleaningRecommendation,
    CleaningStep,
)
from app.schemas.common import (
    ArtifactStatus,
    CleaningOperationType,
    DatasetVersionType,
    DefaultDecision,
    ImpactLevel,
    IssueType,
    UserDecision,
)
from app.schemas.dataset import DatasetTable, DatasetVersion
from app.services.cleaning_execution_service import CleaningExecutionService

_WORKSPACE_ID = uuid.uuid4()
_DATASET_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _make_service() -> tuple[
    CleaningExecutionService,
    DatasetVersionRepository,
    DatasetTableRepository,
    CleaningPlanRepository,
    CleaningResultRepository,
]:
    version_repo = DatasetVersionRepository()
    table_repo = DatasetTableRepository()
    plan_repo = CleaningPlanRepository()
    result_repo = CleaningResultRepository()
    svc = CleaningExecutionService(version_repo, table_repo, plan_repo, result_repo)
    return svc, version_repo, table_repo, plan_repo, result_repo


def _make_step(
    op_type: CleaningOperationType,
    params: dict,
    table: str = "orders",
    requires_approval: bool = False,
    default_decision: DefaultDecision = DefaultDecision.approve,
) -> CleaningStep:
    return CleaningStep(
        step_id=uuid.uuid4(),
        sequence_order=1,
        issue=CleaningIssue(
            issue_type=IssueType.whitespace,
            table_name=table,
            description="test",
            affected_rows_count=1,
            affected_rows_percent=1.0,
        ),
        recommendation=CleaningRecommendation(
            action_type="test",
            recommended_action="test",
            rationale="test",
            impact_level=ImpactLevel.low,
            affects_key_metrics=False,
            requires_human_approval=requires_approval,
            default_decision=default_decision,
        ),
        operation=CleaningOperation(operation_type=op_type, parameters=params),
        preview=CleaningPreview(rows_before=3, estimated_rows_after=3, estimated_rows_removed=0),
    )


def _make_plan(steps: list[CleaningStep], version_id: uuid.UUID) -> CleaningPlan:
    return CleaningPlan(
        cleaning_plan_id=uuid.uuid4(),
        dataset_version_id=version_id,
        status=ArtifactStatus.completed,
        plan_json=CleaningPlanJson(steps=steps),
        created_at=_now(),
    )


def _make_version(version_id: uuid.UUID, version_number: int = 1) -> DatasetVersion:
    return DatasetVersion(
        dataset_version_id=version_id,
        dataset_id=_DATASET_ID,
        version_number=version_number,
        version_type=DatasetVersionType.original,
        created_by_user_id=_USER_ID,
        created_at=_now(),
    )


def _make_decisions(
    steps: list[CleaningStep], override: list[CleaningDecisionItem] | None = None
) -> CleaningDecisions:
    items = override or [
        CleaningDecisionItem(step_id=s.step_id, decision=UserDecision.approve) for s in steps
    ]
    return CleaningDecisions(
        cleaning_decisions_id=uuid.uuid4(),
        cleaning_plan_id=uuid.uuid4(),
        decided_by_user_id=_USER_ID,
        decisions_json=CleaningDecisionsJson(decisions=items),
        created_at=_now(),
    )


@pytest.fixture()
def csv_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, uuid.UUID]:
    monkeypatch.setattr("app.tools.files.storage.settings.LOCAL_STORAGE_DIR", str(tmp_path))
    version_id = uuid.uuid4()
    csv_path = tmp_path / "orders.csv"
    df = pd.DataFrame({"product": ["  Widget  ", "Gadget", "Doohickey"], "revenue": [100.0, 200.0, 300.0]})
    df.to_csv(csv_path, index=False)
    return csv_path, version_id


# ---------------------------------------------------------------------------
# 1. Approved plan creates new cleaned dataset version
# ---------------------------------------------------------------------------


def test_creates_cleaned_dataset_version(csv_table: tuple) -> None:
    csv_path, version_id = csv_table
    svc, version_repo, table_repo, plan_repo, _ = _make_service()

    version_repo.save(_make_version(version_id))
    table_repo.save(DatasetTable(
        table_id=uuid.uuid4(), dataset_version_id=version_id,
        table_name="orders", storage_path=str(csv_path),
    ))
    step = _make_step(CleaningOperationType.strip_whitespace, {"column": "product"})
    plan = _make_plan([step], version_id)
    plan_repo.save(plan)
    decisions = _make_decisions([step])

    result = svc.execute_cleaning_plan(
        _WORKSPACE_ID, _DATASET_ID, version_id, plan.cleaning_plan_id, decisions, _USER_ID
    )

    assert result.status == ArtifactStatus.completed
    assert result.output_dataset_version_id is not None
    out = version_repo.get(result.output_dataset_version_id)
    assert out is not None
    assert out.version_type == DatasetVersionType.cleaned


# ---------------------------------------------------------------------------
# 2. Original dataset version remains unchanged
# ---------------------------------------------------------------------------


def test_original_version_unchanged(csv_table: tuple) -> None:
    csv_path, version_id = csv_table
    svc, version_repo, table_repo, plan_repo, _ = _make_service()

    version_repo.save(_make_version(version_id))
    table_repo.save(DatasetTable(
        table_id=uuid.uuid4(), dataset_version_id=version_id,
        table_name="orders", storage_path=str(csv_path),
    ))
    step = _make_step(CleaningOperationType.strip_whitespace, {"column": "product"})
    plan = _make_plan([step], version_id)
    plan_repo.save(plan)

    result = svc.execute_cleaning_plan(
        _WORKSPACE_ID, _DATASET_ID, version_id, plan.cleaning_plan_id,
        _make_decisions([step]), _USER_ID,
    )

    # Original CSV is unchanged
    original_df = pd.read_csv(csv_path)
    assert original_df["product"].iloc[0] == "  Widget  "
    # Original version still in repo with same ID
    assert version_repo.get(version_id) is not None
    assert result.output_dataset_version_id != version_id


# ---------------------------------------------------------------------------
# 3. Output version parent points to input version
# ---------------------------------------------------------------------------


def test_output_version_parent(csv_table: tuple) -> None:
    csv_path, version_id = csv_table
    svc, version_repo, table_repo, plan_repo, _ = _make_service()
    version_repo.save(_make_version(version_id))
    table_repo.save(DatasetTable(
        table_id=uuid.uuid4(), dataset_version_id=version_id,
        table_name="orders", storage_path=str(csv_path),
    ))
    step = _make_step(CleaningOperationType.ignore_issue, {})
    plan = _make_plan([step], version_id)
    plan_repo.save(plan)

    result = svc.execute_cleaning_plan(
        _WORKSPACE_ID, _DATASET_ID, version_id, plan.cleaning_plan_id,
        _make_decisions([step]), _USER_ID,
    )

    out = version_repo.get(result.output_dataset_version_id)
    assert out.parent_version_id == version_id


# ---------------------------------------------------------------------------
# 4. Output version type is cleaned
# ---------------------------------------------------------------------------


def test_output_version_type_is_cleaned(csv_table: tuple) -> None:
    csv_path, version_id = csv_table
    svc, version_repo, table_repo, plan_repo, _ = _make_service()
    version_repo.save(_make_version(version_id))
    table_repo.save(DatasetTable(
        table_id=uuid.uuid4(), dataset_version_id=version_id,
        table_name="orders", storage_path=str(csv_path),
    ))
    step = _make_step(CleaningOperationType.ignore_issue, {})
    plan = _make_plan([step], version_id)
    plan_repo.save(plan)

    result = svc.execute_cleaning_plan(
        _WORKSPACE_ID, _DATASET_ID, version_id, plan.cleaning_plan_id,
        _make_decisions([step]), _USER_ID,
    )

    out = version_repo.get(result.output_dataset_version_id)
    assert out.version_type == DatasetVersionType.cleaned


# ---------------------------------------------------------------------------
# 5. Missing required approval blocks execution
# ---------------------------------------------------------------------------


def test_missing_approval_raises(csv_table: tuple) -> None:
    csv_path, version_id = csv_table
    svc, version_repo, table_repo, plan_repo, _ = _make_service()
    version_repo.save(_make_version(version_id))
    table_repo.save(DatasetTable(
        table_id=uuid.uuid4(), dataset_version_id=version_id,
        table_name="orders", storage_path=str(csv_path),
    ))
    step = _make_step(
        CleaningOperationType.drop_rows, {"column": "revenue"},
        requires_approval=True, default_decision=DefaultDecision.require_review,
    )
    plan = _make_plan([step], version_id)
    plan_repo.save(plan)
    # Pass no decisions — step requires approval
    decisions = _make_decisions([], override=[])

    with pytest.raises(ValueError, match="blocked"):
        svc.execute_cleaning_plan(
            _WORKSPACE_ID, _DATASET_ID, version_id, plan.cleaning_plan_id, decisions, _USER_ID
        )


# ---------------------------------------------------------------------------
# 6. Cleaning result is saved in repository
# ---------------------------------------------------------------------------


def test_cleaning_result_saved(csv_table: tuple) -> None:
    csv_path, version_id = csv_table
    svc, version_repo, table_repo, plan_repo, result_repo = _make_service()
    version_repo.save(_make_version(version_id))
    table_repo.save(DatasetTable(
        table_id=uuid.uuid4(), dataset_version_id=version_id,
        table_name="orders", storage_path=str(csv_path),
    ))
    step = _make_step(CleaningOperationType.ignore_issue, {})
    plan = _make_plan([step], version_id)
    plan_repo.save(plan)

    result = svc.execute_cleaning_plan(
        _WORKSPACE_ID, _DATASET_ID, version_id, plan.cleaning_plan_id,
        _make_decisions([step]), _USER_ID,
    )

    assert result_repo.get(result.cleaning_result_id) is not None


# ---------------------------------------------------------------------------
# 7. Execution log includes step results
# ---------------------------------------------------------------------------


def test_execution_log_has_step_results(csv_table: tuple) -> None:
    csv_path, version_id = csv_table
    svc, version_repo, table_repo, plan_repo, _ = _make_service()
    version_repo.save(_make_version(version_id))
    table_repo.save(DatasetTable(
        table_id=uuid.uuid4(), dataset_version_id=version_id,
        table_name="orders", storage_path=str(csv_path),
    ))
    step = _make_step(CleaningOperationType.strip_whitespace, {"column": "product"})
    plan = _make_plan([step], version_id)
    plan_repo.save(plan)

    result = svc.execute_cleaning_plan(
        _WORKSPACE_ID, _DATASET_ID, version_id, plan.cleaning_plan_id,
        _make_decisions([step]), _USER_ID,
    )

    log = result.execution_log_json
    assert len(log.step_results) == 1
    assert log.summary is not None
    assert log.summary.total_steps == 1


# ---------------------------------------------------------------------------
# 8. Version number increments correctly
# ---------------------------------------------------------------------------


def test_version_number_increments(csv_table: tuple) -> None:
    csv_path, version_id = csv_table
    svc, version_repo, table_repo, plan_repo, _ = _make_service()
    version_repo.save(_make_version(version_id, version_number=1))
    table_repo.save(DatasetTable(
        table_id=uuid.uuid4(), dataset_version_id=version_id,
        table_name="orders", storage_path=str(csv_path),
    ))
    step = _make_step(CleaningOperationType.ignore_issue, {})
    plan = _make_plan([step], version_id)
    plan_repo.save(plan)

    result = svc.execute_cleaning_plan(
        _WORKSPACE_ID, _DATASET_ID, version_id, plan.cleaning_plan_id,
        _make_decisions([step]), _USER_ID,
    )

    out = version_repo.get(result.output_dataset_version_id)
    assert out.version_number == 2


# ---------------------------------------------------------------------------
# 9. Cleaned table data is saved separately (file exists on disk)
# ---------------------------------------------------------------------------


def test_cleaned_table_saved_to_disk(csv_table: tuple, tmp_path: Path) -> None:
    csv_path, version_id = csv_table
    svc, version_repo, table_repo, plan_repo, _ = _make_service()
    version_repo.save(_make_version(version_id))
    table_repo.save(DatasetTable(
        table_id=uuid.uuid4(), dataset_version_id=version_id,
        table_name="orders", storage_path=str(csv_path),
    ))
    step = _make_step(CleaningOperationType.strip_whitespace, {"column": "product"})
    plan = _make_plan([step], version_id)
    plan_repo.save(plan)

    result = svc.execute_cleaning_plan(
        _WORKSPACE_ID, _DATASET_ID, version_id, plan.cleaning_plan_id,
        _make_decisions([step]), _USER_ID,
    )

    out_tables = table_repo.list_by_version(result.output_dataset_version_id)
    assert len(out_tables) == 1
    assert Path(out_tables[0].storage_path).exists()
    cleaned_df = pd.read_csv(out_tables[0].storage_path)
    assert cleaned_df["product"].iloc[0] == "Widget"


# ---------------------------------------------------------------------------
# 10. Failed execution does not create cleaned dataset version
# ---------------------------------------------------------------------------


def test_failed_step_no_output_version(csv_table: tuple) -> None:
    csv_path, version_id = csv_table
    svc, version_repo, table_repo, plan_repo, _ = _make_service()
    version_repo.save(_make_version(version_id))
    table_repo.save(DatasetTable(
        table_id=uuid.uuid4(), dataset_version_id=version_id,
        table_name="orders", storage_path=str(csv_path),
    ))
    # Use a non-existent table name in the step so executor records a failure
    step = _make_step(
        CleaningOperationType.drop_rows, {"column": "nonexistent_col"},
        table="nonexistent_table",
    )
    plan = _make_plan([step], version_id)
    plan_repo.save(plan)

    result = svc.execute_cleaning_plan(
        _WORKSPACE_ID, _DATASET_ID, version_id, plan.cleaning_plan_id,
        _make_decisions([step]), _USER_ID,
    )

    assert result.status == ArtifactStatus.failed
    assert result.output_dataset_version_id is None
