from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.dependencies import Repos, get_repos, get_storage
from app.schemas.uploads import ContextDocumentUploadResponse, DatasetUploadResponse
from app.services.upload_service import upload_context, upload_dataset
from app.tools.files.storage_service import StorageBackend

router = APIRouter()


@router.post("/workspaces/{workspace_id}/datasets/upload", response_model=DatasetUploadResponse)
async def upload_dataset_route(
    workspace_id: UUID,
    file: UploadFile = File(...),
    dataset_name: str | None = Form(None),
    dataset_id: UUID | None = Form(None),
    repos: Repos = Depends(get_repos),
    storage: StorageBackend = Depends(get_storage),
) -> DatasetUploadResponse:
    content = await file.read()
    try:
        return upload_dataset(
            content=content,
            filename=file.filename or "upload",
            workspace_id=workspace_id,
            dataset_name=dataset_name,
            repos=repos,
            storage=storage,
            existing_dataset_id=dataset_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
