from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import JobStatus, JobType


class Job(BaseModel):
    job_id: UUID
    workspace_id: UUID
    dataset_id: UUID | None = None
    input_dataset_version_id: UUID | None = None
    job_type: JobType
    status: JobStatus
    payload_json: dict[str, Any] = {}
    result_type: str | None = None
    result_id: UUID | None = None
    output_dataset_version_id: UUID | None = None
    error_message: str | None = None
    progress_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
