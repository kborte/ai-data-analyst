"""Unit tests for CleaningExecutionService (M9+: DuckDB-based architecture)."""

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
from app.tools.data.duckdb_service import create_version_duckdb, list_tables, read_preview, temp_duckdb_path
from app.tools.files.storage_service import LocalStorageBackend, version_path

_WORKSPACE_ID = uuid.uuid4()
_DATASET_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _make_service(
    storage: LocalStorageBackend,
) -> tuple[
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
    svc = CleaningExecutionService(version_repo, table_repo, plan_repo, result_repo, storage)
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


def _make_version(version_id: uuid.UUID, storage_path: str, version_number: int = 1) -> DatasetVersion:
    return DatasetVersion(
        dataset_version_id=version_id,
        dataset_id=_DATASET_ID,
        version_number=version_number,
        version_type=DatasetVersionType.original,
        storage_path=storage_path,
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
def duckdb_ctx(tmp_path: Path):
    """Create a LocalStorageBackend with a seeded DuckDB artifact for 'orders' table."""
    storage = LocalStorageBackend(str(tmp_path / "storage"))
    version_id = uuid.uuid4()
    df = pd.DataFrame({
        "product": ["  Widget  ", "Gadget", "Doohickey"],
        "revenue": [100.0, 200.0, 300.0],
    })
    path = version_path(_WORKSPACE_ID, _DATASET_ID, 1, "original")
    with temp_duckdb_path() as tmp_db:
        create_version_duckdb({"orders": df}, tmp_db)
        storage.save(path, tmp_db.read_bytes())
    return storage, version_id, path


# ---------------------------------------------------------------------------
# 1. Approved plan creates new cleaned dataset version
# ---------------------------------------------------------------------------

def test_creates_cleaned_dataset_version(duckdb_ctx) -> None:
    storage, version_id, storage_path = duckdb_ctx
    svc, version_repo, table_repo, plan_repo, _ = _make_service(storage)

    version_repo.save(_make_version(version_id, storage_path))
    table_repo.save(DatasetTable(table_id=uuid.uuid4(), dataset_version_id=version_id, table_name="orders"))
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

def test_original_version_unchanged(duckdb_ctx) -> None:
    storage, version_id, storage_path = duckdb_ctx
    svc, version_repo, table_repo, plan_repo, _ = _make_service(storage)

    version_repo.save(_make_version(version_id, storage_path))
    table_repo.save(DatasetTable(table_id=uuid.uuid4(), dataset_version_id=version_id, table_name="orders"))
    step = _make_step(CleaningOperationType.strip_whitespace, {"column": "product"})
    plan = _make_plan([step], version_id)
    plan_repo.save(plan)

    result = svc.execute_cleaning_plan(
        _WORKSPACE_ID, _DATASET_ID, version_id, plan.cleaning_plan_id,
        _make_decisions([step]), _USER_ID,
    )

    # Original version still in repo with same ID and unchanged storage_path.
    orig = version_repo.get(version_id)
    assert orig is not None
    assert orig.storage_path == storage_path
    assert result.output_dataset_version_id != version_id


# ---------------------------------------------------------------------------
# 3. Output version parent points to input version
# ---------------------------------------------------------------------------

def test_output_version_parent(duckdb_ctx) -> None:
    storage, version_id, storage_path = duckdb_ctx
    svc, version_repo, table_repo, plan_repo, _ = _make_service(storage)
    version_repo.save(_make_version(version_id, storage_path))
    table_repo.save(DatasetTable(table_id=uuid.uuid4(), dataset_version_id=version_id, table_name="orders"))
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

def test_output_version_type_is_cleaned(duckdb_ctx) -> None:
    storage, version_id, storage_path = duckdb_ctx
    svc, version_repo, table_repo, plan_repo, _ = _make_service(storage)
    version_repo.save(_make_version(version_id, storage_path))
    table_repo.save(DatasetTable(table_id=uuid.uuid4(), dataset_version_id=version_id, table_name="orders"))
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

def test_missing_approval_raises(duckdb_ctx) -> None:
    storage, version_id, storage_path = duckdb_ctx
    svc, version_repo, table_repo, plan_repo, _ = _make_service(storage)
    version_repo.save(_make_version(version_id, storage_path))
    table_repo.save(DatasetTable(table_id=uuid.uuid4(), dataset_version_id=version_id, table_name="orders"))
    step = _make_step(
        CleaningOperationType.drop_rows, {"column": "revenue"},
        requires_approval=True, default_decision=DefaultDecision.require_review,
    )
    plan = _make_plan([step], version_id)
    plan_repo.save(plan)
    decisions = _make_decisions([], override=[])

    with pytest.raises(ValueError, match="blocked"):
        svc.execute_cleaning_plan(
            _WORKSPACE_ID, _DATASET_ID, version_id, plan.cleaning_plan_id, decisions, _USER_ID
        )


# ---------------------------------------------------------------------------
# 6. Cleaning result is saved in repository
# ---------------------------------------------------------------------------

def test_cleaning_result_saved(duckdb_ctx) -> None:
    storage, version_id, storage_path = duckdb_ctx
    svc, version_repo, table_repo, plan_repo, result_repo = _make_service(storage)
    version_repo.save(_make_version(version_id, storage_path))
    table_repo.save(DatasetTable(table_id=uuid.uuid4(), dataset_version_id=version_id, table_name="orders"))
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

def test_execution_log_has_step_results(duckdb_ctx) -> None:
    storage, version_id, storage_path = duckdb_ctx
    svc, version_repo, table_repo, plan_repo, _ = _make_service(storage)
    version_repo.save(_make_version(version_id, storage_path))
    table_repo.save(DatasetTable(table_id=uuid.uuid4(), dataset_version_id=version_id, table_name="orders"))
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

def test_version_number_increments(duckdb_ctx) -> None:
    storage, version_id, storage_path = duckdb_ctx
    svc, version_repo, table_repo, plan_repo, _ = _make_service(storage)
    version_repo.save(_make_version(version_id, storage_path, version_number=1))
    table_repo.save(DatasetTable(table_id=uuid.uuid4(), dataset_version_id=version_id, table_name="orders"))
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
# 9. Cleaned data is persisted in the output version's DuckDB artifact
# ---------------------------------------------------------------------------

def test_cleaned_table_saved_to_disk(duckdb_ctx) -> None:
    storage, version_id, storage_path = duckdb_ctx
    svc, version_repo, table_repo, plan_repo, _ = _make_service(storage)
    version_repo.save(_make_version(version_id, storage_path))
    table_repo.save(DatasetTable(table_id=uuid.uuid4(), dataset_version_id=version_id, table_name="orders"))
    step = _make_step(CleaningOperationType.strip_whitespace, {"column": "product"})
    plan = _make_plan([step], version_id)
    plan_repo.save(plan)

    result = svc.execute_cleaning_plan(
        _WORKSPACE_ID, _DATASET_ID, version_id, plan.cleaning_plan_id,
        _make_decisions([step]), _USER_ID,
    )

    out_version = version_repo.get(result.output_dataset_version_id)
    assert out_version is not None
    assert out_version.storage_path is not None

    # Read the cleaned DuckDB artifact from storage and verify data.
    artifact_bytes = storage.read(out_version.storage_path)
    with temp_duckdb_path() as tmp:
        tmp.write_bytes(artifact_bytes)
        rows = read_preview(tmp, "orders", limit=10)

    assert len(rows) == 3
    assert rows[0]["product"] == "Widget"   # whitespace stripped


# ---------------------------------------------------------------------------
# 10. Failed execution does not create cleaned dataset version
# ---------------------------------------------------------------------------

def test_failed_step_no_output_version(duckdb_ctx) -> None:
    storage, version_id, storage_path = duckdb_ctx
    svc, version_repo, table_repo, plan_repo, _ = _make_service(storage)
    version_repo.save(_make_version(version_id, storage_path))
    table_repo.save(DatasetTable(table_id=uuid.uuid4(), dataset_version_id=version_id, table_name="orders"))
    # Reference a table that doesn't exist in the DuckDB — executor should record failure.
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
