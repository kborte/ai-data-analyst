from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import AnalysisRunStatus, ArtifactStatus


class AnalysisArtifactRef(BaseModel):
    artifact_kind: str
    artifact_id: UUID
    status: ArtifactStatus


class AnalysisStage(BaseModel):
    stage_name: str
    status: AnalysisRunStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifact_refs: list[AnalysisArtifactRef] = []


class AnalysisRun(BaseModel):
    """
    Workflow/session record tying all artifacts from one analysis together.

    Tracks: which input version was used, which plans/decisions were generated,
    which output version was produced, and all associated artifacts.
    Not a copy of data — a reproducibility index.
    """

    analysis_run_id: UUID
    workspace_id: UUID
    dataset_id: UUID
    input_dataset_version_id: UUID
    final_dataset_version_id: UUID | None = None
    name: str | None = None
    status: AnalysisRunStatus
    stages: list[AnalysisStage] = []
    artifact_refs: list[AnalysisArtifactRef] = []
    context_document_ids: list[UUID] = []
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = {}
