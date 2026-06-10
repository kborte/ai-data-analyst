"""API tests for cleaning execution routes (M9+: DuckDB-based)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos, get_storage
from app.main import app
from app.tools.data.duckdb_service import create_version_duckdb, read_preview, temp_duckdb_path
from app.tools.files.storage_service import LocalStorageBackend, version_path
from app.schemas.cleaning import (
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
)
from app.schemas.dataset import DatasetTable, DatasetVersion

_WORKSPACE_ID = uuid.uuid4()
_DATASET_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _make_step(
    op_type: CleaningOperationType = CleaningOperationType.strip_whitespace,
    requires_approval: bool = False,
    default_decision: DefaultDecision = DefaultDecision.approve,
    table: str = "orders",
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
        operation=CleaningOperation(operation_type=op_type, parameters={"column": "product"}),
        preview=CleaningPreview(rows_before=3, estimated_rows_after=3, estimated_rows_removed=0),
    )


@pytest.fixture()
def ctx(tmp_path: Path):
    fresh = Repos()
    backend = LocalStorageBackend(str(tmp_path / "storage"))
    app.dependency_overrides[get_repos] = lambda: fresh
    app.dependency_overrides[get_storage] = lambda: backend
    client = TestClient(app)
    yield client, fresh, backend
    app.dependency_overrides.clear()


def _seed_execute_context(
    repos: Repos,
    storage: LocalStorageBackend,
    steps: list[CleaningStep],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create version with DuckDB artifact and plan in repos. Returns (version_id, plan_id)."""
    version_id = uuid.uuid4()
    df = pd.DataFrame({"product": ["  Widget  ", "Gadget"], "revenue": [100.0, 200.0]})
    spath = version_path(_WORKSPACE_ID, _DATASET_ID, 1, "original")
    with temp_duckdb_path() as tmp_db:
        create_version_duckdb({"orders": df}, tmp_db)
        storage.save(spath, tmp_db.read_bytes())

    repos.dataset_version.save(DatasetVersion(
        dataset_version_id=version_id,
        dataset_id=_DATASET_ID,
        version_number=1,
        version_type=DatasetVersionType.original,
        storage_path=spath,
        created_by_user_id=_USER_ID,
        created_at=_now(),
    ))
    repos.dataset_table.save(DatasetTable(
        table_id=uuid.uuid4(),
        dataset_version_id=version_id,
        table_name="orders",
    ))
    plan = CleaningPlan(
        cleaning_plan_id=uuid.uuid4(),
        dataset_version_id=version_id,
        status=ArtifactStatus.completed,
        plan_json=CleaningPlanJson(steps=steps),
        created_at=_now(),
    )
    repos.cleaning_plan.save(plan)
    return version_id, plan.cleaning_plan_id


# ---------------------------------------------------------------------------
# 1. validate returns can_execute=true when approvals present
# ---------------------------------------------------------------------------


def test_validate_can_execute_true(ctx):
    client, repos, _ = ctx
    step = _make_step(requires_approval=True, default_decision=DefaultDecision.require_review)
    plan = CleaningPlan(
        cleaning_plan_id=uuid.uuid4(),
        dataset_version_id=uuid.uuid4(),
        status=ArtifactStatus.completed,
        plan_json=CleaningPlanJson(steps=[step]),
        created_at=_now(),
    )
    repos.cleaning_plan.save(plan)

    resp = client.post(
        f"/cleaning-plans/{plan.cleaning_plan_id}/decisions/validate",
        json={"decisions": [{"step_id": str(step.step_id), "decision": "approve"}]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["can_execute"] is True
    assert body["approved_steps"] == 1
    assert body["blocked_steps"] == 0


# ---------------------------------------------------------------------------
# 2. validate returns can_execute=false when required approval missing
# ---------------------------------------------------------------------------


def test_validate_can_execute_false_missing_approval(ctx):
    client, repos, _ = ctx
    step = _make_step(requires_approval=True, default_decision=DefaultDecision.require_review)
    plan = CleaningPlan(
        cleaning_plan_id=uuid.uuid4(),
        dataset_version_id=uuid.uuid4(),
        status=ArtifactStatus.completed,
        plan_json=CleaningPlanJson(steps=[step]),
        created_at=_now(),
    )
    repos.cleaning_plan.save(plan)

    resp = client.post(
        f"/cleaning-plans/{plan.cleaning_plan_id}/decisions/validate",
        json={"decisions": []},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["can_execute"] is False
    assert body["blocked_steps"] == 1


# ---------------------------------------------------------------------------
# 3. execute route creates a queued job (no longer runs synchronously)
# ---------------------------------------------------------------------------


def test_execute_creates_queued_job(ctx):
    client, repos, backend = ctx
    step = _make_step()
    version_id, plan_id = _seed_execute_context(repos, backend, [step])
    workspace_id = uuid.uuid4()

    resp = client.post(
        f"/cleaning-plans/{plan_id}/execute",
        json={
            "workspace_id": str(workspace_id),
            "dataset_id": str(_DATASET_ID),
            "input_dataset_version_id": str(version_id),
            "executed_by_user_id": str(_USER_ID),
            "decisions": [{"step_id": str(step.step_id), "decision": "approve"}],
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == "queued"
    assert body["job_type"] == "execute_cleaning"


# ---------------------------------------------------------------------------
# 4. execute route stores payload with decisions and ids
# ---------------------------------------------------------------------------


def test_execute_job_payload_contains_decisions(ctx):
    client, repos, backend = ctx
    step = _make_step()
    version_id, plan_id = _seed_execute_context(repos, backend, [step])
    workspace_id = uuid.uuid4()

    resp = client.post(
        f"/cleaning-plans/{plan_id}/execute",
        json={
            "workspace_id": str(workspace_id),
            "dataset_id": str(_DATASET_ID),
            "input_dataset_version_id": str(version_id),
            "executed_by_user_id": str(_USER_ID),
            "decisions": [{"step_id": str(step.step_id), "decision": "approve"}],
        },
    )

    body = resp.json()
    payload = body["payload_json"]
    assert payload["cleaning_plan_id"] == str(plan_id)
    assert len(payload["decisions"]) == 1
    assert payload["decisions"][0]["decision"] == "approve"


# ---------------------------------------------------------------------------
# 5. worker handler executes cleaning and marks job completed
# ---------------------------------------------------------------------------


def test_worker_runs_cleaning_job_end_to_end(ctx):
    from app.worker.runner import run_one

    client, repos, backend = ctx
    step = _make_step()
    version_id, plan_id = _seed_execute_context(repos, backend, [step])
    workspace_id = uuid.uuid4()

    resp = client.post(
        f"/cleaning-plans/{plan_id}/execute",
        json={
            "workspace_id": str(workspace_id),
            "dataset_id": str(_DATASET_ID),
            "input_dataset_version_id": str(version_id),
            "executed_by_user_id": str(_USER_ID),
            "decisions": [{"step_id": str(step.step_id), "decision": "approve"}],
        },
    )
    job_id = uuid.UUID(resp.json()["job_id"])

    processed = run_one(repos.job, repos, storage=backend, llm=None)

    assert processed is True
    saved_job = repos.job.get(job_id)
    assert saved_job.status == "completed"
    assert saved_job.result_type == "cleaning_result"
    assert saved_job.result_id is not None
    assert saved_job.output_dataset_version_id is not None


# ---------------------------------------------------------------------------
# 6. worker creates CleaningResult and cleaned DatasetVersion
# ---------------------------------------------------------------------------


def test_worker_creates_cleaning_result_and_version(ctx):
    from app.worker.runner import run_one

    client, repos, backend = ctx
    step = _make_step()
    version_id, plan_id = _seed_execute_context(repos, backend, [step])
    workspace_id = uuid.uuid4()

    resp = client.post(
        f"/cleaning-plans/{plan_id}/execute",
        json={
            "workspace_id": str(workspace_id),
            "dataset_id": str(_DATASET_ID),
            "input_dataset_version_id": str(version_id),
            "executed_by_user_id": str(_USER_ID),
            "decisions": [{"step_id": str(step.step_id), "decision": "approve"}],
        },
    )
    job_id = uuid.UUID(resp.json()["job_id"])
    run_one(repos.job, repos, storage=backend, llm=None)

    job = repos.job.get(job_id)
    result = repos.cleaning_result.get(job.result_id)
    assert result is not None
    assert result.status == "completed"
    out_version = repos.dataset_version.get(job.output_dataset_version_id)
    assert out_version is not None
    assert out_version.dataset_id == _DATASET_ID
    assert out_version.parent_version_id == version_id


# ---------------------------------------------------------------------------
# 7. original version not mutated after worker runs
# ---------------------------------------------------------------------------


def test_worker_does_not_mutate_original_version(ctx):
    from app.worker.runner import run_one

    client, repos, backend = ctx
    step = _make_step()
    version_id, plan_id = _seed_execute_context(repos, backend, [step])
    original_storage_path = repos.dataset_version.get(version_id).storage_path
    original_bytes = backend.read(original_storage_path)
    workspace_id = uuid.uuid4()

    resp = client.post(
        f"/cleaning-plans/{plan_id}/execute",
        json={
            "workspace_id": str(workspace_id),
            "dataset_id": str(_DATASET_ID),
            "input_dataset_version_id": str(version_id),
            "executed_by_user_id": str(_USER_ID),
            "decisions": [{"step_id": str(step.step_id), "decision": "approve"}],
        },
    )
    run_one(repos.job, repos, storage=backend, llm=None)

    # Original artifact must not be overwritten.
    assert backend.read(original_storage_path) == original_bytes
    assert repos.dataset_version.get(version_id) is not None


# ---------------------------------------------------------------------------
# 6. Missing cleaning plan returns clear error
# ---------------------------------------------------------------------------


def test_validate_missing_plan_returns_404(ctx):
    client, _, _ = ctx
    resp = client.post(
        f"/cleaning-plans/{uuid.uuid4()}/decisions/validate",
        json={"decisions": []},
    )
    assert resp.status_code == 404


def test_execute_missing_plan_returns_404(ctx):
    client, repos, _ = ctx
    version_id = uuid.uuid4()
    repos.dataset_version.save(DatasetVersion(
        dataset_version_id=version_id,
        dataset_id=_DATASET_ID,
        version_number=1,
        version_type=DatasetVersionType.original,
        created_by_user_id=_USER_ID,
        created_at=_now(),
    ))
    resp = client.post(
        f"/cleaning-plans/{uuid.uuid4()}/execute",
        json={
            "workspace_id": str(uuid.uuid4()),
            "dataset_id": str(_DATASET_ID),
            "input_dataset_version_id": str(version_id),
            "executed_by_user_id": str(_USER_ID),
            "decisions": [],
        },
    )
    assert resp.status_code == 404
