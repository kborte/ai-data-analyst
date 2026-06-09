from collections.abc import Generator
from dataclasses import dataclass, field

from app.tools.llm.provider import FakeLLMProvider, LLMProvider, OpenAILLMProvider
from app.tools.files.storage_service import LocalStorageBackend, StorageBackend, SupabaseStorageBackend

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
    VisualizationPlanRepository,
    VisualizationResultRepository,
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
    visualization_plan: VisualizationPlanRepository = field(default_factory=VisualizationPlanRepository)
    visualization_result: VisualizationResultRepository = field(default_factory=VisualizationResultRepository)


_memory_repos = Repos()


def get_storage() -> StorageBackend:
    from app.core.config import settings  # noqa: PLC0415
    if settings.STORAGE_BACKEND == "supabase":
        return SupabaseStorageBackend(
            url=settings.SUPABASE_URL,
            key=settings.SUPABASE_SERVICE_ROLE_KEY,
            bucket=settings.SUPABASE_STORAGE_BUCKET,
        )
    return LocalStorageBackend(base_dir=settings.LOCAL_STORAGE_DIR)


def get_llm_provider() -> LLMProvider:
    from app.core.config import settings  # noqa: PLC0415
    if settings.OPENAI_API_KEY:
        return OpenAILLMProvider(api_key=settings.OPENAI_API_KEY, model=settings.LLM_MODEL)
    return FakeLLMProvider()


def get_memory_repos() -> Repos:
    return _memory_repos


def get_repos() -> Generator[Repos, None, None]:
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
            visualization_plan=db_repos.VisualizationPlanRepository(session),  # type: ignore[arg-type]
            visualization_result=db_repos.VisualizationResultRepository(session),  # type: ignore[arg-type]
        )
