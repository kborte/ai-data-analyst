from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ContextDocument(BaseModel):
    context_document_id: UUID
    workspace_id: UUID
    data_source_id: UUID | None = None
    title: str
    storage_path: str
    created_by_user_id: UUID
    created_at: datetime


class ContextSummary(BaseModel):
    context_document_id: UUID
    summary_text: str
    key_entities: list[str] = []
    key_metrics: list[str] = []
    created_at: datetime
