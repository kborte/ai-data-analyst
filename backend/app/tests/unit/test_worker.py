"""Tests for worker claim/run/fail behavior using the in-memory repository."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.dependencies import Repos
from app.repositories.memory import JobRepository
from app.schemas.common import JobStatus, JobType
from app.schemas.job import Job
from app.worker.runner import run_one


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
def job_repo():
    return JobRepository()


@pytest.fixture()
def repos(job_repo):
    r = Repos()
    r.job = job_repo
    return r


# ── claim_next_queued ─────────────────────────────────────────────────────────

def test_claim_returns_none_when_empty(job_repo):
    assert job_repo.claim_next_queued() is None


def test_claim_marks_job_running(job_repo):
    job = _make_job()
    job_repo.save(job)
    claimed = job_repo.claim_next_queued()
    assert claimed is not None
    assert claimed.job_id == job.job_id
    assert claimed.status == JobStatus.running
    assert claimed.started_at is not None


def test_claim_oldest_first(job_repo):
    from datetime import timedelta
    now = datetime.now(tz=timezone.utc)
    old = _make_job(created_at=now - timedelta(seconds=10))
    new = _make_job(created_at=now)
    job_repo.save(new)
    job_repo.save(old)
    claimed = job_repo.claim_next_queued()
    assert claimed.job_id == old.job_id


def test_claim_skips_non_queued(job_repo):
    job_repo.save(_make_job(status=JobStatus.running))
    job_repo.save(_make_job(status=JobStatus.completed))
    job_repo.save(_make_job(status=JobStatus.failed))
    assert job_repo.claim_next_queued() is None


def test_claim_removes_from_queued_pool(job_repo):
    job_repo.save(_make_job())
    job_repo.claim_next_queued()
    assert job_repo.claim_next_queued() is None


# ── run_one: empty queue ──────────────────────────────────────────────────────

def test_run_one_returns_false_when_empty(job_repo, repos):
    assert run_one(job_repo, repos) is False


# ── run_one: successful job ───────────────────────────────────────────────────

def test_run_one_completes_job(job_repo, repos):
    from unittest.mock import patch

    job = _make_job(job_type=JobType.upload_import)
    job_repo.save(job)
    with patch("app.worker.runner.HANDLERS", {"upload_import": lambda j, r, s, l: {}}):
        processed = run_one(job_repo, repos, storage=None, llm=None)
    assert processed is True
    saved = job_repo.get(job.job_id)
    assert saved.status == JobStatus.completed
    assert saved.completed_at is not None


def test_run_one_returns_true_when_job_processed(job_repo, repos):
    from unittest.mock import patch
    job_repo.save(_make_job())
    with patch("app.worker.runner.HANDLERS", {"upload_import": lambda j, r, s, l: {}}):
        assert run_one(job_repo, repos) is True


def test_run_one_all_registered_types_have_handlers(job_repo, repos):
    from app.worker.handlers import HANDLERS
    for jt in JobType:
        assert str(jt) in HANDLERS, f"Missing handler for {jt}"


# ── run_one: handler raises ───────────────────────────────────────────────────

def test_run_one_marks_failed_on_handler_exception(job_repo, repos):
    from unittest.mock import patch

    def boom(job, repos, storage, llm):
        raise RuntimeError("something went wrong")

    job = _make_job(job_type=JobType.profile_dataset)
    job_repo.save(job)

    with patch("app.worker.runner.HANDLERS", {"profile_dataset": boom}):
        run_one(job_repo, repos)

    saved = job_repo.get(job.job_id)
    assert saved.status == JobStatus.failed
    assert "something went wrong" in saved.error_message
    assert saved.completed_at is not None


def test_run_one_captures_traceback_in_error_message(job_repo, repos):
    from unittest.mock import patch

    def explode(job, repos, storage, llm):
        raise ValueError("bad value")

    job = _make_job(job_type=JobType.execute_cleaning)
    job_repo.save(job)

    with patch("app.worker.runner.HANDLERS", {"execute_cleaning": explode}):
        run_one(job_repo, repos)

    saved = job_repo.get(job.job_id)
    assert "ValueError" in saved.error_message


# ── run_one: unknown job type ─────────────────────────────────────────────────

def test_run_one_fails_unknown_job_type(job_repo, repos):
    from unittest.mock import patch

    job = _make_job(job_type=JobType.upload_import)
    job_repo.save(job)

    with patch("app.worker.runner.HANDLERS", {}):
        run_one(job_repo, repos)

    saved = job_repo.get(job.job_id)
    assert saved.status == JobStatus.failed
    assert "no handler" in saved.error_message


# ── run_one: result fields propagated ────────────────────────────────────────

def test_run_one_stores_result_fields(job_repo, repos):
    from unittest.mock import patch

    result_id = uuid4()

    def handler_with_result(job, repos, storage, llm):
        return {"result_type": "data_profile", "result_id": result_id}

    job = _make_job(job_type=JobType.profile_dataset)
    job_repo.save(job)

    with patch("app.worker.runner.HANDLERS", {"profile_dataset": handler_with_result}):
        run_one(job_repo, repos)

    saved = job_repo.get(job.job_id)
    assert saved.status == JobStatus.completed
    assert saved.result_type == "data_profile"
    assert saved.result_id == result_id
