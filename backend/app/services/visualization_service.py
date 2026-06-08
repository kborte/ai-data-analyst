"""
VisualizationService: creates visualization plans, validates decisions, generates chart specs.

No LLM calls. Input data never mutated. No new DatasetVersion is created.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd

from app.repositories.memory import (
    DataProfileRepository,
    DatasetTableRepository,
    VisualizationPlanRepository,
    VisualizationResultRepository,
)
from app.schemas.common import ArtifactStatus, UserDecision
from app.schemas.visualization import (
    VisualizationDecisionItem,
    VisualizationDecisions,
    VisualizationPlan,
    VisualizationPlanJson,
    VisualizationResult,
)
from app.tools.charts.chart_executor import ChartExecutor
from app.tools.charts.chart_planner import ChartPlanner

_EXCEL_EXTS = {".xlsx", ".xls"}


@dataclass
class DecisionValidation:
    can_generate: bool
    total_charts: int
    approved_charts: int
    rejected_charts: int
    blocked_charts: int


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


class VisualizationService:
    def __init__(
        self,
        profile_repo: DataProfileRepository,
        table_repo: DatasetTableRepository,
        plan_repo: VisualizationPlanRepository,
        result_repo: VisualizationResultRepository,
    ) -> None:
        self._profiles = profile_repo
        self._tables = table_repo
        self._plans = plan_repo
        self._results = result_repo

    def create_visualization_plan(
        self, profile_id: UUID, dataset_version_id: UUID
    ) -> VisualizationPlan:
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise ValueError(f"DataProfile {profile_id} not found")
        suggestions = ChartPlanner().suggest(profile)
        plan = VisualizationPlan(
            visualization_plan_id=uuid4(),
            dataset_version_id=dataset_version_id,
            status=ArtifactStatus.completed,
            plan_json=VisualizationPlanJson(suggestions=suggestions),
            created_at=datetime.now(tz=UTC),
        )
        return self._plans.save(plan)

    def validate_decisions(
        self,
        visualization_plan_id: UUID,
        decision_items: list[VisualizationDecisionItem],
    ) -> DecisionValidation:
        plan = self._plans.get(visualization_plan_id)
        if plan is None:
            raise ValueError(f"VisualizationPlan {visualization_plan_id} not found")
        decision_map = {d.visualization_id: d for d in decision_items}
        suggestions = plan.plan_json.suggestions
        blocked = [
            s for s in suggestions
            if s.requires_human_approval and s.visualization_id not in decision_map
        ]
        approved = [
            s for s in suggestions
            if s.visualization_id in decision_map
            and decision_map[s.visualization_id].decision == UserDecision.approve
        ]
        rejected = [
            s for s in suggestions
            if s.visualization_id in decision_map
            and decision_map[s.visualization_id].decision != UserDecision.approve
        ]
        return DecisionValidation(
            can_generate=len(blocked) == 0,
            total_charts=len(suggestions),
            approved_charts=len(approved),
            rejected_charts=len(rejected),
            blocked_charts=len(blocked),
        )

    def generate(
        self,
        plan_id: UUID,
        decisions: VisualizationDecisions,
    ) -> VisualizationResult:
        plan = self._plans.get(plan_id)
        if plan is None:
            raise ValueError(f"VisualizationPlan {plan_id} not found")

        decision_map = {d.visualization_id: d for d in decisions.decisions_json.decisions}
        blocked = [
            s for s in plan.plan_json.suggestions
            if s.requires_human_approval and s.visualization_id not in decision_map
        ]
        if blocked:
            raise ValueError(f"Generation blocked: {len(blocked)} chart(s) require a decision")

        approved = [
            s for s in plan.plan_json.suggestions
            if s.visualization_id in decision_map
            and decision_map[s.visualization_id].decision == UserDecision.approve
        ]

        table_metas = self._tables.list_by_version(plan.dataset_version_id)
        if not table_metas:
            raise ValueError(f"No tables found for version {plan.dataset_version_id}")

        tables: dict[str, pd.DataFrame] = {}
        for tm in table_metas:
            if not tm.storage_path:
                raise ValueError(f"Table '{tm.table_name}' has no storage path")
            tables[tm.table_name] = _load_df(tm.storage_path)

        chart_results = ChartExecutor().execute(tables, approved)
        chart_specs = [r.chart_spec for r in chart_results if r.chart_spec is not None]

        result = VisualizationResult(
            visualization_result_id=uuid4(),
            visualization_plan_id=plan_id,
            dataset_version_id=plan.dataset_version_id,
            status=ArtifactStatus.completed,
            chart_specs=chart_specs,
            chart_results=chart_results,
            created_at=datetime.now(tz=UTC),
        )
        return self._results.save(result)
