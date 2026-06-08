from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.dependencies import Repos, get_repos
from app.schemas.uploads import ContextDocumentUploadResponse, DatasetUploadResponse
from app.services.upload_service import upload_context, upload_dataset

router = APIRouter()


@router.post("/workspaces/{workspace_id}/datasets/upload", response_model=DatasetUploadResponse)
async def upload_dataset_route(
    workspace_id: UUID,
    file: UploadFile = File(...),
    dataset_name: str | None = Form(None),
    repos: Repos = Depends(get_repos),
) -> DatasetUploadResponse:
    content = await file.read()
    try:
        return upload_dataset(
            content=content,
            filename=file.filename or "upload",
            workspace_id=workspace_id,
            dataset_name=dataset_name,
            repos=repos,
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
) -> ContextDocumentUploadResponse:
    content = await file.read()
    try:
        return upload_context(
            content=content,
            filename=file.filename or "upload",
            workspace_id=workspace_id,
            repos=repos,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
