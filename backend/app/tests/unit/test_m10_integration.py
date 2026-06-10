"""
M10 integration tests covering:
- job schema validation
- job repository create/read/list/update
- job status routes
- worker claim/success/failure behavior
- cleaning, upload, and profile job flows end-to-end
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos, get_storage
from app.main import app
from app.repositories.memory import JobRepository
from app.schemas.common import JobStatus, JobType
from app.schemas.job import Job
from app.schemas.workspace import Workspace
from app.tools.files.storage_service import LocalStorageBackend
from app.worker.runner import run_one

FIXTURES = Path(__file__).parent.parent / "fixtures"
CSV_BYTES = (FIXTURES / "simple_sales.csv").read_bytes()
WORKSPACE_ID = uuid4()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture()
def ctx(storage_dir: Path):
    repos = Repos()
    repos.workspace.save(Workspace(
        workspace_id=WORKSPACE_ID,
        name="test workspace",
        created_by_user_id=uuid4(),
        created_at=datetime.now(tz=timezone.utc),
    ))
    backend = LocalStorageBackend(str(storage_dir))
    app.dependency_overrides[get_repos] = lambda: repos
    app.dependency_overrides[get_storage] = lambda: backend
    client = TestClient(app)
    yield client, repos, backend
    app.dependency_overrides.clear()


def _make_job(**kwargs) -> Job:
    defaults = dict(
        job_id=uuid4(),
        workspace_id=WORKSPACE_ID,
        dataset_id=uuid4(),
        job_type=JobType.upload_import,
        status=JobStatus.queued,
        created_at=datetime.now(tz=timezone.utc),
    )
    defaults.update(kwargs)
    return Job(**defaults)


# ---------------------------------------------------------------------------
# Job schema validation
# ---------------------------------------------------------------------------

def test_job_schema_requires_job_id():
    with pytest.raises(Exception):
        Job(workspace_id=WORKSPACE_ID, job_type=JobType.upload_import,
            status=JobStatus.queued, created_at=datetime.now(tz=timezone.utc))


def test_job_schema_optional_fields_default_none():
    job = _make_job()
    assert job.dataset_id is not None  # set in _make_job
    assert job.input_dataset_version_id is None
    assert job.result_type is None
    assert job.result_id is None
    assert job.output_dataset_version_id is None
    assert job.error_message is None
    assert job.started_at is None
    assert job.completed_at is None


def test_job_schema_payload_json_defaults_empty():
    job = _make_job()
    assert job.payload_json == {}


def test_job_type_values():
    assert set(JobType) == {
        JobType.upload_import,
        JobType.profile_dataset,
        JobType.execute_cleaning,
        JobType.execute_features,
        JobType.generate_visualizations,
    }


def test_job_status_values():
    assert set(JobStatus) == {
        JobStatus.queued,
        JobStatus.running,
        JobStatus.completed,
        JobStatus.failed,
        JobStatus.cancelled,
    }


# ---------------------------------------------------------------------------
# Job repository CRUD
# ---------------------------------------------------------------------------

def test_repo_save_and_get():
    repo = JobRepository()
    job = _make_job()
    saved = repo.save(job)
    assert saved.job_id == job.job_id
    assert repo.get(job.job_id) is not None


def test_repo_get_missing_returns_none():
    repo = JobRepository()
    assert repo.get(uuid4()) is None


def test_repo_list_by_dataset():
    repo = JobRepository()
    dataset_id = uuid4()
    j1 = _make_job(dataset_id=dataset_id)
    j2 = _make_job(dataset_id=dataset_id)
    j3 = _make_job()  # different dataset
    repo.save(j1)
    repo.save(j2)
    repo.save(j3)
    results = repo.list_by_dataset(dataset_id)
    assert len(results) == 2
    ids = {r.job_id for r in results}
    assert j1.job_id in ids
    assert j2.job_id in ids


def test_repo_update_via_save():
    repo = JobRepository()
    job = _make_job()
    repo.save(job)
    updated = job.model_copy(update={"status": JobStatus.completed})
    repo.save(updated)
    assert repo.get(job.job_id).status == JobStatus.completed


def test_repo_list_by_dataset_sorted_newest_first():
    from datetime import timedelta
    repo = JobRepository()
    now = datetime.now(tz=timezone.utc)
    dataset_id = uuid4()
    old = _make_job(dataset_id=dataset_id, created_at=now - timedelta(seconds=10))
    new = _make_job(dataset_id=dataset_id, created_at=now)
    repo.save(old)
    repo.save(new)
    results = repo.list_by_dataset(dataset_id)
    assert results[0].job_id == new.job_id


# ---------------------------------------------------------------------------
# Job status API routes
# ---------------------------------------------------------------------------

def test_api_get_job(ctx):
    client, repos, backend = ctx
    job = _make_job(workspace_id=WORKSPACE_ID)
    repos.job.save(job)
    resp = client.get(f"/jobs/{job.job_id}")
    assert resp.status_code == 200
    assert resp.json()["job_id"] == str(job.job_id)


def test_api_get_job_not_found(ctx):
    client, repos, backend = ctx
    resp = client.get(f"/jobs/{uuid4()}")
    assert resp.status_code == 404


def test_api_list_dataset_jobs(ctx):
    client, repos, backend = ctx
    dataset_id = uuid4()
    repos.job.save(_make_job(workspace_id=WORKSPACE_ID, dataset_id=dataset_id))
    repos.job.save(_make_job(workspace_id=WORKSPACE_ID, dataset_id=dataset_id))
    repos.job.save(_make_job(workspace_id=WORKSPACE_ID))  # different dataset
    resp = client.get(f"/datasets/{dataset_id}/jobs")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_api_cancel_queued_job(ctx):
    client, repos, backend = ctx
    job = _make_job(workspace_id=WORKSPACE_ID, status=JobStatus.queued)
    repos.job.save(job)
    resp = client.post(f"/jobs/{job.job_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_api_cancel_completed_returns_409(ctx):
    client, repos, backend = ctx
    job = _make_job(workspace_id=WORKSPACE_ID, status=JobStatus.completed)
    repos.job.save(job)
    resp = client.post(f"/jobs/{job.job_id}/cancel")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Worker claim/success/failure behavior
# ---------------------------------------------------------------------------

def test_worker_empty_queue_returns_false():
    repo = JobRepository()
    repos = Repos()
    repos.job = repo
    assert run_one(repo, repos, storage=None, llm=None) is False


def test_worker_processes_job_and_returns_true():
    from unittest.mock import patch
    repo = JobRepository()
    repos = Repos()
    repos.job = repo
    job = _make_job()
    repo.save(job)
    with patch("app.worker.runner.HANDLERS", {str(job.job_type): lambda j, r, s, l: {}}):
        result = run_one(repo, repos, storage=None, llm=None)
    assert result is True


def test_worker_marks_job_completed():
    from unittest.mock import patch
    repo = JobRepository()
    repos = Repos()
    repos.job = repo
    job = _make_job()
    repo.save(job)
    with patch("app.worker.runner.HANDLERS", {str(job.job_type): lambda j, r, s, l: {}}):
        run_one(repo, repos, storage=None, llm=None)
    saved = repo.get(job.job_id)
    assert saved.status == JobStatus.completed
    assert saved.completed_at is not None


def test_worker_marks_job_failed_on_exception():
    from unittest.mock import patch
    repo = JobRepository()
    repos = Repos()
    repos.job = repo
    job = _make_job()
    repo.save(job)
    def raiser(j, r, s, l):
        raise RuntimeError("oops")
    with patch("app.worker.runner.HANDLERS", {str(job.job_type): raiser}):
        run_one(repo, repos, storage=None, llm=None)
    saved = repo.get(job.job_id)
    assert saved.status == JobStatus.failed
    assert "oops" in saved.error_message
    assert saved.completed_at is not None


def test_worker_sets_result_fields():
    from unittest.mock import patch
    result_id = uuid4()
    repo = JobRepository()
    repos = Repos()
    repos.job = repo
    job = _make_job()
    repo.save(job)
    with patch("app.worker.runner.HANDLERS", {
        str(job.job_type): lambda j, r, s, l: {"result_type": "data_profile", "result_id": result_id}
    }):
        run_one(repo, repos, storage=None, llm=None)
    saved = repo.get(job.job_id)
    assert saved.result_type == "data_profile"
    assert saved.result_id == result_id


# ---------------------------------------------------------------------------
# Upload job flow end-to-end
# ---------------------------------------------------------------------------

def test_upload_route_returns_queued_job(ctx):
    client, repos, backend = ctx
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_BYTES, "text/csv")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "queued"
    assert body["job_type"] == "upload_import"
    assert str(WORKSPACE_ID) == body["workspace_id"]


def test_upload_worker_creates_version(ctx):
    client, repos, backend = ctx
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_BYTES, "text/csv")},
    )
    job_id = UUID(resp.json()["job_id"])
    run_one(repos.job, repos, storage=backend, llm=None)
    job = repos.job.get(job_id)
    assert job.status == "completed"
    assert job.output_dataset_version_id is not None
    version = repos.dataset_version.get(job.output_dataset_version_id)
    assert version is not None
    assert version.storage_path.endswith(".duckdb")


def test_upload_job_can_be_polled_via_api(ctx):
    client, repos, backend = ctx
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_BYTES, "text/csv")},
    )
    job_id = resp.json()["job_id"]
    run_one(repos.job, repos, storage=backend, llm=None)
    poll = client.get(f"/jobs/{job_id}")
    assert poll.status_code == 200
    assert poll.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# Profile job flow end-to-end
# ---------------------------------------------------------------------------

def test_profile_route_returns_queued_job(ctx):
    client, repos, backend = ctx
    # Upload first
    client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_BYTES, "text/csv")},
    )
    run_one(repos.job, repos, storage=backend, llm=None)
    version = list(repos.dataset_version._store.values())[0]

    resp = client.post(f"/datasets/{version.dataset_id}/versions/{version.dataset_version_id}/profile")
    assert resp.status_code == 201
    assert resp.json()["job_type"] == "profile_dataset"
    assert resp.json()["status"] == "queued"


def test_profile_worker_creates_profiles(ctx):
    client, repos, backend = ctx
    client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_BYTES, "text/csv")},
    )
    run_one(repos.job, repos, storage=backend, llm=None)
    version = list(repos.dataset_version._store.values())[0]

    resp = client.post(f"/datasets/{version.dataset_id}/versions/{version.dataset_version_id}/profile")
    job_id = UUID(resp.json()["job_id"])
    run_one(repos.job, repos, storage=backend, llm=None)

    job = repos.job.get(job_id)
    assert job.status == "completed"
    assert job.result_id is not None
    profiles = repos.profile.list_by_version(version.dataset_version_id)
    assert len(profiles) == 1
    assert profiles[0].row_count == 5
