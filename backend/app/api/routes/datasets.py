"""Dataset listing and management routes for the frontend."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import Repos, get_repos
from app.schemas.dataset import Dataset, DatasetTable, DatasetVersion
from app.schemas.profile import DataProfile
from app.schemas.source import UploadedFile
from app.services.upload_service import SYSTEM_USER_ID

router = APIRouter(tags=["datasets"])


class CreateDatasetRequest(BaseModel):
    name: str


class DatasetFile(BaseModel):
    file_id: UUID
    data_source_id: UUID
    original_filename: str
    file_kind: str
    size_bytes: int
    uploaded_at: datetime


@router.post("/workspaces/{workspace_id}/datasets", response_model=Dataset, status_code=201)
def create_dataset(
    workspace_id: UUID,
    body: CreateDatasetRequest,
    repos: Repos = Depends(get_repos),
) -> Dataset:
    now = datetime.now(tz=UTC)
    dataset = Dataset(
        dataset_id=uuid4(),
        workspace_id=workspace_id,
        name=body.name.strip() or "Untitled dataset",
        created_by_user_id=SYSTEM_USER_ID,
        created_at=now,
    )
    return repos.dataset.save(dataset)


@router.get("/workspaces/{workspace_id}/datasets", response_model=list[Dataset])
def list_datasets(workspace_id: UUID, repos: Repos = Depends(get_repos)) -> list[Dataset]:
    return repos.dataset.list_by_workspace(workspace_id)


@router.get("/datasets/{dataset_id}", response_model=Dataset)
def get_dataset(dataset_id: UUID, repos: Repos = Depends(get_repos)) -> Dataset:
    ds = repos.dataset.get(dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


@router.get("/datasets/{dataset_id}/versions", response_model=list[DatasetVersion])
def list_versions(dataset_id: UUID, repos: Repos = Depends(get_repos)) -> list[DatasetVersion]:
    return repos.dataset_version.list_by_dataset(dataset_id)


@router.get(
    "/datasets/{dataset_id}/versions/{dataset_version_id}/tables",
    response_model=list[DatasetTable],
)
def list_tables(
    dataset_id: UUID,
    dataset_version_id: UUID,
    repos: Repos = Depends(get_repos),
) -> list[DatasetTable]:
    version = repos.dataset_version.get(dataset_version_id)
    if version is None or version.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="DatasetVersion not found")
    return repos.dataset_table.list_by_version(dataset_version_id)


@router.get(
    "/datasets/{dataset_id}/versions/{dataset_version_id}/profiles",
    response_model=list[DataProfile],
)
def list_profiles(
    dataset_id: UUID,
    dataset_version_id: UUID,
    repos: Repos = Depends(get_repos),
) -> list[DataProfile]:
    version = repos.dataset_version.get(dataset_version_id)
    if version is None or version.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="DatasetVersion not found")
    return repos.profile.list_by_version(dataset_version_id)


@router.get("/datasets/{dataset_id}/files", response_model=list[DatasetFile])
def list_dataset_files(
    dataset_id: UUID,
    repos: Repos = Depends(get_repos),
) -> list[DatasetFile]:
    ds = repos.dataset.get(dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    sources = repos.dataset_source.list_by_dataset(dataset_id)
    files: list[DatasetFile] = []
    for link in sources:
        for f in repos.uploaded_file.list_by_source(link.data_source_id):
            files.append(
                DatasetFile(
                    file_id=f.file_id,
                    data_source_id=f.data_source_id,
                    original_filename=f.original_filename,
                    file_kind=str(f.file_kind),
                    size_bytes=f.size_bytes,
                    uploaded_at=f.uploaded_at,
                )
            )
    return files


@router.delete("/datasets/{dataset_id}/files/{file_id}", status_code=204)
def remove_dataset_file(
    dataset_id: UUID,
    file_id: UUID,
    repos: Repos = Depends(get_repos),
) -> None:
    ds = repos.dataset.get(dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    uploaded = repos.uploaded_file.get(file_id)
    if uploaded is None:
        raise HTTPException(status_code=404, detail="File not found")
    removed = repos.dataset_source.delete_by_data_source(dataset_id, uploaded.data_source_id)
    if not removed:
        raise HTTPException(status_code=404, detail="File not linked to this dataset")
