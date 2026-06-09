from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.dependencies import Repos, get_repos, get_storage
from app.schemas.common import JobStatus, JobType
from app.schemas.job import Job
from app.schemas.uploads import ContextDocumentUploadResponse
from app.services.upload_service import TABULAR_EXTENSIONS, upload_context
from app.tools.files.storage_service import StorageBackend

router = APIRouter()

_PENDING_PREFIX = "uploads/pending"


@router.post("/workspaces/{workspace_id}/datasets/upload", response_model=Job, status_code=201)
async def upload_dataset_route(
    workspace_id: UUID,
    file: UploadFile = File(...),
    dataset_name: str | None = Form(None),
    dataset_id: UUID | None = Form(None),
    repos: Repos = Depends(get_repos),
    storage: StorageBackend = Depends(get_storage),
) -> Job:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in TABULAR_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {suffix!r}. Expected one of {sorted(TABULAR_EXTENSIONS)}.",
        )
    file_id = uuid4()
    pending_path = f"{_PENDING_PREFIX}/{workspace_id}/{file_id}_{filename}"
    try:
        storage.save(pending_path, content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if dataset_id is not None:
        existing = repos.dataset.get(dataset_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found.")

    payload: dict = {
        "pending_storage_path": pending_path,
        "filename": filename,
        "dataset_name": dataset_name,
    }
    if dataset_id is not None:
        payload["existing_dataset_id"] = str(dataset_id)

    job = Job(
        job_id=uuid4(),
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        job_type=JobType.upload_import,
        status=JobStatus.queued,
        payload_json=payload,
        created_at=datetime.now(tz=UTC),
    )
    return repos.job.save(job)


@router.post(
    "/workspaces/{workspace_id}/context-documents/upload",
    response_model=ContextDocumentUploadResponse,
)
async def upload_context_route(
    workspace_id: UUID,
    file: UploadFile = File(...),
    repos: Repos = Depends(get_repos),
    storage: StorageBackend = Depends(get_storage),
) -> ContextDocumentUploadResponse:
    content = await file.read()
    try:
        return upload_context(
            content=content,
            filename=file.filename or "upload",
            workspace_id=workspace_id,
            repos=repos,
            storage=storage,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
