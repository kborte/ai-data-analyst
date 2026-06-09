"""Workspace management routes."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import Repos, get_repos

router = APIRouter(tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    name: str
    created_by_user_id: UUID


class WorkspaceResponse(BaseModel):
    workspace_id: str
    name: str
    created_by_user_id: str
    created_at: str


class AddMemberRequest(BaseModel):
    username: str


class UserLookupResponse(BaseModel):
    user_id: str
    username: str


def _ws_response(ws) -> WorkspaceResponse:
    return WorkspaceResponse(
        workspace_id=str(ws.workspace_id),
        name=ws.name,
        created_by_user_id=str(ws.created_by_user_id),
        created_at=ws.created_at.isoformat(),
    )


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=201)
def create_workspace(
    body: CreateWorkspaceRequest,
    repos: Repos = Depends(get_repos),
) -> WorkspaceResponse:
    user = repos.user.get(body.created_by_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.now(tz=UTC)
    ws = repos.workspace.create(
        name=body.name.strip() or "Untitled workspace",
        created_by_user_id=body.created_by_user_id,
        created_at=now,
    )
    repos.workspace.add_member(ws.workspace_id, body.created_by_user_id, role="owner", joined_at=now)
    return _ws_response(ws)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(workspace_id: UUID, repos: Repos = Depends(get_repos)) -> WorkspaceResponse:
    ws = repos.workspace.get(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return _ws_response(ws)


@router.get("/users/{user_id}/workspaces", response_model=list[WorkspaceResponse])
def list_user_workspaces(user_id: UUID, repos: Repos = Depends(get_repos)) -> list[WorkspaceResponse]:
    return [_ws_response(ws) for ws in repos.workspace.list_by_user(user_id)]


@router.post("/workspaces/{workspace_id}/members", status_code=204)
def add_member(
    workspace_id: UUID,
    body: AddMemberRequest,
    repos: Repos = Depends(get_repos),
) -> None:
    ws = repos.workspace.get(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    username = body.username.strip().lower()
    user = repos.user.find_by_email(f"{username}@placeholder.local")
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")

    repos.workspace.add_member(workspace_id, user.user_id, role="member", joined_at=datetime.now(tz=UTC))


@router.get("/users", response_model=UserLookupResponse)
def lookup_user(username: str, repos: Repos = Depends(get_repos)) -> UserLookupResponse:
    user = repos.user.find_by_email(f"{username.strip().lower()}@placeholder.local")
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserLookupResponse(user_id=str(user.user_id), username=user.display_name)
