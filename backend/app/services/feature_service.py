"""
FeatureService: creates feature plans, validates decisions, executes approved features.

No LLM calls. No arbitrary code execution. Input data never mutated.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd

from app.repositories.memory import (
    DataProfileRepository,
    DatasetTableRepository,
    DatasetVersionRepository,
    FeaturePlanRepository,
    FeatureResultRepository,
)
from app.schemas.common import ArtifactStatus, DatasetVersionType, ExecutionStatus, UserDecision
from app.schemas.dataset import DatasetTable, DatasetVersion
from app.schemas.features import (
    FeatureDecisionItem,
    FeatureDecisions,
    FeatureExecutionLogJson,
    FeaturePlan,
    FeaturePlanJson,
    FeatureResult,
)
from app.tools.data.feature_executor import execute_features
from app.tools.data.feature_planner import generate_feature_suggestions
from app.tools.files.storage import build_cleaned_table_path, save_cleaned_table

_EXCEL_EXTS = {".xlsx", ".xls"}


@dataclass
class DecisionValidation:
    can_execute: bool
    total_features: int
    approved_features: int
    rejected_features: int
    blocked_features: int


def _load_df(storage_path: str) -> pd.DataFrame:
    p = Path(storage_path)
    if not p.exists():
        raise FileNotFoundError(f"Storage file not found: {storage_path}")
    ext = p.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(p)
    if ext in _EXCEL_EXTS:
        return pd.read_excel(p, engine="openpyxl")
    raise ValueError(f"Unsupported file type: {ext!r}")


def _next_version_number(dataset_id: UUID, version_repo: DatasetVersionRepository) -> int:
    existing = version_repo.list_by_dataset(dataset_id)
    return max((v.version_number for v in existing), default=0) + 1


class FeatureService:
    def __init__(
        self,
        profile_repo: DataProfileRepository,
        version_repo: DatasetVersionRepository,
        table_repo: DatasetTableRepository,
        plan_repo: FeaturePlanRepository,
        result_repo: FeatureResultRepository,
    ) -> None:
        self._profiles = profile_repo
        self._versions = version_repo
        self._tables = table_repo
        self._plans = plan_repo
        self._results = result_repo

    def create_feature_plan(self, profile_id: UUID, dataset_version_id: UUID) -> FeaturePlan:
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise ValueError(f"DataProfile {profile_id} not found")
        features = generate_feature_suggestions(profile)
        plan = FeaturePlan(
            feature_plan_id=uuid4(),
            dataset_version_id=dataset_version_id,
            status=ArtifactStatus.completed,
            plan_json=FeaturePlanJson(features=features),
            created_at=datetime.now(tz=UTC),
        )
        return self._plans.save(plan)

    def validate_decisions(
        self, feature_plan_id: UUID, decision_items: list[FeatureDecisionItem]
    ) -> DecisionValidation:
        plan = self._plans.get(feature_plan_id)
        if plan is None:
            raise ValueError(f"FeaturePlan {feature_plan_id} not found")
        decision_map = {d.feature_id: d for d in decision_items}
        features = plan.plan_json.features
        blocked = [f for f in features if f.requires_human_approval and f.feature_id not in decision_map]
        approved = [
            f for f in features
            if f.feature_id in decision_map
            and decision_map[f.feature_id].decision == UserDecision.approve
        ]
        rejected = [
            f for f in features
            if f.feature_id in decision_map
            and decision_map[f.feature_id].decision != UserDecision.approve
        ]
        return DecisionValidation(
            can_execute=len(blocked) == 0,
            total_features=len(features),
            approved_features=len(approved),
            rejected_features=len(rejected),
            blocked_features=len(blocked),
        )

    def execute_feature_plan(
        self,
        workspace_id: UUID,
        dataset_id: UUID,
        input_dataset_version_id: UUID,
        feature_plan_id: UUID,
        decisions: FeatureDecisions,
        executed_by_user_id: UUID,
    ) -> FeatureResult:
        plan = self._plans.get(feature_plan_id)
        if plan is None:
            raise ValueError(f"FeaturePlan {feature_plan_id} not found")

        input_version = self._versions.get(input_dataset_version_id)
        if input_version is None:
            raise ValueError(f"DatasetVersion {input_dataset_version_id} not found")

        decision_map = {d.feature_id: d for d in decisions.decisions_json.decisions}
        blocked = [
            f for f in plan.plan_json.features
            if f.requires_human_approval and f.feature_id not in decision_map
        ]
        if blocked:
            raise ValueError(f"Execution blocked: {len(blocked)} feature(s) require a decision")

        approved_features = [
            f for f in plan.plan_json.features
            if f.feature_id in decision_map
            and decision_map[f.feature_id].decision == UserDecision.approve
        ]

        table_metas = self._tables.list_by_version(input_dataset_version_id)
        if not table_metas:
            raise ValueError(f"No tables found for version {input_dataset_version_id}")

        tables: dict[str, pd.DataFrame] = {}
        for tm in table_metas:
            if not tm.storage_path:
                raise ValueError(f"Table '{tm.table_name}' has no storage path")
            tables[tm.table_name] = _load_df(tm.storage_path)

        exec_result = execute_features(tables, approved_features)
        completed_at = datetime.now(tz=UTC)

        out_version_id = uuid4()
        all_out_tables = {**exec_result.tables, **exec_result.new_tables}
        for table_name, df in all_out_tables.items():
            csv_bytes = df.to_csv(index=False).encode()
            save_cleaned_table(workspace_id, dataset_id, out_version_id, table_name, csv_bytes)
            path = build_cleaned_table_path(workspace_id, dataset_id, out_version_id, table_name)
            self._tables.save(DatasetTable(
                table_id=uuid4(),
                dataset_version_id=out_version_id,
                table_name=table_name,
                storage_path=str(path),
                row_count=len(df),
                column_count=len(df.columns),
            ))

        next_num = _next_version_number(dataset_id, self._versions)
        out_version = DatasetVersion(
            dataset_version_id=out_version_id,
            dataset_id=dataset_id,
            parent_version_id=input_dataset_version_id,
            version_number=next_num,
            version_type=DatasetVersionType.enriched,
            display_name="Enriched data",
            description="Created by applying approved feature definitions",
            row_count=sum(len(df) for df in exec_result.tables.values()),
            column_count=max((len(df.columns) for df in exec_result.tables.values()), default=0),
            created_by_user_id=executed_by_user_id,
            created_at=completed_at,
        )
        self._versions.save(out_version)

        features_added: list[str] = []
        log_entries: list[dict] = []
        errors: list[str] = []
        for sr in exec_result.step_results:
            features_added.extend(sr.output_columns)
            if sr.output_table:
                features_added.append(sr.output_table)
            log_entries.append({
                "feature_id": str(sr.feature_id),
                "feature_name": sr.feature_name,
                "status": sr.status,
                "output_columns": sr.output_columns,
                "output_table": sr.output_table,
                "error": sr.error,
            })
            if sr.status == ExecutionStatus.failed and sr.error:
                errors.append(sr.error)

        result = FeatureResult(
            feature_result_id=uuid4(),
            feature_plan_id=feature_plan_id,
            feature_decisions_id=decisions.feature_decisions_id,
            input_dataset_version_id=input_dataset_version_id,
            output_dataset_version_id=out_version_id,
            status=ArtifactStatus.completed,
            features_added=features_added,
            execution_log_json=FeatureExecutionLogJson(
                feature_results=log_entries,
                errors=errors,
            ),
            created_at=completed_at,
        )
        return self._results.save(result)
