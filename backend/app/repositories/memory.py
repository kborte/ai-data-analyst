"""
In-memory repositories backed by plain dicts keyed by UUID.
Temporary — replace with database-backed implementations in a later milestone.
"""

from uuid import UUID

from app.schemas.cleaning import CleaningDecisions, CleaningPlan, CleaningResult
from app.schemas.job import Job
from app.schemas.context_document import ContextDocument
from app.schemas.saved_view import SavedView
from app.schemas.saved_visual import SavedVisual
from app.schemas.dataset import Dataset, DatasetSource, DatasetTable, DatasetVersion
from app.schemas.features import FeatureDecisions, FeaturePlan, FeatureResult
from app.schemas.profile import DataProfile
from app.schemas.source import DataSource, UploadedFile
from app.schemas.user import User
from app.schemas.visualization import VisualizationPlan, VisualizationResult
from app.schemas.workspace import Workspace


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

    def delete_by_data_source(self, dataset_id: UUID, data_source_id: UUID) -> bool:
        for ds_id, obj in list(self._store.items()):
            if obj.dataset_id == dataset_id and obj.data_source_id == data_source_id:
                del self._store[ds_id]
                return True
        return False


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


class CleaningDecisionsRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, CleaningDecisions] = {}

    def save(self, obj: CleaningDecisions) -> CleaningDecisions:
        self._store[obj.cleaning_decisions_id] = obj
        return obj

    def get(self, cleaning_decisions_id: UUID) -> CleaningDecisions | None:
        return self._store.get(cleaning_decisions_id)


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


class FeatureDecisionsRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, FeatureDecisions] = {}

    def save(self, obj: FeatureDecisions) -> FeatureDecisions:
        self._store[obj.feature_decisions_id] = obj
        return obj

    def get(self, feature_decisions_id: UUID) -> FeatureDecisions | None:
        return self._store.get(feature_decisions_id)


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


class VisualizationPlanRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, VisualizationPlan] = {}

    def save(self, obj: VisualizationPlan) -> VisualizationPlan:
        self._store[obj.visualization_plan_id] = obj
        return obj

    def get(self, visualization_plan_id: UUID) -> VisualizationPlan | None:
        return self._store.get(visualization_plan_id)

    def list_by_version(self, dataset_version_id: UUID) -> list[VisualizationPlan]:
        return [v for v in self._store.values() if v.dataset_version_id == dataset_version_id]


class VisualizationResultRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, VisualizationResult] = {}

    def save(self, obj: VisualizationResult) -> VisualizationResult:
        self._store[obj.visualization_result_id] = obj
        return obj

    def get(self, visualization_result_id: UUID) -> VisualizationResult | None:
        return self._store.get(visualization_result_id)

    def list_by_plan(self, visualization_plan_id: UUID) -> list[VisualizationResult]:
        return [v for v in self._store.values() if v.visualization_plan_id == visualization_plan_id]


class JobRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, Job] = {}

    def save(self, obj: Job) -> Job:
        self._store[obj.job_id] = obj
        return obj

    def get(self, job_id: UUID) -> Job | None:
        return self._store.get(job_id)

    def list_by_dataset(self, dataset_id: UUID) -> list[Job]:
        return sorted(
            [j for j in self._store.values() if j.dataset_id == dataset_id],
            key=lambda j: j.created_at,
            reverse=True,
        )

    def list_by_workspace(self, workspace_id: UUID) -> list[Job]:
        return sorted(
            [j for j in self._store.values() if j.workspace_id == workspace_id],
            key=lambda j: j.created_at,
            reverse=True,
        )

    def claim_next_queued(self) -> Job | None:
        """Return and mark running the oldest queued job (not concurrency-safe)."""
        from datetime import datetime, timezone  # noqa: PLC0415
        candidates = sorted(
            [j for j in self._store.values() if j.status == "queued"],
            key=lambda j: j.created_at,
        )
        if not candidates:
            return None
        job = candidates[0]
        claimed = job.model_copy(update={
            "status": "running",
            "started_at": datetime.now(tz=timezone.utc),
        })
        self._store[claimed.job_id] = claimed
        return claimed


class SavedViewRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, SavedView] = {}

    def save(self, obj: SavedView) -> SavedView:
        self._store[obj.saved_view_id] = obj
        return obj

    def get(self, saved_view_id: UUID) -> SavedView | None:
        return self._store.get(saved_view_id)

    def list_by_version(self, dataset_version_id: UUID) -> list[SavedView]:
        return sorted(
            [v for v in self._store.values() if v.dataset_version_id == dataset_version_id],
            key=lambda v: v.created_at,
            reverse=True,
        )

    def list_by_dataset(self, dataset_id: UUID) -> list[SavedView]:
        return sorted(
            [v for v in self._store.values() if v.dataset_id == dataset_id],
            key=lambda v: v.created_at,
            reverse=True,
        )

    def delete(self, saved_view_id: UUID) -> bool:
        """Returns True if the view existed and was removed."""
        return self._store.pop(saved_view_id, None) is not None


class SavedVisualRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, SavedVisual] = {}

    def save(self, obj: SavedVisual) -> SavedVisual:
        self._store[obj.visual_id] = obj
        return obj

    def get(self, visual_id: UUID) -> SavedVisual | None:
        return self._store.get(visual_id)

    def list_by_version(self, dataset_version_id: UUID) -> list[SavedVisual]:
        return sorted(
            [v for v in self._store.values() if v.dataset_version_id == dataset_version_id],
            key=lambda v: v.created_at,
            reverse=True,
        )

    def list_by_dataset(self, dataset_id: UUID) -> list[SavedVisual]:
        return sorted(
            [v for v in self._store.values() if v.dataset_id == dataset_id],
            key=lambda v: v.created_at,
            reverse=True,
        )

    def delete(self, visual_id: UUID) -> bool:
        return self._store.pop(visual_id, None) is not None


class UserRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, User] = {}

    def create(self, email: str, display_name: str, created_at: object) -> User:
        import uuid as _uuid  # noqa: PLC0415
        from datetime import datetime  # noqa: PLC0415
        user = User(
            user_id=_uuid.uuid4(),
            email=email,
            display_name=display_name,
            created_at=created_at if isinstance(created_at, datetime) else datetime.now(),  # type: ignore[arg-type]
        )
        self._store[user.user_id] = user
        return user

    def get(self, user_id: UUID) -> User | None:
        return self._store.get(user_id)

    def find_by_email(self, email: str) -> User | None:
        return next((u for u in self._store.values() if u.email == email), None)


class WorkspaceRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, Workspace] = {}
        self._memberships: list[tuple[UUID, UUID]] = []  # (workspace_id, user_id)

    def create(self, name: str, created_by_user_id: UUID, created_at: object) -> Workspace:
        import uuid as _uuid  # noqa: PLC0415
        from datetime import datetime  # noqa: PLC0415
        ws = Workspace(
            workspace_id=_uuid.uuid4(),
            name=name,
            created_by_user_id=created_by_user_id,
            created_at=created_at if isinstance(created_at, datetime) else datetime.now(),  # type: ignore[arg-type]
        )
        self._store[ws.workspace_id] = ws
        return ws

    def save(self, ws: Workspace) -> Workspace:
        self._store[ws.workspace_id] = ws
        return ws

    def get(self, workspace_id: UUID) -> Workspace | None:
        return self._store.get(workspace_id)

    def list_by_user(self, user_id: UUID) -> list[Workspace]:
        ws_ids = {ws_id for ws_id, uid in self._memberships if uid == user_id}
        return [ws for ws_id, ws in self._store.items() if ws_id in ws_ids]

    def add_member(self, workspace_id: UUID, user_id: UUID, role: str, joined_at: object) -> None:
        if (workspace_id, user_id) not in self._memberships:
            self._memberships.append((workspace_id, user_id))
