"""
In-memory repositories backed by plain dicts keyed by UUID.
Temporary — replace with database-backed implementations in a later milestone.
"""

from uuid import UUID

from app.schemas.cleaning import CleaningPlan, CleaningResult
from app.schemas.context_document import ContextDocument
from app.schemas.dataset import Dataset, DatasetSource, DatasetTable, DatasetVersion
from app.schemas.features import FeaturePlan, FeatureResult
from app.schemas.profile import DataProfile
from app.schemas.source import DataSource, UploadedFile


class DataSourceRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, DataSource] = {}

    def save(self, obj: DataSource) -> DataSource:
        self._store[obj.data_source_id] = obj
        return obj

    def get(self, data_source_id: UUID) -> DataSource | None:
        return self._store.get(data_source_id)

    def list_by_workspace(self, workspace_id: UUID) -> list[DataSource]:
        return [v for v in self._store.values() if v.workspace_id == workspace_id]


class UploadedFileRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, UploadedFile] = {}

    def save(self, obj: UploadedFile) -> UploadedFile:
        self._store[obj.file_id] = obj
        return obj

    def get(self, file_id: UUID) -> UploadedFile | None:
        return self._store.get(file_id)

    def list_by_source(self, data_source_id: UUID) -> list[UploadedFile]:
        return [v for v in self._store.values() if v.data_source_id == data_source_id]


class DatasetRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, Dataset] = {}

    def save(self, obj: Dataset) -> Dataset:
        self._store[obj.dataset_id] = obj
        return obj

    def get(self, dataset_id: UUID) -> Dataset | None:
        return self._store.get(dataset_id)

    def list_by_workspace(self, workspace_id: UUID) -> list[Dataset]:
        return [v for v in self._store.values() if v.workspace_id == workspace_id]


class DatasetSourceRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, DatasetSource] = {}

    def save(self, obj: DatasetSource) -> DatasetSource:
        self._store[obj.dataset_source_id] = obj
        return obj

    def get(self, dataset_source_id: UUID) -> DatasetSource | None:
        return self._store.get(dataset_source_id)

    def list_by_dataset(self, dataset_id: UUID) -> list[DatasetSource]:
        return [v for v in self._store.values() if v.dataset_id == dataset_id]


class DatasetVersionRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, DatasetVersion] = {}

    def save(self, obj: DatasetVersion) -> DatasetVersion:
        self._store[obj.dataset_version_id] = obj
        return obj

    def get(self, dataset_version_id: UUID) -> DatasetVersion | None:
        return self._store.get(dataset_version_id)

    def list_by_dataset(self, dataset_id: UUID) -> list[DatasetVersion]:
        return [v for v in self._store.values() if v.dataset_id == dataset_id]


class DatasetTableRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, DatasetTable] = {}

    def save(self, obj: DatasetTable) -> DatasetTable:
        self._store[obj.table_id] = obj
        return obj

    def get(self, table_id: UUID) -> DatasetTable | None:
        return self._store.get(table_id)

    def list_by_version(self, dataset_version_id: UUID) -> list[DatasetTable]:
        return [v for v in self._store.values() if v.dataset_version_id == dataset_version_id]


class ContextDocumentRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, ContextDocument] = {}

    def save(self, obj: ContextDocument) -> ContextDocument:
        self._store[obj.context_document_id] = obj
        return obj

    def get(self, context_document_id: UUID) -> ContextDocument | None:
        return self._store.get(context_document_id)

    def list_by_workspace(self, workspace_id: UUID) -> list[ContextDocument]:
        return [v for v in self._store.values() if v.workspace_id == workspace_id]


class DataProfileRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, DataProfile] = {}

    def save(self, obj: DataProfile) -> DataProfile:
        self._store[obj.profile_id] = obj
        return obj

    def get(self, profile_id: UUID) -> DataProfile | None:
        return self._store.get(profile_id)

    def list_by_version(self, dataset_version_id: UUID) -> list[DataProfile]:
        return [v for v in self._store.values() if v.dataset_version_id == dataset_version_id]


class CleaningPlanRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, CleaningPlan] = {}

    def save(self, obj: CleaningPlan) -> CleaningPlan:
        self._store[obj.cleaning_plan_id] = obj
        return obj

    def get(self, cleaning_plan_id: UUID) -> CleaningPlan | None:
        return self._store.get(cleaning_plan_id)

    def list_by_version(self, dataset_version_id: UUID) -> list[CleaningPlan]:
        return [v for v in self._store.values() if v.dataset_version_id == dataset_version_id]


class CleaningResultRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, CleaningResult] = {}

    def save(self, obj: CleaningResult) -> CleaningResult:
        self._store[obj.cleaning_result_id] = obj
        return obj

    def get(self, cleaning_result_id: UUID) -> CleaningResult | None:
        return self._store.get(cleaning_result_id)

    def list_by_plan(self, cleaning_plan_id: UUID) -> list[CleaningResult]:
        return [v for v in self._store.values() if v.cleaning_plan_id == cleaning_plan_id]


class FeaturePlanRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, FeaturePlan] = {}

    def save(self, obj: FeaturePlan) -> FeaturePlan:
        self._store[obj.feature_plan_id] = obj
        return obj

    def get(self, feature_plan_id: UUID) -> FeaturePlan | None:
        return self._store.get(feature_plan_id)

    def list_by_version(self, dataset_version_id: UUID) -> list[FeaturePlan]:
        return [v for v in self._store.values() if v.dataset_version_id == dataset_version_id]


class FeatureResultRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, FeatureResult] = {}

    def save(self, obj: FeatureResult) -> FeatureResult:
        self._store[obj.feature_result_id] = obj
        return obj

    def get(self, feature_result_id: UUID) -> FeatureResult | None:
        return self._store.get(feature_result_id)

    def list_by_plan(self, feature_plan_id: UUID) -> list[FeatureResult]:
        return [v for v in self._store.values() if v.feature_plan_id == feature_plan_id]
