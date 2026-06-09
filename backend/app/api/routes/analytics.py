"""M12E: Thin analytics API routes — ask, save-as-view, save-as-visual."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import Repos, get_llm_provider, get_repos, get_storage
from app.schemas.analytics import (
    AnalyticsResponse,
    PriorOutputRef,
    RecentMessage,
)
from app.schemas.saved_view import SavedView
from app.schemas.saved_visual import SavedVisual
from app.services.analytics_context import build_dataset_context
from app.services.analytics_planner import AnalyticsPlanner
from app.services.saved_artifacts import (
    save_view_from_storage_artifact,
    save_view_from_table_result,
    save_visual_from_chart_spec,
)
from app.schemas.visualization import ChartSpec, SeriesSpec
from app.tools.data.duckdb_service import temp_duckdb_path
from app.tools.files.storage_service import StorageBackend
from app.tools.llm.provider import LLMProvider

router = APIRouter(tags=["analytics"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class AnalyticsAskRequest(BaseModel):
    question: str
    recent_messages: list[RecentMessage] = []
    prior_output_refs: list[PriorOutputRef] = []


class SaveAsViewRequest(BaseModel):
    dataset_id: UUID
    dataset_version_id: UUID
    name: str
    description: str | None = None
    # Provide storage_path for a large result already stored, OR columns+rows for inline.
    storage_path: str | None = None
    storage_backend: str | None = None
    storage_format: str | None = None
    columns: list[str] = []
    rows: list[list[Any]] = []


class SaveAsVisualRequest(BaseModel):
    dataset_id: UUID
    dataset_version_id: UUID
    title: str
    description: str | None = None
    chart_type: str
    chart_spec_json: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/datasets/{dataset_id}/versions/{dataset_version_id}/analytics/ask",
    response_model=AnalyticsResponse,
)
def ask_analytics(
    dataset_id: UUID,
    dataset_version_id: UUID,
    body: AnalyticsAskRequest,
    repos: Repos = Depends(get_repos),
    storage: StorageBackend = Depends(get_storage),
    llm: LLMProvider = Depends(get_llm_provider),
) -> AnalyticsResponse:
    version = repos.dataset_version.get(dataset_version_id)
    if version is None or version.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="DatasetVersion not found")

    dataset = repos.dataset.get(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if not version.storage_path or not version.storage_path.endswith(".duckdb"):
        raise HTTPException(
            status_code=422,
            detail="Dataset version has no DuckDB artifact. Run file ingestion first.",
        )

    context = build_dataset_context(
        dataset_id=dataset_id,
        dataset_version_id=dataset_version_id,
        dataset_repo=repos.dataset,
        version_repo=repos.dataset_version,
        table_repo=repos.dataset_table,
        profile_repo=repos.profile,
        saved_view_repo=repos.saved_view,
        saved_visual_repo=repos.saved_visual,
    )
    if context is None:
        raise HTTPException(status_code=404, detail="Dataset context could not be built")

    planner = AnalyticsPlanner(llm=llm)

    with temp_duckdb_path() as tmp_db:
        db_bytes = storage.read(version.storage_path)
        tmp_db.write_bytes(db_bytes)

        plan = planner.plan(
            question=body.question,
            context=context,
            recent_messages=body.recent_messages,
            prior_output_refs=body.prior_output_refs,
        )

        output = planner.execute(
            plan=plan,
            db_path=tmp_db,
            workspace_id=dataset.workspace_id,
            dataset_id=dataset_id,
            storage=storage,
            context=context,
        )

    return AnalyticsResponse(
        dataset_id=dataset_id,
        dataset_version_id=dataset_version_id,
        question=body.question,
        plan=plan,
        output=output,
    )


@router.post(
    "/analytics/table-results/save-as-view",
    response_model=SavedView,
    status_code=201,
)
def save_table_result_as_view(
    body: SaveAsViewRequest,
    repos: Repos = Depends(get_repos),
    storage: StorageBackend = Depends(get_storage),
) -> SavedView:
    version = repos.dataset_version.get(body.dataset_version_id)
    if version is None or version.dataset_id != body.dataset_id:
        raise HTTPException(status_code=404, detail="DatasetVersion not found")

    dataset = repos.dataset.get(body.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if body.storage_path:
        return save_view_from_storage_artifact(
            workspace_id=dataset.workspace_id,
            dataset_id=body.dataset_id,
            dataset_version_id=body.dataset_version_id,
            name=body.name,
            description=body.description,
            storage_backend=body.storage_backend or "local",
            storage_path=body.storage_path,
            storage_format=body.storage_format or "csv",
            repo=repos.saved_view,
        )

    if body.columns and body.rows is not None:
        return save_view_from_table_result(
            workspace_id=dataset.workspace_id,
            dataset_id=body.dataset_id,
            dataset_version_id=body.dataset_version_id,
            name=body.name,
            description=body.description,
            columns=body.columns,
            rows=body.rows,
            repo=repos.saved_view,
            storage=storage,
        )

    raise HTTPException(
        status_code=422,
        detail="Provide either storage_path or columns+rows to save the table result.",
    )


@router.post(
    "/analytics/visual-results/save-as-visual",
    response_model=SavedVisual,
    status_code=201,
)
def save_visual_result_as_visual(
    body: SaveAsVisualRequest,
    repos: Repos = Depends(get_repos),
) -> SavedVisual:
    version = repos.dataset_version.get(body.dataset_version_id)
    if version is None or version.dataset_id != body.dataset_id:
        raise HTTPException(status_code=404, detail="DatasetVersion not found")

    dataset = repos.dataset.get(body.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Build a minimal ChartSpec from the provided spec JSON
    try:
        chart_spec = _chart_spec_from_json(body.chart_type, body.chart_spec_json)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid chart_spec_json: {exc}") from exc

    return save_visual_from_chart_spec(
        workspace_id=dataset.workspace_id,
        dataset_id=body.dataset_id,
        dataset_version_id=body.dataset_version_id,
        title=body.title,
        description=body.description,
        chart_spec=chart_spec,
        repo=repos.saved_visual,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _chart_spec_from_json(chart_type: str, spec_json: dict[str, Any]) -> ChartSpec:
    """Reconstruct a ChartSpec from route-provided JSON, or build a minimal one."""
    if spec_json and "x_key" in spec_json and "series" in spec_json:
        return ChartSpec.model_validate(spec_json)

    # Minimal spec when the client only sends chart_type + title
    return ChartSpec(
        visualization_id=spec_json.get("visualization_id", str(__import__("uuid").uuid4())),
        title=spec_json.get("title", "Chart"),
        chart_type=chart_type,
        x_key=spec_json.get("x_key", "x"),
        series=[
            SeriesSpec(
                data_key=s["data_key"],
                label=s.get("label", s["data_key"]),
            )
            for s in spec_json.get("series", [{"data_key": "value", "label": "Value"}])
        ],
        data=spec_json.get("data", []),
        description=spec_json.get("description", ""),
    )
