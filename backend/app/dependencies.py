from collections.abc import Generator
from dataclasses import dataclass, field

from app.repositories.memory import (
    CleaningPlanRepository,
    CleaningResultRepository,
    ContextDocumentRepository,
    DataProfileRepository,
    DatasetRepository,
    DatasetSourceRepository,
    DatasetTableRepository,
    DatasetVersionRepository,
    DataSourceRepository,
    FeaturePlanRepository,
    FeatureResultRepository,
    UploadedFileRepository,
)


@dataclass
class Repos:
    data_source: DataSourceRepository = field(default_factory=DataSourceRepository)
    uploaded_file: UploadedFileRepository = field(default_factory=UploadedFileRepository)
    dataset: DatasetRepository = field(default_factory=DatasetRepository)
    dataset_source: DatasetSourceRepository = field(default_factory=DatasetSourceRepository)
    dataset_version: DatasetVersionRepository = field(default_factory=DatasetVersionRepository)
    dataset_table: DatasetTableRepository = field(default_factory=DatasetTableRepository)
    context_document: ContextDocumentRepository = field(default_factory=ContextDocumentRepository)
    profile: DataProfileRepository = field(default_factory=DataProfileRepository)
    cleaning_plan: CleaningPlanRepository = field(default_factory=CleaningPlanRepository)
    cleaning_result: CleaningResultRepository = field(default_factory=CleaningResultRepository)
    feature_plan: FeaturePlanRepository = field(default_factory=FeaturePlanRepository)
    feature_result: FeatureResultRepository = field(default_factory=FeatureResultRepository)


_repos = Repos()


def get_repos() -> Repos:
    return _repos


def get_db_repos() -> Generator[Repos, None, None]:
    """FastAPI dependency that provides database-backed repositories via a SQLAlchemy session."""
    import app.repositories.database as db_repos  # noqa: PLC0415
    from app.db.base import get_db  # noqa: PLC0415

    for session in get_db():
        yield Repos(
            data_source=db_repos.DataSourceRepository(session),  # type: ignore[arg-type]
            uploaded_file=db_repos.UploadedFileRepository(session),  # type: ignore[arg-type]
            dataset=db_repos.DatasetRepository(session),  # type: ignore[arg-type]
            dataset_source=db_repos.DatasetSourceRepository(session),  # type: ignore[arg-type]
            dataset_version=db_repos.DatasetVersionRepository(session),  # type: ignore[arg-type]
            dataset_table=db_repos.DatasetTableRepository(session),  # type: ignore[arg-type]
            context_document=db_repos.ContextDocumentRepository(session),  # type: ignore[arg-type]
            profile=db_repos.DataProfileRepository(session),  # type: ignore[arg-type]
            cleaning_plan=db_repos.CleaningPlanRepository(session),  # type: ignore[arg-type]
            cleaning_result=db_repos.CleaningResultRepository(session),  # type: ignore[arg-type]
            feature_plan=db_repos.FeaturePlanRepository(session),  # type: ignore[arg-type]
            feature_result=db_repos.FeatureResultRepository(session),  # type: ignore[arg-type]
        )
