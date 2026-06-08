"""
CleaningExecutionService: resolves decisions, executes cleaning, creates cleaned DatasetVersion.

No LLM calls. No in-place mutation of original data.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd

from app.repositories.memory import (
    CleaningPlanRepository,
    CleaningResultRepository,
    DatasetTableRepository,
    DatasetVersionRepository,
)
from app.schemas.cleaning import (
    CleaningDecisions,
    CleaningExecutionLogJson,
    CleaningExecutionSummary,
    CleaningResult,
    CleaningStepResult,
)
from app.schemas.common import ArtifactStatus, DatasetVersionType, ExecutionStatus
from app.schemas.dataset import DatasetTable, DatasetVersion
from app.tools.data.cleaning_decision_resolver import resolve_decisions
from app.tools.data.cleaning_executor import ExecutionResult, StepExecutionResult, execute_cleaning
from app.tools.files.storage import save_cleaned_table

_EXCEL_EXTS = {".xlsx", ".xls"}


def _load_df(storage_path: str, table_name: str) -> pd.DataFrame:
    p = Path(storage_path)
    if not p.exists():
        raise FileNotFoundError(f"Storage file not found: {storage_path}")
    ext = p.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(p)
    if ext in _EXCEL_EXTS:
        return pd.read_excel(p, sheet_name=table_name, engine="openpyxl")
    raise ValueError(f"Unsupported file type: {ext!r}")


def _next_version_number(dataset_id: UUID, version_repo: DatasetVersionRepository) -> int:
    existing = version_repo.list_by_dataset(dataset_id)
    return max((v.version_number for v in existing), default=0) + 1


def _map_step_result(sr: StepExecutionResult) -> CleaningStepResult:
    return CleaningStepResult(
        step_id=sr.step_id,
        status=sr.status,
        rows_affected=sr.rows_removed if sr.rows_removed else None,
        error_message=sr.error,
    )


def _build_summary(step_results: list[StepExecutionResult], exec_result: ExecutionResult) -> CleaningExecutionSummary:
    executed = sum(1 for s in step_results if s.status == ExecutionStatus.success)
    skipped = sum(1 for s in step_results if s.status == ExecutionStatus.skipped)
    failed = sum(1 for s in step_results if s.status == ExecutionStatus.failed)
    rows_before = sum(s.rows_before for s in step_results if s.rows_before)
    rows_after_total = sum(len(df) for df in exec_result.tables.values())
    rows_removed = sum(s.rows_removed for s in step_results)
    cols: list[str] = []
    seen: set[str] = set()
    for s in step_results:
        for c in s.columns_changed:
            if c not in seen:
                cols.append(c)
                seen.add(c)
    return CleaningExecutionSummary(
        total_steps=len(step_results),
        executed_steps=executed,
        skipped_steps=skipped,
        failed_steps=failed,
        rows_before=rows_before,
        rows_after=rows_after_total,
        rows_removed=rows_removed,
        columns_changed=cols,
    )


class CleaningExecutionService:
    def __init__(
        self,
        version_repo: DatasetVersionRepository,
        table_repo: DatasetTableRepository,
        plan_repo: CleaningPlanRepository,
        result_repo: CleaningResultRepository,
    ) -> None:
        self._versions = version_repo
        self._tables = table_repo
        self._plans = plan_repo
        self._results = result_repo

    def execute_cleaning_plan(
        self,
        workspace_id: UUID,
        dataset_id: UUID,
        input_dataset_version_id: UUID,
        cleaning_plan_id: UUID,
        decisions: CleaningDecisions,
        executed_by_user_id: UUID,
    ) -> CleaningResult:
        # 1. Retrieve and validate input version
        input_version = self._versions.get(input_dataset_version_id)
        if input_version is None:
            raise ValueError(f"DatasetVersion {input_dataset_version_id} not found")
        if input_version.dataset_id != dataset_id:
            raise ValueError("DatasetVersion does not belong to given dataset")

        # 2. Retrieve and validate plan
        plan = self._plans.get(cleaning_plan_id)
        if plan is None:
            raise ValueError(f"CleaningPlan {cleaning_plan_id} not found")
        if plan.dataset_version_id != input_dataset_version_id:
            raise ValueError("CleaningPlan does not belong to given dataset version")

        # 3. Resolve decisions
        resolution = resolve_decisions(plan, decisions.decisions_json)
        started_at = datetime.now(tz=UTC)

        if not resolution.summary.can_execute:
            raise ValueError(
                f"Execution blocked: {resolution.summary.blocked_steps} step(s) require approval"
            )

        # 4. Load original tables
        orig_tables_meta = self._tables.list_by_version(input_dataset_version_id)
        if not orig_tables_meta:
            raise ValueError(f"No tables found for version {input_dataset_version_id}")

        tables: dict[str, pd.DataFrame] = {}
        for tm in orig_tables_meta:
            if not tm.storage_path:
                raise ValueError(f"Table '{tm.table_name}' has no storage path")
            tables[tm.table_name] = _load_df(tm.storage_path, tm.table_name)

        # 5. Execute cleaning
        exec_result = execute_cleaning(tables, resolution.resolutions)
        completed_at = datetime.now(tz=UTC)

        step_results = exec_result.step_results
        any_failed = any(s.status == ExecutionStatus.failed for s in step_results)
        run_id = uuid4()

        if any_failed:
            log = self._build_log(
                run_id, cleaning_plan_id, input_dataset_version_id, None,
                started_at, completed_at, step_results, exec_result, failed=True,
            )
            result = CleaningResult(
                cleaning_result_id=uuid4(),
                cleaning_plan_id=cleaning_plan_id,
                cleaning_decisions_id=decisions.cleaning_decisions_id,
                input_dataset_version_id=input_dataset_version_id,
                output_dataset_version_id=None,
                status=ArtifactStatus.failed,
                execution_log_json=log,
                created_at=completed_at,
            )
            return self._results.save(result)

        # 6. Persist cleaned tables and create new version
        out_version_id = uuid4()
        for table_name, df in exec_result.tables.items():
            csv_bytes = df.to_csv(index=False).encode()
            save_cleaned_table(workspace_id, dataset_id, out_version_id, table_name, csv_bytes)

        total_rows = sum(len(df) for df in exec_result.tables.values())
        total_cols = max((len(df.columns) for df in exec_result.tables.values()), default=0)
        next_num = _next_version_number(dataset_id, self._versions)

        out_version = DatasetVersion(
            dataset_version_id=out_version_id,
            dataset_id=dataset_id,
            parent_version_id=input_dataset_version_id,
            version_number=next_num,
            version_type=DatasetVersionType.cleaned,
            display_name="Cleaned data",
            description="Created by applying approved cleaning steps",
            row_count=total_rows,
            column_count=total_cols,
            created_by_user_id=executed_by_user_id,
            created_at=completed_at,
        )
        self._versions.save(out_version)

        for table_name, df in exec_result.tables.items():
            from app.tools.files.storage import build_cleaned_table_path
            path = build_cleaned_table_path(workspace_id, dataset_id, out_version_id, table_name)
            self._tables.save(DatasetTable(
                table_id=uuid4(),
                dataset_version_id=out_version_id,
                table_name=table_name,
                storage_path=str(path),
                row_count=len(df),
                column_count=len(df.columns),
            ))

        log = self._build_log(
            run_id, cleaning_plan_id, input_dataset_version_id, out_version_id,
            started_at, completed_at, step_results, exec_result, failed=False,
        )
        result = CleaningResult(
            cleaning_result_id=uuid4(),
            cleaning_plan_id=cleaning_plan_id,
            cleaning_decisions_id=decisions.cleaning_decisions_id,
            input_dataset_version_id=input_dataset_version_id,
            output_dataset_version_id=out_version_id,
            status=ArtifactStatus.completed,
            row_count_before=sum(len(t) for t in tables.values()),
            row_count_after=total_rows,
            execution_log_json=log,
            created_at=completed_at,
        )
        return self._results.save(result)

    @staticmethod
    def _build_log(
        run_id: UUID,
        plan_id: UUID,
        in_vid: UUID,
        out_vid: UUID | None,
        started_at: datetime,
        completed_at: datetime,
        step_results: list[StepExecutionResult],
        exec_result: ExecutionResult,
        *,
        failed: bool,
    ) -> CleaningExecutionLogJson:
        summary = _build_summary(step_results, exec_result)
        return CleaningExecutionLogJson(
            cleaning_run_id=run_id,
            cleaning_plan_id=plan_id,
            input_dataset_version_id=in_vid,
            output_dataset_version_id=out_vid,
            started_at=started_at,
            completed_at=completed_at,
            summary=summary,
            step_results=[_map_step_result(s) for s in step_results],
            errors=["One or more steps failed"] if failed else [],
        )
