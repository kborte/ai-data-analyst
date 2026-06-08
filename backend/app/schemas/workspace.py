from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import WorkspaceRole


class Workspace(BaseModel):
    workspace_id: UUID
    name: str
    description: str | None = None
    created_by_user_id: UUID
    created_at: datetime


class WorkspaceMembership(BaseModel):
    membership_id: UUID
    workspace_id: UUID
    user_id: UUID
    role: WorkspaceRole
    joined_at: datetime
