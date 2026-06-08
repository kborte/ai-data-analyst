"""API tests for cleaning execution routes (M5D)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos
from app.main import app
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
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.tools.files.storage.settings.LOCAL_STORAGE_DIR", str(tmp_path))
    fresh = Repos()
    app.dependency_overrides[get_repos] = lambda: fresh
    client = TestClient(app)
    yield client, fresh, tmp_path
    app.dependency_overrides.clear()


def _seed_execute_context(repos: Repos, tmp_path: Path, steps: list[CleaningStep]):
    """Create version, table CSV, and plan in repos. Returns (version_id, plan_id)."""
    version_id = uuid.uuid4()
    csv_path = tmp_path / "orders.csv"
    df = pd.DataFrame({"product": ["  Widget  ", "Gadget"], "revenue": [100.0, 200.0]})
    df.to_csv(csv_path, index=False)

    repos.dataset_version.save(DatasetVersion(
        dataset_version_id=version_id,
        dataset_id=_DATASET_ID,
        version_number=1,
        version_type=DatasetVersionType.original,
        created_by_user_id=_USER_ID,
        created_at=_now(),
    ))
    repos.dataset_table.save(DatasetTable(
        table_id=uuid.uuid4(),
        dataset_version_id=version_id,
        table_name="orders",
        storage_path=str(csv_path),
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
# 3. execute route creates cleaning result
# ---------------------------------------------------------------------------


def test_execute_creates_cleaning_result(ctx):
    client, repos, tmp_path = ctx
    step = _make_step()
    version_id, plan_id = _seed_execute_context(repos, tmp_path, [step])

    resp = client.post(
        f"/cleaning-plans/{plan_id}/execute",
        json={
            "workspace_id": str(uuid.uuid4()),
            "dataset_id": str(_DATASET_ID),
            "input_dataset_version_id": str(version_id),
            "executed_by_user_id": str(_USER_ID),
            "decisions": [{"step_id": str(step.step_id), "decision": "approve"}],
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "cleaning_result_id" in body
    assert body["status"] == "completed"


# ---------------------------------------------------------------------------
# 4. execute route returns output dataset version id
# ---------------------------------------------------------------------------


def test_execute_returns_output_version_id(ctx):
    client, repos, tmp_path = ctx
    step = _make_step()
    version_id, plan_id = _seed_execute_context(repos, tmp_path, [step])

    resp = client.post(
        f"/cleaning-plans/{plan_id}/execute",
        json={
            "workspace_id": str(uuid.uuid4()),
            "dataset_id": str(_DATASET_ID),
            "input_dataset_version_id": str(version_id),
            "executed_by_user_id": str(_USER_ID),
            "decisions": [{"step_id": str(step.step_id), "decision": "approve"}],
        },
    )

    body = resp.json()
    assert body["output_dataset_version_id"] is not None
    out_id = uuid.UUID(body["output_dataset_version_id"])
    assert repos.dataset_version.get(out_id) is not None


# ---------------------------------------------------------------------------
# 5. execute route does not mutate original version
# ---------------------------------------------------------------------------


def test_execute_does_not_mutate_original(ctx):
    client, repos, tmp_path = ctx
    step = _make_step()
    version_id, plan_id = _seed_execute_context(repos, tmp_path, [step])
    csv_path = tmp_path / "orders.csv"
    original_content = csv_path.read_bytes()

    client.post(
        f"/cleaning-plans/{plan_id}/execute",
        json={
            "workspace_id": str(uuid.uuid4()),
            "dataset_id": str(_DATASET_ID),
            "input_dataset_version_id": str(version_id),
            "executed_by_user_id": str(_USER_ID),
            "decisions": [{"step_id": str(step.step_id), "decision": "approve"}],
        },
    )

    assert csv_path.read_bytes() == original_content
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


def test_execute_missing_plan_returns_422(ctx):
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
    assert resp.status_code == 422
