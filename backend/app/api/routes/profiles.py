from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import Repos, get_repos
from app.schemas.profile import DataProfile
from app.services.profiling_service import create_profiles

router = APIRouter()


@router.post(
    "/datasets/{dataset_id}/versions/{dataset_version_id}/profile",
    response_model=list[DataProfile],
)
def create_profile(
    dataset_id: UUID,
    dataset_version_id: UUID,
    repos: Repos = Depends(get_repos),
) -> list[DataProfile]:
    try:
        return create_profiles(
            dataset_id=dataset_id,
            dataset_version_id=dataset_version_id,
            repos=repos,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/profiles/{profile_id}", response_model=DataProfile)
def get_profile(
    profile_id: UUID,
    repos: Repos = Depends(get_repos),
) -> DataProfile:
    profile = repos.profile.get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found.")
    return profile
