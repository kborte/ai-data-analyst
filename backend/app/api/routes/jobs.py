from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import Repos, get_repos
from app.schemas.common import JobStatus
from app.schemas.job import Job

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: UUID, repos: Repos = Depends(get_repos)):
    job = repos.job.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/datasets/{dataset_id}/jobs", response_model=list[Job])
def list_dataset_jobs(dataset_id: UUID, repos: Repos = Depends(get_repos)):
    return repos.job.list_by_dataset(dataset_id)


@router.post("/jobs/{job_id}/cancel", response_model=Job)
def cancel_job(job_id: UUID, repos: Repos = Depends(get_repos)):
    job = repos.job.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in (JobStatus.queued, JobStatus.running):
        raise HTTPException(status_code=409, detail=f"Cannot cancel job with status '{job.status}'")
    cancelled = job.model_copy(update={"status": JobStatus.cancelled})
    return repos.job.save(cancelled)
