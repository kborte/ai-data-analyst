"""
Core worker logic: claim one job, execute its handler, persist result/error.
Separated from __main__ so it can be unit-tested without spawning a process.
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.schemas.common import JobStatus
from app.worker.handlers import HANDLERS

if TYPE_CHECKING:
    from app.repositories.memory import JobRepository

logger = logging.getLogger(__name__)


def run_one(job_repo: "JobRepository", repos: Any, storage: Any = None, llm: Any = None) -> bool:
    """
    Claim and run the next queued job.

    Returns True if a job was processed, False if the queue was empty.
    `repos` is a full Repos instance, `storage` and `llm` are passed to handlers
    that need them (handlers should use the provided instances rather than constructing
    their own so that tests can inject fakes).
    """
    job = job_repo.claim_next_queued()
    if job is None:
        return False

    logger.info("claimed job %s type=%s", job.job_id, job.job_type)

    handler = HANDLERS.get(str(job.job_type))
    if handler is None:
        error = f"no handler registered for job_type '{job.job_type}'"
        logger.error(error)
        failed = job.model_copy(update={
            "status": JobStatus.failed,
            "error_message": error,
            "completed_at": datetime.now(tz=timezone.utc),
        })
        job_repo.save(failed)
        return True

    try:
        result_fields = handler(job, repos, storage, llm)
        completed = job.model_copy(update={
            "status": JobStatus.completed,
            "completed_at": datetime.now(tz=timezone.utc),
            **(result_fields or {}),
        })
        job_repo.save(completed)
        logger.info("job %s completed", job.job_id)
    except Exception:
        error_message = traceback.format_exc()
        logger.error("job %s failed:\n%s", job.job_id, error_message)
        failed = job.model_copy(update={
            "status": JobStatus.failed,
            "error_message": error_message,
            "completed_at": datetime.now(tz=timezone.utc),
        })
        job_repo.save(failed)

    return True
