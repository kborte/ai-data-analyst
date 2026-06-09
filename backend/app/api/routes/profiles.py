from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import Repos, get_repos, get_storage
from app.schemas.common import JobStatus, JobType
from app.schemas.job import Job
from app.schemas.profile import DataProfile
from app.tools.files.storage_service import StorageBackend

router = APIRouter()


@router.post(
    "/datasets/{dataset_id}/versions/{dataset_version_id}/profile",
    response_model=Job,
    status_code=201,
)
def create_profile(
    dataset_id: UUID,
    dataset_version_id: UUID,
    repos: Repos = Depends(get_repos),
    storage: StorageBackend = Depends(get_storage),
) -> Job:
    version = repos.dataset_version.get(dataset_version_id)
    if version is None or version.dataset_id != dataset_id:
        raise HTTPException(
            status_code=404,
            detail=f"DatasetVersion {dataset_version_id} not found for dataset {dataset_id}.",
        )

    dataset = repos.dataset.get(dataset_id)
    workspace_id = dataset.workspace_id if dataset else uuid4()

    job = Job(
        job_id=uuid4(),
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        input_dataset_version_id=dataset_version_id,
        job_type=JobType.profile_dataset,
        status=JobStatus.queued,
        payload_json={"dataset_version_id": str(dataset_version_id)},
        created_at=datetime.now(tz=UTC),
    )
    return repos.job.save(job)


@router.get("/profiles/{profile_id}", response_model=DataProfile)
def get_profile(
    profile_id: UUID,
    repos: Repos = Depends(get_repos),
) -> DataProfile:
    profile = repos.profile.get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found.")
    return profile
