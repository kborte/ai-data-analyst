"""Placeholder authentication routes.

No real auth — a username is used as an identifier.
Login creates the user if new, returns user_id + username either way.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import Repos, get_repos

router = APIRouter(tags=["auth"])

_PLACEHOLDER_EMAIL_SUFFIX = "@placeholder.local"


def _email(username: str) -> str:
    return f"{username.strip().lower()}{_PLACEHOLDER_EMAIL_SUFFIX}"


class LoginRequest(BaseModel):
    username: str


class LoginResponse(BaseModel):
    user_id: str
    username: str


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, repos: Repos = Depends(get_repos)) -> LoginResponse:
    username = body.username.strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="username required")

    existing = repos.user.find_by_email(_email(username))
    if existing:
        return LoginResponse(user_id=str(existing.user_id), username=existing.display_name)

    user = repos.user.create(
        email=_email(username),
        display_name=username,
        created_at=datetime.now(tz=UTC),
    )
    return LoginResponse(user_id=str(user.user_id), username=user.display_name)
