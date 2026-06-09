import csv
import io
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.dependencies import Repos, get_repos, get_storage
from app.schemas.saved_view import (
    PREVIEW_ROW_LIMIT,
    SavedView,
    SavedViewCreate,
    SavedViewPreview,
)
from app.tools.files.storage_service import StorageBackend

router = APIRouter(tags=["saved_views"])


# ---------------------------------------------------------------------------
# List / Create
# ---------------------------------------------------------------------------

@router.get(
    "/datasets/{dataset_id}/versions/{dataset_version_id}/views",
    response_model=list[SavedView],
)
def list_views(
    dataset_id: UUID,
    dataset_version_id: UUID,
    repos: Repos = Depends(get_repos),
):
    return repos.saved_view.list_by_version(dataset_version_id)


@router.post(
    "/datasets/{dataset_id}/versions/{dataset_version_id}/views",
    response_model=SavedView,
    status_code=201,
)
def create_view(
    dataset_id: UUID,
    dataset_version_id: UUID,
    body: SavedViewCreate,
    repos: Repos = Depends(get_repos),
):
    dataset = repos.dataset.get(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    view = SavedView(
        saved_view_id=uuid4(),
        workspace_id=dataset.workspace_id,
        dataset_id=dataset_id,
        dataset_version_id=dataset_version_id,
        name=body.name,
        description=body.description,
        source_type=body.source_type,
        source_spec_json=body.source_spec_json,
        storage_backend=body.storage_backend,
        storage_bucket=body.storage_bucket,
        storage_path=body.storage_path,
        storage_format=body.storage_format,
        row_count=body.row_count,
        column_count=body.column_count,
        created_at=datetime.now(tz=timezone.utc),
        created_by_user_id=body.created_by_user_id,
        metadata_json=body.metadata_json,
    )
    return repos.saved_view.save(view)


# ---------------------------------------------------------------------------
# Get / Delete
# ---------------------------------------------------------------------------

@router.get("/views/{view_id}", response_model=SavedView)
def get_view(view_id: UUID, repos: Repos = Depends(get_repos)):
    view = repos.saved_view.get(view_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Saved view not found")
    return view


@router.delete("/views/{view_id}", status_code=204)
def delete_view(
    view_id: UUID,
    repos: Repos = Depends(get_repos),
    storage: StorageBackend = Depends(get_storage),
):
    view = repos.saved_view.get(view_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Saved view not found")
    if view.storage_path:
        try:
            storage.delete(view.storage_path)
        except Exception:
            pass  # best-effort; metadata deletion proceeds regardless
    repos.saved_view.delete(view_id)


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

@router.get("/views/{view_id}/preview", response_model=SavedViewPreview)
def preview_view(
    view_id: UUID,
    repos: Repos = Depends(get_repos),
    storage: StorageBackend = Depends(get_storage),
):
    view = repos.saved_view.get(view_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Saved view not found")

    if not view.storage_path:
        return SavedViewPreview(
            saved_view_id=view_id,
            columns=[],
            rows=[],
            preview_row_count=0,
            total_rows_in_artifact=view.row_count,
        )

    fmt = (view.storage_format or "").lower()
    if fmt not in ("csv", ""):
        raise HTTPException(
            status_code=415,
            detail=f"Preview not supported for format '{fmt}'. Only CSV is supported.",
        )

    try:
        raw = storage.read(view.storage_path)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Artifact not found in storage") from exc

    reader = csv.reader(io.StringIO(raw.decode("utf-8")))
    rows_iter = iter(reader)
    try:
        columns = next(rows_iter)
    except StopIteration:
        return SavedViewPreview(
            saved_view_id=view_id,
            columns=[],
            rows=[],
            preview_row_count=0,
            total_rows_in_artifact=view.row_count,
        )

    rows = [row for _, row in zip(range(PREVIEW_ROW_LIMIT), rows_iter)]
    return SavedViewPreview(
        saved_view_id=view_id,
        columns=columns,
        rows=rows,
        preview_row_count=len(rows),
        total_rows_in_artifact=view.row_count,
    )


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

@router.get("/views/{view_id}/download")
def download_view(
    view_id: UUID,
    format: str = Query(default="csv"),
    repos: Repos = Depends(get_repos),
    storage: StorageBackend = Depends(get_storage),
):
    view = repos.saved_view.get(view_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Saved view not found")

    if format.lower() != "csv":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported download format '{format}'. Only 'csv' is supported.",
        )

    if not view.storage_path:
        raise HTTPException(status_code=404, detail="No artifact stored for this view")

    try:
        data = storage.read(view.storage_path)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Artifact not found in storage") from exc

    safe_name = view.name.replace(" ", "_").replace("/", "_")
    return Response(
        content=data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.csv"'},
    )
