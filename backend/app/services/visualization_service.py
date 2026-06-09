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
from app.schemas.profile import DataProfile
from app.schemas.visualization import (
    VisualizationDecisionItem,
    VisualizationDecisions,
    VisualizationPlan,
    VisualizationPlanJson,
    VisualizationResult,
)
from app.tools.charts.chart_executor import ChartExecutor
from app.tools.charts.chart_planner import ChartPlanner
from app.tools.llm.prompts import CHART_SUGGEST_SCHEMA, chart_suggest_prompt
from app.tools.llm.provider import FakeLLMProvider, LLMProvider

_EXCEL_EXTS = {".xlsx", ".xls"}
# LLM only called when deterministic planner produces fewer than this many suggestions.
_LLM_CHART_THRESHOLD = 3


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


def _llm_chart_suggestions(
    profile: DataProfile,
    existing: list,
    llm: LLMProvider,
) -> list:
    """ONE LLM call: add charts for patterns the heuristic rules didn't cover."""
    from uuid import uuid4  # noqa: PLC0415
    from app.schemas.common import ChartType  # noqa: PLC0415

    existing_titles = [s.title for s in existing]
    prompt = chart_suggest_prompt(profile, existing_titles)
    result = llm.complete_structured(prompt, "suggest_charts", CHART_SUGGEST_SCHEMA)

    valid_cols = {c.column_name for c in profile.column_profiles}
    from app.schemas.visualization import ChartSuggestion  # noqa: PLC0415
    added = []
    for item in result.get("charts", []):
        x_col = item.get("x_column", "")
        if x_col not in valid_cols:
            continue  # hallucinated column — skip
        y_col = item.get("y_column")
        if y_col and y_col not in valid_cols:
            y_col = None
        try:
            chart_type = ChartType(item["chart_type"])
        except (KeyError, ValueError):
            continue
        added.append(ChartSuggestion(
            visualization_id=uuid4(),
            title=item.get("title", ""),
            description=item.get("description", ""),
            chart_type=chart_type,
            input_table=profile.table_name,
            x_column=x_col,
            y_column=y_col,
            aggregation=item.get("aggregation"),
            user_facing_explanation=item.get("user_facing_explanation", ""),
            requires_human_approval=True,
        ))
    return added


class VisualizationService:
    def __init__(
        self,
        profile_repo: DataProfileRepository,
        table_repo: DatasetTableRepository,
        plan_repo: VisualizationPlanRepository,
        result_repo: VisualizationResultRepository,
        llm: LLMProvider | None = None,
    ) -> None:
        self._profiles = profile_repo
        self._tables = table_repo
        self._plans = plan_repo
        self._results = result_repo
        self._llm = llm or FakeLLMProvider()

    def create_visualization_plan(
        self, profile_id: UUID, dataset_version_id: UUID
    ) -> VisualizationPlan:
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise ValueError(f"DataProfile {profile_id} not found")
        suggestions = ChartPlanner().suggest(profile)

        if self._llm.is_available() and len(suggestions) < _LLM_CHART_THRESHOLD:
            suggestions = suggestions + _llm_chart_suggestions(profile, suggestions, self._llm)
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
