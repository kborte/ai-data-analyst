from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos
from app.main import app
from app.schemas.common import JobStatus, JobType
from app.schemas.job import Job


def _make_job(**kwargs) -> Job:
    defaults = dict(
        job_id=uuid4(),
        workspace_id=uuid4(),
        dataset_id=uuid4(),
        job_type=JobType.upload_import,
        status=JobStatus.queued,
        created_at=datetime.now(tz=timezone.utc),
    )
    defaults.update(kwargs)
    return Job(**defaults)


@pytest.fixture()
def mem_repos():
    return Repos()


@pytest.fixture()
def client(mem_repos):
    app.dependency_overrides[get_repos] = lambda: mem_repos
    yield TestClient(app)
    app.dependency_overrides.pop(get_repos, None)


def test_get_job_not_found(client):
    resp = client.get(f"/jobs/{uuid4()}")
    assert resp.status_code == 404


def test_get_job_found(client, mem_repos):
    job = _make_job()
    mem_repos.job.save(job)
    resp = client.get(f"/jobs/{job.job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == str(job.job_id)
    assert data["status"] == "queued"
    assert data["job_type"] == "upload_import"


def test_list_dataset_jobs_empty(client):
    resp = client.get(f"/datasets/{uuid4()}/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_dataset_jobs(client, mem_repos):
    dataset_id = uuid4()
    workspace_id = uuid4()
    j1 = _make_job(dataset_id=dataset_id, workspace_id=workspace_id, job_type=JobType.upload_import)
    j2 = _make_job(dataset_id=dataset_id, workspace_id=workspace_id, job_type=JobType.profile_dataset)
    other = _make_job()
    mem_repos.job.save(j1)
    mem_repos.job.save(j2)
    mem_repos.job.save(other)
    resp = client.get(f"/datasets/{dataset_id}/jobs")
    assert resp.status_code == 200
    ids = {item["job_id"] for item in resp.json()}
    assert str(j1.job_id) in ids
    assert str(j2.job_id) in ids
    assert str(other.job_id) not in ids


def test_cancel_queued_job(client, mem_repos):
    job = _make_job(status=JobStatus.queued)
    mem_repos.job.save(job)
    resp = client.post(f"/jobs/{job.job_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    saved = mem_repos.job.get(job.job_id)
    assert saved.status == JobStatus.cancelled


def test_cancel_running_job(client, mem_repos):
    job = _make_job(status=JobStatus.running)
    mem_repos.job.save(job)
    resp = client.post(f"/jobs/{job.job_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_cancel_completed_job_conflict(client, mem_repos):
    job = _make_job(status=JobStatus.completed)
    mem_repos.job.save(job)
    resp = client.post(f"/jobs/{job.job_id}/cancel")
    assert resp.status_code == 409


def test_cancel_failed_job_conflict(client, mem_repos):
    job = _make_job(status=JobStatus.failed)
    mem_repos.job.save(job)
    resp = client.post(f"/jobs/{job.job_id}/cancel")
    assert resp.status_code == 409


def test_cancel_nonexistent_job(client):
    resp = client.post(f"/jobs/{uuid4()}/cancel")
    assert resp.status_code == 404


def test_job_fields_in_response(client, mem_repos):
    dataset_id = uuid4()
    version_id = uuid4()
    job = _make_job(
        dataset_id=dataset_id,
        input_dataset_version_id=version_id,
        job_type=JobType.execute_cleaning,
        status=JobStatus.running,
        payload_json={"steps": 3},
        progress_message="2 of 3 steps done",
    )
    mem_repos.job.save(job)
    resp = client.get(f"/jobs/{job.job_id}")
    data = resp.json()
    assert data["dataset_id"] == str(dataset_id)
    assert data["input_dataset_version_id"] == str(version_id)
    assert data["job_type"] == "execute_cleaning"
    assert data["payload_json"] == {"steps": 3}
    assert data["progress_message"] == "2 of 3 steps done"
