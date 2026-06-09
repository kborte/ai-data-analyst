from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response

from app.dependencies import Repos, get_repos, get_storage
from app.schemas.saved_visual import SavedVisual, SavedVisualCreate
from app.tools.files.storage_service import StorageBackend

router = APIRouter(tags=["saved_visuals"])


# ---------------------------------------------------------------------------
# List / Create
# ---------------------------------------------------------------------------

@router.get(
    "/datasets/{dataset_id}/versions/{dataset_version_id}/visuals",
    response_model=list[SavedVisual],
)
def list_visuals(
    dataset_id: UUID,
    dataset_version_id: UUID,
    repos: Repos = Depends(get_repos),
):
    return repos.saved_visual.list_by_version(dataset_version_id)


@router.post(
    "/datasets/{dataset_id}/versions/{dataset_version_id}/visuals",
    response_model=SavedVisual,
    status_code=201,
)
def create_visual(
    dataset_id: UUID,
    dataset_version_id: UUID,
    body: SavedVisualCreate,
    repos: Repos = Depends(get_repos),
):
    dataset = repos.dataset.get(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    visual = SavedVisual(
        visual_id=uuid4(),
        workspace_id=dataset.workspace_id,
        dataset_id=dataset_id,
        dataset_version_id=dataset_version_id,
        title=body.title,
        description=body.description,
        chart_type=body.chart_type,
        chart_spec_json=body.chart_spec_json,
        source_type=body.source_type,
        source_visualization_result_id=body.source_visualization_result_id,
        source_view_id=body.source_view_id,
        source_spec_json=body.source_spec_json,
        data_storage_backend=body.data_storage_backend,
        data_storage_bucket=body.data_storage_bucket,
        data_storage_path=body.data_storage_path,
        created_at=datetime.now(tz=timezone.utc),
        created_by_user_id=body.created_by_user_id,
        metadata_json=body.metadata_json,
    )
    return repos.saved_visual.save(visual)


# ---------------------------------------------------------------------------
# Get / Delete
# ---------------------------------------------------------------------------

@router.get("/visuals/{visual_id}", response_model=SavedVisual)
def get_visual(visual_id: UUID, repos: Repos = Depends(get_repos)):
    visual = repos.saved_visual.get(visual_id)
    if visual is None:
        raise HTTPException(status_code=404, detail="Saved visual not found")
    return visual


@router.delete("/visuals/{visual_id}", status_code=204)
def delete_visual(
    visual_id: UUID,
    repos: Repos = Depends(get_repos),
    storage: StorageBackend = Depends(get_storage),
):
    visual = repos.saved_visual.get(visual_id)
    if visual is None:
        raise HTTPException(status_code=404, detail="Saved visual not found")
    if visual.data_storage_path:
        try:
            storage.delete(visual.data_storage_path)
        except Exception:
            pass  # best-effort; metadata deletion proceeds regardless
    repos.saved_visual.delete(visual_id)


# ---------------------------------------------------------------------------
# Chart data
# ---------------------------------------------------------------------------

@router.get("/visuals/{visual_id}/data")
def get_visual_data(
    visual_id: UUID,
    repos: Repos = Depends(get_repos),
    storage: StorageBackend = Depends(get_storage),
):
    """Return chart data for a saved visual.

    If a data artifact is stored separately (data_storage_path set), return its
    raw bytes. Otherwise return chart_spec_json.data inline as JSON so the
    frontend can render without a second round-trip.
    """
    visual = repos.saved_visual.get(visual_id)
    if visual is None:
        raise HTTPException(status_code=404, detail="Saved visual not found")

    if visual.data_storage_path:
        try:
            raw = storage.read(visual.data_storage_path)
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Data artifact not found in storage") from exc
        return Response(content=raw, media_type="application/json")

    # Fall back to inline data from chart_spec_json
    inline_data = visual.chart_spec_json.get("data", [])
    return JSONResponse(content={"data": inline_data, "visual_id": str(visual_id)})
