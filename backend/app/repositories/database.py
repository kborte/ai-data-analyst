"""
Database-backed repository implementations using SQLAlchemy sessions.
Each class mirrors the interface of the corresponding in-memory repository.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import (
    CleaningDecisionsModel,
    CleaningPlanModel,
    CleaningResultModel,
    ContextDocumentModel,
    DataProfileModel,
    DatasetModel,
    DatasetSourceModel,
    DatasetTableModel,
    DatasetVersionModel,
    DataSourceModel,
    FeatureDecisionsModel,
    FeaturePlanModel,
    FeatureResultModel,
    JobModel,
    SavedViewModel,
    SavedVisualModel,
    UploadedFileModel,
    VisualizationPlanModel,
    VisualizationResultModel,
)
from app.schemas.job import Job
from app.schemas.cleaning import (
    CleaningDecisions,
    CleaningDecisionsJson,
    CleaningExecutionLogJson,
    CleaningPlan,
    CleaningPlanJson,
    CleaningResult,
)
from app.schemas.common import ApprovalStatus, ExecutionStatus
from app.schemas.context_document import ContextDocument
from app.schemas.dataset import Dataset, DatasetSource, DatasetTable, DatasetVersion
from app.schemas.features import (
    FeatureDecisions,
    FeatureDecisionsJson,
    FeatureExecutionLogJson,
    FeaturePlan,
    FeaturePlanJson,
    FeatureResult,
)
from app.schemas.profile import ColumnProfile, DataProfile, DataQualityIssue
from app.schemas.source import DataSource, UploadedFile
from app.schemas.saved_view import SavedView, SavedViewSourceType
from app.schemas.saved_visual import SavedVisual, SavedVisualSourceType
from app.schemas.visualization import (
    ChartExecutionResult,
    ChartSpec,
    VisualizationPlan,
    VisualizationPlanJson,
    VisualizationResult,
)

# --- ORM → Pydantic converters ---


def _data_source_from_orm(row: DataSourceModel) -> DataSource:
    return DataSource(
        data_source_id=row.data_source_id,
        workspace_id=row.workspace_id,
        source_kind=row.source_kind,
        display_name=row.display_name,
        description=row.description,
        storage_path=row.storage_path,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def _uploaded_file_from_orm(row: UploadedFileModel) -> UploadedFile:
    return UploadedFile(
        file_id=row.file_id,
        workspace_id=row.workspace_id,
        data_source_id=row.data_source_id,
        file_kind=row.file_kind,
        original_filename=row.original_filename,
        storage_path=row.storage_path,
        size_bytes=row.size_bytes,
        uploaded_by_user_id=row.uploaded_by_user_id,
        uploaded_at=row.uploaded_at,
    )


def _dataset_from_orm(row: DatasetModel) -> Dataset:
    return Dataset(
        dataset_id=row.dataset_id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def _dataset_source_from_orm(row: DatasetSourceModel) -> DatasetSource:
    return DatasetSource(
        dataset_source_id=row.dataset_source_id,
        dataset_id=row.dataset_id,
        data_source_id=row.data_source_id,
        role=row.source_role,
    )


def _dataset_version_from_orm(row: DatasetVersionModel) -> DatasetVersion:
    return DatasetVersion(
        dataset_version_id=row.dataset_version_id,
        dataset_id=row.dataset_id,
        parent_version_id=row.parent_version_id,
        version_number=row.version_number,
        version_type=row.version_type,
        display_name=row.display_name,
        description=row.description,
        storage_path=row.storage_path,
        row_count=row.row_count,
        column_count=row.column_count,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        metadata=row.obj_metadata or {},
    )


def _dataset_table_from_orm(row: DatasetTableModel) -> DatasetTable:
    return DatasetTable(
        table_id=row.table_id,
        dataset_version_id=row.dataset_version_id,
        table_name=row.table_name,
        storage_path=row.storage_path,
        row_count=row.row_count,
        column_count=row.column_count,
    )


def _context_document_from_orm(row: ContextDocumentModel) -> ContextDocument:
    return ContextDocument(
        context_document_id=row.context_document_id,
        workspace_id=row.workspace_id,
        data_source_id=row.data_source_id,
        title=row.title,
        storage_path=row.storage_path,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def _data_profile_from_orm(row: DataProfileModel) -> DataProfile:
    pj = row.profile_json or {}
    return DataProfile(
        profile_id=row.profile_id,
        dataset_version_id=row.dataset_version_id,
        table_name=row.table_name,
        row_count=row.row_count,
        column_count=row.column_count,
        column_profiles=[ColumnProfile.model_validate(cp) for cp in pj.get("column_profiles", [])],
        quality_issues=[DataQualityIssue.model_validate(qi) for qi in pj.get("quality_issues", [])],
        likely_id_columns=pj.get("likely_id_columns", []),
        likely_metric_columns=pj.get("likely_metric_columns", []),
        likely_categorical_columns=pj.get("likely_categorical_columns", []),
        likely_date_columns=pj.get("likely_date_columns", []),
        created_at=row.created_at,
        metadata=pj.get("metadata", {}),
    )


def _cleaning_plan_from_orm(row: CleaningPlanModel) -> CleaningPlan:
    return CleaningPlan(
        cleaning_plan_id=row.cleaning_plan_id,
        dataset_version_id=row.dataset_version_id,
        analysis_run_id=row.analysis_run_id,
        status=row.status,
        plan_json=CleaningPlanJson.model_validate(row.plan_json or {}),
        created_at=row.created_at,
    )


def _cleaning_result_from_orm(row: CleaningResultModel) -> CleaningResult:
    ej = row.execution_log_json or {}
    cols_changed = ej.get("_columns_changed", [])
    approval_status = ej.get("_approval_status", str(ApprovalStatus.pending))
    clean_ej = {k: v for k, v in ej.items() if not k.startswith("_")}
    return CleaningResult(
        cleaning_result_id=row.cleaning_result_id,
        cleaning_plan_id=row.cleaning_plan_id,
        cleaning_decisions_id=row.cleaning_decisions_id,
        input_dataset_version_id=row.input_dataset_version_id,
        output_dataset_version_id=row.output_dataset_version_id,
        status=row.status,
        row_count_before=row.row_count_before,
        row_count_after=row.row_count_after,
        columns_changed=cols_changed,
        execution_log_json=CleaningExecutionLogJson.model_validate(clean_ej),
        created_at=row.created_at,
        approval_status=approval_status,
    )


def _feature_plan_from_orm(row: FeaturePlanModel) -> FeaturePlan:
    return FeaturePlan(
        feature_plan_id=row.feature_plan_id,
        dataset_version_id=row.dataset_version_id,
        analysis_run_id=row.analysis_run_id,
        status=row.status,
        plan_json=FeaturePlanJson.model_validate(row.plan_json or {}),
        created_at=row.created_at,
    )


def _feature_result_from_orm(row: FeatureResultModel) -> FeatureResult:
    return FeatureResult(
        feature_result_id=row.feature_result_id,
        feature_plan_id=row.feature_plan_id,
        feature_decisions_id=row.feature_decisions_id,
        input_dataset_version_id=row.input_dataset_version_id,
        output_dataset_version_id=row.output_dataset_version_id,
        status=row.status,
        features_added=row.features_added or [],
        execution_log_json=FeatureExecutionLogJson.model_validate(row.execution_log_json or {}),
        created_at=row.created_at,
        execution_status=row.execution_status or str(ExecutionStatus.success),
    )


# --- Repository classes ---


class DataSourceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: DataSource) -> DataSource:
        row = DataSourceModel(
            data_source_id=obj.data_source_id,
            workspace_id=obj.workspace_id,
            source_kind=str(obj.source_kind),
            display_name=obj.display_name,
            description=obj.description,
            storage_path=obj.storage_path,
            created_by_user_id=obj.created_by_user_id,
            created_at=obj.created_at,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _data_source_from_orm(merged)

    def get(self, data_source_id: UUID) -> DataSource | None:
        row = self._session.get(DataSourceModel, data_source_id)
        return _data_source_from_orm(row) if row else None

    def list_by_workspace(self, workspace_id: UUID) -> list[DataSource]:
        rows = (
            self._session.query(DataSourceModel)
            .filter(DataSourceModel.workspace_id == workspace_id)
            .all()
        )
        return [_data_source_from_orm(r) for r in rows]


class UploadedFileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: UploadedFile) -> UploadedFile:
        row = UploadedFileModel(
            file_id=obj.file_id,
            workspace_id=obj.workspace_id,
            data_source_id=obj.data_source_id,
            file_kind=str(obj.file_kind),
            original_filename=obj.original_filename,
            storage_path=obj.storage_path,
            size_bytes=obj.size_bytes,
            uploaded_by_user_id=obj.uploaded_by_user_id,
            uploaded_at=obj.uploaded_at,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _uploaded_file_from_orm(merged)

    def get(self, file_id: UUID) -> UploadedFile | None:
        row = self._session.get(UploadedFileModel, file_id)
        return _uploaded_file_from_orm(row) if row else None

    def list_by_source(self, data_source_id: UUID) -> list[UploadedFile]:
        rows = (
            self._session.query(UploadedFileModel)
            .filter(UploadedFileModel.data_source_id == data_source_id)
            .all()
        )
        return [_uploaded_file_from_orm(r) for r in rows]


class DatasetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: Dataset) -> Dataset:
        row = DatasetModel(
            dataset_id=obj.dataset_id,
            workspace_id=obj.workspace_id,
            name=obj.name,
            description=obj.description,
            created_by_user_id=obj.created_by_user_id,
            created_at=obj.created_at,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _dataset_from_orm(merged)

    def get(self, dataset_id: UUID) -> Dataset | None:
        row = self._session.get(DatasetModel, dataset_id)
        return _dataset_from_orm(row) if row else None

    def list_by_workspace(self, workspace_id: UUID) -> list[Dataset]:
        rows = (
            self._session.query(DatasetModel)
            .filter(DatasetModel.workspace_id == workspace_id)
            .all()
        )
        return [_dataset_from_orm(r) for r in rows]


class DatasetSourceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: DatasetSource) -> DatasetSource:
        row = DatasetSourceModel(
            dataset_source_id=obj.dataset_source_id,
            dataset_id=obj.dataset_id,
            data_source_id=obj.data_source_id,
            source_role=str(obj.role),
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _dataset_source_from_orm(merged)

    def get(self, dataset_source_id: UUID) -> DatasetSource | None:
        row = self._session.get(DatasetSourceModel, dataset_source_id)
        return _dataset_source_from_orm(row) if row else None

    def list_by_dataset(self, dataset_id: UUID) -> list[DatasetSource]:
        rows = (
            self._session.query(DatasetSourceModel)
            .filter(DatasetSourceModel.dataset_id == dataset_id)
            .all()
        )
        return [_dataset_source_from_orm(r) for r in rows]


class DatasetVersionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: DatasetVersion) -> DatasetVersion:
        row = DatasetVersionModel(
            dataset_version_id=obj.dataset_version_id,
            dataset_id=obj.dataset_id,
            parent_version_id=obj.parent_version_id,
            version_number=obj.version_number,
            version_type=str(obj.version_type),
            display_name=obj.display_name,
            description=obj.description,
            storage_path=obj.storage_path,
            row_count=obj.row_count,
            column_count=obj.column_count,
            created_by_user_id=obj.created_by_user_id,
            created_at=obj.created_at,
            obj_metadata=obj.metadata,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _dataset_version_from_orm(merged)

    def get(self, dataset_version_id: UUID) -> DatasetVersion | None:
        row = self._session.get(DatasetVersionModel, dataset_version_id)
        return _dataset_version_from_orm(row) if row else None

    def list_by_dataset(self, dataset_id: UUID) -> list[DatasetVersion]:
        rows = (
            self._session.query(DatasetVersionModel)
            .filter(DatasetVersionModel.dataset_id == dataset_id)
            .all()
        )
        return [_dataset_version_from_orm(r) for r in rows]


class DatasetTableRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: DatasetTable) -> DatasetTable:
        row = DatasetTableModel(
            table_id=obj.table_id,
            dataset_version_id=obj.dataset_version_id,
            table_name=obj.table_name,
            storage_path=obj.storage_path,
            row_count=obj.row_count,
            column_count=obj.column_count,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _dataset_table_from_orm(merged)

    def get(self, table_id: UUID) -> DatasetTable | None:
        row = self._session.get(DatasetTableModel, table_id)
        return _dataset_table_from_orm(row) if row else None

    def list_by_version(self, dataset_version_id: UUID) -> list[DatasetTable]:
        rows = (
            self._session.query(DatasetTableModel)
            .filter(DatasetTableModel.dataset_version_id == dataset_version_id)
            .all()
        )
        return [_dataset_table_from_orm(r) for r in rows]


class ContextDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: ContextDocument) -> ContextDocument:
        row = ContextDocumentModel(
            context_document_id=obj.context_document_id,
            workspace_id=obj.workspace_id,
            data_source_id=obj.data_source_id,
            title=obj.title,
            storage_path=obj.storage_path,
            created_by_user_id=obj.created_by_user_id,
            created_at=obj.created_at,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _context_document_from_orm(merged)

    def get(self, context_document_id: UUID) -> ContextDocument | None:
        row = self._session.get(ContextDocumentModel, context_document_id)
        return _context_document_from_orm(row) if row else None

    def list_by_workspace(self, workspace_id: UUID) -> list[ContextDocument]:
        rows = (
            self._session.query(ContextDocumentModel)
            .filter(ContextDocumentModel.workspace_id == workspace_id)
            .all()
        )
        return [_context_document_from_orm(r) for r in rows]


class DataProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: DataProfile) -> DataProfile:
        row = DataProfileModel(
            profile_id=obj.profile_id,
            dataset_version_id=obj.dataset_version_id,
            table_name=obj.table_name,
            row_count=obj.row_count,
            column_count=obj.column_count,
            profile_json={
                "column_profiles": [cp.model_dump(mode="json") for cp in obj.column_profiles],
                "quality_issues": [qi.model_dump(mode="json") for qi in obj.quality_issues],
                "likely_id_columns": obj.likely_id_columns,
                "likely_metric_columns": obj.likely_metric_columns,
                "likely_categorical_columns": obj.likely_categorical_columns,
                "likely_date_columns": obj.likely_date_columns,
                "metadata": obj.metadata,
            },
            created_at=obj.created_at,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _data_profile_from_orm(merged)

    def get(self, profile_id: UUID) -> DataProfile | None:
        row = self._session.get(DataProfileModel, profile_id)
        return _data_profile_from_orm(row) if row else None

    def list_by_version(self, dataset_version_id: UUID) -> list[DataProfile]:
        rows = (
            self._session.query(DataProfileModel)
            .filter(DataProfileModel.dataset_version_id == dataset_version_id)
            .all()
        )
        return [_data_profile_from_orm(r) for r in rows]


class CleaningPlanRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: CleaningPlan) -> CleaningPlan:
        row = CleaningPlanModel(
            cleaning_plan_id=obj.cleaning_plan_id,
            dataset_version_id=obj.dataset_version_id,
            analysis_run_id=obj.analysis_run_id,
            status=str(obj.status),
            plan_json=obj.plan_json.model_dump(mode="json"),
            created_at=obj.created_at,
            workspace_id=None,
            dataset_id=None,
            profile_id=None,
            created_by_user_id=None,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _cleaning_plan_from_orm(merged)

    def get(self, cleaning_plan_id: UUID) -> CleaningPlan | None:
        row = self._session.get(CleaningPlanModel, cleaning_plan_id)
        return _cleaning_plan_from_orm(row) if row else None

    def list_by_version(self, dataset_version_id: UUID) -> list[CleaningPlan]:
        rows = (
            self._session.query(CleaningPlanModel)
            .filter(CleaningPlanModel.dataset_version_id == dataset_version_id)
            .all()
        )
        return [_cleaning_plan_from_orm(r) for r in rows]


class CleaningResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: CleaningResult) -> CleaningResult:
        execution_log_dict = obj.execution_log_json.model_dump(mode="json")
        execution_log_dict["_columns_changed"] = obj.columns_changed
        execution_log_dict["_approval_status"] = str(obj.approval_status)
        row = CleaningResultModel(
            cleaning_result_id=obj.cleaning_result_id,
            cleaning_plan_id=obj.cleaning_plan_id,
            cleaning_decisions_id=obj.cleaning_decisions_id,
            input_dataset_version_id=obj.input_dataset_version_id,
            output_dataset_version_id=obj.output_dataset_version_id,
            status=str(obj.status),
            row_count_before=obj.row_count_before,
            row_count_after=obj.row_count_after,
            execution_log_json=execution_log_dict,
            created_at=obj.created_at,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _cleaning_result_from_orm(merged)

    def get(self, cleaning_result_id: UUID) -> CleaningResult | None:
        row = self._session.get(CleaningResultModel, cleaning_result_id)
        return _cleaning_result_from_orm(row) if row else None

    def list_by_plan(self, cleaning_plan_id: UUID) -> list[CleaningResult]:
        rows = (
            self._session.query(CleaningResultModel)
            .filter(CleaningResultModel.cleaning_plan_id == cleaning_plan_id)
            .all()
        )
        return [_cleaning_result_from_orm(r) for r in rows]


class FeaturePlanRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: FeaturePlan) -> FeaturePlan:
        row = FeaturePlanModel(
            feature_plan_id=obj.feature_plan_id,
            dataset_version_id=obj.dataset_version_id,
            analysis_run_id=obj.analysis_run_id,
            status=str(obj.status),
            plan_json=obj.plan_json.model_dump(mode="json"),
            created_at=obj.created_at,
            workspace_id=None,
            dataset_id=None,
            profile_id=None,
            created_by_user_id=None,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _feature_plan_from_orm(merged)

    def get(self, feature_plan_id: UUID) -> FeaturePlan | None:
        row = self._session.get(FeaturePlanModel, feature_plan_id)
        return _feature_plan_from_orm(row) if row else None

    def list_by_version(self, dataset_version_id: UUID) -> list[FeaturePlan]:
        rows = (
            self._session.query(FeaturePlanModel)
            .filter(FeaturePlanModel.dataset_version_id == dataset_version_id)
            .all()
        )
        return [_feature_plan_from_orm(r) for r in rows]


class FeatureResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: FeatureResult) -> FeatureResult:
        row = FeatureResultModel(
            feature_result_id=obj.feature_result_id,
            feature_plan_id=obj.feature_plan_id,
            feature_decisions_id=obj.feature_decisions_id,
            input_dataset_version_id=obj.input_dataset_version_id,
            output_dataset_version_id=obj.output_dataset_version_id,
            status=str(obj.status),
            execution_status=str(obj.execution_status),
            features_added=obj.features_added,
            execution_log_json=obj.execution_log_json.model_dump(mode="json"),
            created_at=obj.created_at,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _feature_result_from_orm(merged)

    def get(self, feature_result_id: UUID) -> FeatureResult | None:
        row = self._session.get(FeatureResultModel, feature_result_id)
        return _feature_result_from_orm(row) if row else None

    def list_by_plan(self, feature_plan_id: UUID) -> list[FeatureResult]:
        rows = (
            self._session.query(FeatureResultModel)
            .filter(FeatureResultModel.feature_plan_id == feature_plan_id)
            .all()
        )
        return [_feature_result_from_orm(r) for r in rows]


# --- Decisions repositories (add-on to M7B) ---


def _cleaning_decisions_from_orm(row: CleaningDecisionsModel) -> CleaningDecisions:
    return CleaningDecisions(
        cleaning_decisions_id=row.cleaning_decisions_id,
        cleaning_plan_id=row.cleaning_plan_id,
        decided_by_user_id=row.decided_by_user_id,
        decisions_json=CleaningDecisionsJson.model_validate(row.decisions_json or {}),
        created_at=row.created_at,
    )


class CleaningDecisionsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: CleaningDecisions) -> CleaningDecisions:
        row = CleaningDecisionsModel(
            cleaning_decisions_id=obj.cleaning_decisions_id,
            cleaning_plan_id=obj.cleaning_plan_id,
            decided_by_user_id=obj.decided_by_user_id,
            decisions_json=obj.decisions_json.model_dump(mode="json"),
            created_at=obj.created_at,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _cleaning_decisions_from_orm(merged)

    def get(self, cleaning_decisions_id: UUID) -> CleaningDecisions | None:
        row = self._session.get(CleaningDecisionsModel, cleaning_decisions_id)
        return _cleaning_decisions_from_orm(row) if row else None

    def list_by_plan(self, cleaning_plan_id: UUID) -> list[CleaningDecisions]:
        rows = (
            self._session.query(CleaningDecisionsModel)
            .filter(CleaningDecisionsModel.cleaning_plan_id == cleaning_plan_id)
            .all()
        )
        return [_cleaning_decisions_from_orm(r) for r in rows]


def _feature_decisions_from_orm(row: FeatureDecisionsModel) -> FeatureDecisions:
    return FeatureDecisions(
        feature_decisions_id=row.feature_decisions_id,
        feature_plan_id=row.feature_plan_id,
        decided_by_user_id=row.decided_by_user_id,
        decisions_json=FeatureDecisionsJson.model_validate(row.decisions_json or {}),
        created_at=row.created_at,
    )


class FeatureDecisionsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: FeatureDecisions) -> FeatureDecisions:
        row = FeatureDecisionsModel(
            feature_decisions_id=obj.feature_decisions_id,
            feature_plan_id=obj.feature_plan_id,
            decided_by_user_id=obj.decided_by_user_id,
            decisions_json=obj.decisions_json.model_dump(mode="json"),
            created_at=obj.created_at,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _feature_decisions_from_orm(merged)

    def get(self, feature_decisions_id: UUID) -> FeatureDecisions | None:
        row = self._session.get(FeatureDecisionsModel, feature_decisions_id)
        return _feature_decisions_from_orm(row) if row else None

    def list_by_plan(self, feature_plan_id: UUID) -> list[FeatureDecisions]:
        rows = (
            self._session.query(FeatureDecisionsModel)
            .filter(FeatureDecisionsModel.feature_plan_id == feature_plan_id)
            .all()
        )
        return [_feature_decisions_from_orm(r) for r in rows]


def _visualization_plan_from_orm(row: VisualizationPlanModel) -> VisualizationPlan:
    return VisualizationPlan(
        visualization_plan_id=row.visualization_plan_id,
        dataset_version_id=row.dataset_version_id,
        analysis_run_id=row.analysis_run_id,
        status=row.status,
        plan_json=VisualizationPlanJson.model_validate(row.plan_json or {}),
        created_at=row.created_at,
    )


def _visualization_result_from_orm(row: VisualizationResultModel) -> VisualizationResult:
    rj = row.result_json or {}
    return VisualizationResult(
        visualization_result_id=row.visualization_result_id,
        visualization_plan_id=row.visualization_plan_id,
        dataset_version_id=row.dataset_version_id,
        status=row.status,
        chart_specs=[ChartSpec.model_validate(s) for s in rj.get("chart_specs", [])],
        chart_results=[ChartExecutionResult.model_validate(r) for r in rj.get("chart_results", [])],
        created_at=row.created_at,
    )


class VisualizationPlanRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: VisualizationPlan) -> VisualizationPlan:
        row = VisualizationPlanModel(
            visualization_plan_id=obj.visualization_plan_id,
            dataset_version_id=obj.dataset_version_id,
            analysis_run_id=obj.analysis_run_id,
            status=str(obj.status),
            plan_json=obj.plan_json.model_dump(mode="json"),
            created_at=obj.created_at,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _visualization_plan_from_orm(merged)

    def get(self, visualization_plan_id: UUID) -> VisualizationPlan | None:
        row = self._session.get(VisualizationPlanModel, visualization_plan_id)
        return _visualization_plan_from_orm(row) if row else None

    def list_by_version(self, dataset_version_id: UUID) -> list[VisualizationPlan]:
        rows = (
            self._session.query(VisualizationPlanModel)
            .filter(VisualizationPlanModel.dataset_version_id == dataset_version_id)
            .all()
        )
        return [_visualization_plan_from_orm(r) for r in rows]


class VisualizationResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: VisualizationResult) -> VisualizationResult:
        row = VisualizationResultModel(
            visualization_result_id=obj.visualization_result_id,
            visualization_plan_id=obj.visualization_plan_id,
            dataset_version_id=obj.dataset_version_id,
            status=str(obj.status),
            result_json={
                "chart_specs": [s.model_dump(mode="json") for s in obj.chart_specs],
                "chart_results": [r.model_dump(mode="json") for r in obj.chart_results],
            },
            created_at=obj.created_at,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _visualization_result_from_orm(merged)

    def get(self, visualization_result_id: UUID) -> VisualizationResult | None:
        row = self._session.get(VisualizationResultModel, visualization_result_id)
        return _visualization_result_from_orm(row) if row else None

    def list_by_plan(self, visualization_plan_id: UUID) -> list[VisualizationResult]:
        rows = (
            self._session.query(VisualizationResultModel)
            .filter(VisualizationResultModel.visualization_plan_id == visualization_plan_id)
            .all()
        )
        return [_visualization_result_from_orm(r) for r in rows]


def _job_from_orm(row: JobModel) -> Job:
    return Job(
        job_id=row.job_id,
        workspace_id=row.workspace_id,
        dataset_id=row.dataset_id,
        input_dataset_version_id=row.input_dataset_version_id,
        job_type=row.job_type,
        status=row.status,
        payload_json=row.payload_json or {},
        result_type=row.result_type,
        result_id=row.result_id,
        output_dataset_version_id=row.output_dataset_version_id,
        error_message=row.error_message,
        progress_message=row.progress_message,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


class JobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: Job) -> Job:
        row = JobModel(
            job_id=obj.job_id,
            workspace_id=obj.workspace_id,
            dataset_id=obj.dataset_id,
            input_dataset_version_id=obj.input_dataset_version_id,
            job_type=str(obj.job_type),
            status=str(obj.status),
            payload_json=obj.payload_json,
            result_type=obj.result_type,
            result_id=obj.result_id,
            output_dataset_version_id=obj.output_dataset_version_id,
            error_message=obj.error_message,
            progress_message=obj.progress_message,
            created_at=obj.created_at,
            started_at=obj.started_at,
            completed_at=obj.completed_at,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _job_from_orm(merged)

    def get(self, job_id: UUID) -> Job | None:
        row = self._session.get(JobModel, job_id)
        return _job_from_orm(row) if row else None

    def list_by_dataset(self, dataset_id: UUID) -> list[Job]:
        rows = (
            self._session.query(JobModel)
            .filter(JobModel.dataset_id == dataset_id)
            .order_by(JobModel.created_at.desc())
            .all()
        )
        return [_job_from_orm(r) for r in rows]

    def list_by_workspace(self, workspace_id: UUID) -> list[Job]:
        rows = (
            self._session.query(JobModel)
            .filter(JobModel.workspace_id == workspace_id)
            .order_by(JobModel.created_at.desc())
            .all()
        )
        return [_job_from_orm(r) for r in rows]

    def claim_next_queued(self) -> Job | None:
        """Atomically claim the oldest queued job using SELECT FOR UPDATE SKIP LOCKED."""
        from sqlalchemy import text  # noqa: PLC0415
        row = (
            self._session.query(JobModel)
            .filter(JobModel.status == "queued")
            .order_by(JobModel.created_at)
            .with_for_update(skip_locked=True)
            .first()
        )
        if row is None:
            return None
        row.status = "running"
        from datetime import datetime, timezone  # noqa: PLC0415
        row.started_at = datetime.now(tz=timezone.utc)
        self._session.commit()
        return _job_from_orm(row)


def _saved_view_from_orm(row: SavedViewModel) -> SavedView:
    return SavedView(
        saved_view_id=row.saved_view_id,
        workspace_id=row.workspace_id,
        dataset_id=row.dataset_id,
        dataset_version_id=row.dataset_version_id,
        name=row.name,
        description=row.description,
        source_type=SavedViewSourceType(row.source_type),
        source_spec_json=row.source_spec_json or {},
        storage_backend=row.storage_backend,
        storage_bucket=row.storage_bucket,
        storage_path=row.storage_path,
        storage_format=row.storage_format,
        row_count=row.row_count,
        column_count=row.column_count,
        created_at=row.created_at,
        created_by_user_id=row.created_by_user_id,
        metadata_json=row.metadata_json or {},
    )


class SavedViewRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: SavedView) -> SavedView:
        row = SavedViewModel(
            saved_view_id=obj.saved_view_id,
            workspace_id=obj.workspace_id,
            dataset_id=obj.dataset_id,
            dataset_version_id=obj.dataset_version_id,
            name=obj.name,
            description=obj.description,
            source_type=str(obj.source_type),
            source_spec_json=obj.source_spec_json,
            storage_backend=obj.storage_backend,
            storage_bucket=obj.storage_bucket,
            storage_path=obj.storage_path,
            storage_format=obj.storage_format,
            row_count=obj.row_count,
            column_count=obj.column_count,
            created_at=obj.created_at,
            created_by_user_id=obj.created_by_user_id,
            metadata_json=obj.metadata_json,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _saved_view_from_orm(merged)

    def get(self, saved_view_id: UUID) -> SavedView | None:
        row = self._session.get(SavedViewModel, saved_view_id)
        return _saved_view_from_orm(row) if row else None

    def list_by_version(self, dataset_version_id: UUID) -> list[SavedView]:
        rows = (
            self._session.query(SavedViewModel)
            .filter(SavedViewModel.dataset_version_id == dataset_version_id)
            .order_by(SavedViewModel.created_at.desc())
            .all()
        )
        return [_saved_view_from_orm(r) for r in rows]

    def list_by_dataset(self, dataset_id: UUID) -> list[SavedView]:
        rows = (
            self._session.query(SavedViewModel)
            .filter(SavedViewModel.dataset_id == dataset_id)
            .order_by(SavedViewModel.created_at.desc())
            .all()
        )
        return [_saved_view_from_orm(r) for r in rows]

    def delete(self, saved_view_id: UUID) -> bool:
        row = self._session.get(SavedViewModel, saved_view_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True


def _saved_visual_from_orm(row: SavedVisualModel) -> SavedVisual:
    return SavedVisual(
        visual_id=row.visual_id,
        workspace_id=row.workspace_id,
        dataset_id=row.dataset_id,
        dataset_version_id=row.dataset_version_id,
        title=row.title,
        description=row.description,
        chart_type=row.chart_type,
        chart_spec_json=row.chart_spec_json or {},
        source_type=SavedVisualSourceType(row.source_type),
        source_visualization_result_id=row.source_visualization_result_id,
        source_view_id=row.source_view_id,
        source_spec_json=row.source_spec_json or {},
        data_storage_backend=row.data_storage_backend,
        data_storage_bucket=row.data_storage_bucket,
        data_storage_path=row.data_storage_path,
        created_at=row.created_at,
        created_by_user_id=row.created_by_user_id,
        metadata_json=row.metadata_json or {},
    )


class SavedVisualRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, obj: SavedVisual) -> SavedVisual:
        row = SavedVisualModel(
            visual_id=obj.visual_id,
            workspace_id=obj.workspace_id,
            dataset_id=obj.dataset_id,
            dataset_version_id=obj.dataset_version_id,
            title=obj.title,
            description=obj.description,
            chart_type=obj.chart_type,
            chart_spec_json=obj.chart_spec_json,
            source_type=str(obj.source_type),
            source_visualization_result_id=obj.source_visualization_result_id,
            source_view_id=obj.source_view_id,
            source_spec_json=obj.source_spec_json,
            data_storage_backend=obj.data_storage_backend,
            data_storage_bucket=obj.data_storage_bucket,
            data_storage_path=obj.data_storage_path,
            created_at=obj.created_at,
            created_by_user_id=obj.created_by_user_id,
            metadata_json=obj.metadata_json,
        )
        merged = self._session.merge(row)
        self._session.commit()
        return _saved_visual_from_orm(merged)

    def get(self, visual_id: UUID) -> SavedVisual | None:
        row = self._session.get(SavedVisualModel, visual_id)
        return _saved_visual_from_orm(row) if row else None

    def list_by_version(self, dataset_version_id: UUID) -> list[SavedVisual]:
        rows = (
            self._session.query(SavedVisualModel)
            .filter(SavedVisualModel.dataset_version_id == dataset_version_id)
            .order_by(SavedVisualModel.created_at.desc())
            .all()
        )
        return [_saved_visual_from_orm(r) for r in rows]

    def list_by_dataset(self, dataset_id: UUID) -> list[SavedVisual]:
        rows = (
            self._session.query(SavedVisualModel)
            .filter(SavedVisualModel.dataset_id == dataset_id)
            .order_by(SavedVisualModel.created_at.desc())
            .all()
        )
        return [_saved_visual_from_orm(r) for r in rows]

    def delete(self, visual_id: UUID) -> bool:
        row = self._session.get(SavedVisualModel, visual_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True
