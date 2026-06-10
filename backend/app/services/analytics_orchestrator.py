"""Analytics workflow orchestrator — LangGraph StateGraph implementation.

Intent-aware graph topology
---------------------------
Cleaning always runs first, regardless of whether the user asked for
analysis, visualization, or explicit cleaning.  After cleaning, the
graph routes to the correct terminal based on the detected intent.

START → router
  router(start)                          → classify_intent
  router(awaiting_cleaning_approval + decisions) → execute_cleaning
  router(awaiting_cleaning_approval, no decisions) → profile_and_plan   # re-emit

  classify_intent  → profile_and_plan   (always — cleaning is mandatory first step)

  profile_and_plan(items)               → pause_cleaning  → END  (NeedsApprovalResponse)
  profile_and_plan(no items, clean)     → cleaning_result → END  (AnalysisResultResponse: preview)
  profile_and_plan(no items, analyze)   → analyze         → END  (AnalysisResultResponse)
  profile_and_plan(error)               → END             (NeedsClarificationResponse)

  execute_cleaning(success, clean)   → cleaning_result → END
  execute_cleaning(success, analyze) → analyze         → END
  execute_cleaning(error)            → END

  cleaning_result → END
  analyze         → END

Human-in-the-loop is stateless: WorkflowState is serialized into
NeedsApprovalResponse, returned to the client, echoed back on the next
request.  The router re-enters the graph at the correct node.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph

from app.dependencies import Repos
from app.schemas.analytics import (
    AnalyticsIntent,
    AnalyticsOutput,
    PriorOutputRef,
    RecentMessage,
    TableOutput,
    TextOutput,
)
from app.schemas.analytics_context import DatasetContext
from app.schemas.cleaning import (
    CleaningDecisionItem,
    CleaningDecisions,
    CleaningDecisionsJson,
)
from app.schemas.dataset import DatasetTable
from app.schemas.workflow import (
    AnalysisResultResponse,
    ApprovalItem,
    NeedsApprovalResponse,
    NeedsClarificationResponse,
    WorkflowIntent,
    WorkflowResponse,
    WorkflowStage,
    WorkflowState,
)
from app.services.analytics_context import build_dataset_context
from app.services.analytics_planner import AnalyticsPlanner
from app.services.cleaning_execution_service import CleaningExecutionService
from app.services.cleaning_plan_service import CleaningPlanService
from app.services.profiling_service import create_profiles
from app.tools.data.duckdb_service import (
    get_table_info,
    list_tables,
    read_preview,
    temp_duckdb_path,
)
from app.tools.files.storage_service import StorageBackend
from app.tools.llm.provider import FakeLLMProvider, LLMProvider
from app.tools.llm.prompts import analytics_text_answer_prompt

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

_CLEAN_KEYWORDS = frozenset({
    "clean", "fix", "correct", "standardize", "standardise",
    "dedupe", "deduplicate", "duplicate", "missing", "null", "nulls",
    "outlier", "outliers", "impute", "normalize", "normalise",
    "scrub", "format", "typo", "typos", "blank", "blanks",
    "remove duplicates", "fill missing", "data quality",
})

# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------


class WorkflowGraphState(TypedDict):
    # ── fixed inputs ──────────────────────────────────────────────────────
    question: str
    dataset_id: UUID
    workspace_id: UUID | None
    cleaning_decisions: list[CleaningDecisionItem]
    recent_messages: list[RecentMessage]
    prior_output_refs: list[PriorOutputRef]

    # ── mutable during the run ────────────────────────────────────────────
    workflow_stage: str      # WorkflowStage value
    workflow_intent: str     # WorkflowIntent value
    active_version_id: UUID
    profile_id: UUID | None
    cleaning_plan_id: UUID | None
    resolved_version_id: UUID | None

    # cleaning approval items computed in profile_and_plan
    cleaning_approval_items: list[ApprovalItem]

    # ── terminal output ───────────────────────────────────────────────────
    response: WorkflowResponse | None


# ---------------------------------------------------------------------------
# Stateless helpers
# ---------------------------------------------------------------------------

def _classify_question(question: str) -> WorkflowIntent:
    q = question.lower()
    if any(kw in q for kw in _CLEAN_KEYWORDS):
        return WorkflowIntent.clean
    return WorkflowIntent.analyze


def _build_cleaning_approval_items(plan: Any) -> list[ApprovalItem]:
    items: list[ApprovalItem] = []
    for step in plan.plan_json.steps:
        if step.recommendation.requires_human_approval:
            col = step.issue.column_name or "table"
            items.append(ApprovalItem(
                id=str(step.step_id),
                title=f"{step.issue.issue_type} in '{col}'",
                description=(
                    f"{step.issue.affected_rows_percent:.1f}% of rows affected. "
                    f"{step.recommendation.rationale}"
                ),
                recommended_action=step.recommendation.recommended_action,
                details=f"Operation: {step.operation.operation_type}",
                default_decision="approve",
            ))
    return items


def _ensure_tables_registered(
    version_id: UUID,
    storage_path: str,
    repos: Repos,
    storage: StorageBackend,
) -> None:
    if repos.dataset_table.list_by_version(version_id):
        return
    with temp_duckdb_path() as tmp:
        tmp.write_bytes(storage.read(storage_path))
        for tname in list_tables(tmp):
            info = get_table_info(tmp, tname)
            repos.dataset_table.save(DatasetTable(
                table_id=uuid.uuid4(),
                dataset_version_id=version_id,
                table_name=tname,
                row_count=info.row_count,
                column_count=info.column_count,
            ))


def _version_label(version: Any) -> str:
    display = version.display_name or ""
    num = getattr(version, "version_number", None)
    if display:
        return f"v{num} – {display}" if num else display
    return f"v{num}" if num else str(version.dataset_version_id)[:8]


def _current_workflow_state(gs: WorkflowGraphState) -> WorkflowState:
    return WorkflowState(
        workspace_id=gs["workspace_id"],
        dataset_id=gs["dataset_id"],
        dataset_version_id=gs["active_version_id"],
        question=gs["question"],
        stage=WorkflowStage(gs["workflow_stage"]),
        intent=WorkflowIntent(gs["workflow_intent"]),
        profile_id=gs.get("profile_id"),
        cleaning_plan_id=gs.get("cleaning_plan_id"),
        resolved_version_id=gs.get("resolved_version_id"),
    )


def _interpretation(
    outputs: list[AnalyticsOutput],
    context: DatasetContext,
    question: str,
    llm: LLMProvider,
) -> str:
    if not llm.is_available():
        return "Generated the requested analysis. Review the results below."
    summaries: list[str] = []
    for out in outputs:
        otype = getattr(out, "output_type", "unknown")
        if otype == "table":
            header = f"Table '{out.title}': {out.row_count} rows, columns: {', '.join(out.columns[:8])}"
            # Include up to 5 result rows so the LLM can reference actual values.
            if getattr(out, "preview_rows", None):
                sample = []
                for row in out.preview_rows[:5]:
                    sample.append(dict(zip(out.columns, row)))
                header += f"\nSample rows: {sample}"
            summaries.append(header)
        elif otype == "visual":
            summaries.append(f"Chart '{out.title}' ({out.chart_type})")
        elif otype == "text":
            summaries.append(f"Text answer: {out.content[:120]}")
    prompt = (
        analytics_text_answer_prompt(question, context)
        + "\n\nResults produced:\n"
        + "\n".join(f"- {s}" for s in summaries)
        + "\n\nIn 2–3 sentences, summarise what the results show and the key takeaway."
    )
    return llm.complete_text(prompt, max_tokens=200) or "Analysis complete. Review the results below."


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def _build_graph(repos: Repos, storage: StorageBackend, llm: LLMProvider) -> Any:

    # ── Node: router ──────────────────────────────────────────────────────
    def node_router(state: WorkflowGraphState) -> dict:
        return {}

    def _route_from_router(state: WorkflowGraphState) -> str:
        stage = state["workflow_stage"]
        if stage == WorkflowStage.awaiting_cleaning_approval:
            if state["cleaning_decisions"]:
                return "execute_cleaning"
            return "profile_and_plan"   # re-emit from existing plan
        return "classify_intent"        # start or unknown

    # ── Node: classify_intent ─────────────────────────────────────────────
    def node_classify_intent(state: WorkflowGraphState) -> dict:
        intent = _classify_question(state["question"])
        return {"workflow_intent": intent}

    # Cleaning always runs first — intent only controls what happens after.

    # ── Node: profile_and_plan ────────────────────────────────────────────
    def node_profile_and_plan(state: WorkflowGraphState) -> dict:
        version_id = state["active_version_id"]
        dataset_id = state["dataset_id"]

        profiles = repos.profile.list_by_version(version_id)
        if not profiles:
            version = repos.dataset_version.get(version_id)
            if version and version.storage_path:
                try:
                    _ensure_tables_registered(version_id, version.storage_path, repos, storage)
                except Exception:  # noqa: BLE001
                    pass
            try:
                profiles = create_profiles(
                    dataset_id=dataset_id,
                    dataset_version_id=version_id,
                    repos=repos,
                    storage=storage,
                )
            except LookupError as exc:
                return {
                    "response": NeedsClarificationResponse(
                        message=f"Cannot profile dataset: {exc}",
                        dataset_id=dataset_id,
                        dataset_version_id=version_id,
                    ),
                    "workflow_stage": WorkflowStage.complete,
                }

        profile = profiles[0]
        existing = repos.cleaning_plan.list_by_version(version_id)
        if existing:
            cleaning_plan = existing[-1]
        else:
            svc = CleaningPlanService(
                profile_repo=repos.profile,
                cleaning_plan_repo=repos.cleaning_plan,
                llm=llm,
            )
            cleaning_plan = svc.create_cleaning_plan(
                profile_id=profile.profile_id,
                dataset_version_id=version_id,
            )

        approval_items = _build_cleaning_approval_items(cleaning_plan)
        return {
            "profile_id": profile.profile_id,
            "cleaning_plan_id": cleaning_plan.cleaning_plan_id,
            "cleaning_approval_items": approval_items,
        }

    def _route_after_profile_and_plan(state: WorkflowGraphState) -> str:
        if state.get("response"):
            return END
        # Only pause for cleaning approval when the user explicitly asked to clean.
        # Analysis/visual requests skip the approval step and proceed to analyze.
        if (
            state.get("cleaning_approval_items")
            and state["workflow_intent"] == WorkflowIntent.clean
        ):
            return "pause_cleaning"
        # Route by intent (cleaning issues exist but user asked to analyze — skip them).
        if state["workflow_intent"] == WorkflowIntent.clean:
            return "cleaning_result"
        return "analyze"

    # ── Node: pause_cleaning ──────────────────────────────────────────────
    def node_pause_cleaning(state: WorkflowGraphState) -> dict:
        wf_state = _current_workflow_state(state)
        wf_state = wf_state.model_copy(update={"stage": WorkflowStage.awaiting_cleaning_approval})
        items = state.get("cleaning_approval_items") or []
        return {
            "workflow_stage": WorkflowStage.awaiting_cleaning_approval,
            "response": NeedsApprovalResponse(
                stage="cleaning",
                message=(
                    f"Found {len(items)} data quality issue(s) that need your review "
                    "before cleaning. Approve or reject each step."
                ),
                dataset_id=state["dataset_id"],
                dataset_version_id=state["active_version_id"],
                items=items,
                workflow_state=wf_state,
            ),
        }

    # ── Node: execute_cleaning ────────────────────────────────────────────
    def node_execute_cleaning(state: WorkflowGraphState) -> dict:
        dataset_id = state["dataset_id"]
        version_id = state["active_version_id"]
        cleaning_plan_id = state["cleaning_plan_id"]

        if not cleaning_plan_id:
            return {
                "response": NeedsClarificationResponse(
                    message="Workflow state is missing the cleaning plan ID. Please restart.",
                    dataset_id=dataset_id,
                    dataset_version_id=version_id,
                ),
                "workflow_stage": WorkflowStage.complete,
            }

        decisions_obj = CleaningDecisions(
            cleaning_decisions_id=uuid.uuid4(),
            cleaning_plan_id=cleaning_plan_id,
            decided_by_user_id=_SYSTEM_USER_ID,
            decisions_json=CleaningDecisionsJson(decisions=state["cleaning_decisions"]),
            created_at=datetime.now(tz=UTC),
        )
        # Must persist before execute — FK on cleaning_results.cleaning_decisions_id.
        repos.cleaning_decisions.save(decisions_obj)

        exec_svc = CleaningExecutionService(
            version_repo=repos.dataset_version,
            table_repo=repos.dataset_table,
            plan_repo=repos.cleaning_plan,
            result_repo=repos.cleaning_result,
            storage=storage,
        )
        try:
            result = exec_svc.execute_cleaning_plan(
                workspace_id=state["workspace_id"] or uuid.uuid4(),
                dataset_id=dataset_id,
                input_dataset_version_id=version_id,
                cleaning_plan_id=cleaning_plan_id,
                decisions=decisions_obj,
                executed_by_user_id=_SYSTEM_USER_ID,
            )
        except ValueError as exc:
            return {
                "response": NeedsClarificationResponse(
                    message=f"Cleaning execution failed: {exc}",
                    dataset_id=dataset_id,
                    dataset_version_id=version_id,
                ),
                "workflow_stage": WorkflowStage.complete,
            }

        new_version_id = result.output_dataset_version_id or version_id
        return {
            "active_version_id": new_version_id,
            "resolved_version_id": new_version_id,
            "cleaning_approval_items": [],
        }

    def _route_after_execute_cleaning(state: WorkflowGraphState) -> str:
        if state.get("response"):
            return END
        if state["workflow_intent"] == WorkflowIntent.clean:
            return "cleaning_result"
        return "analyze"

    # ── Node: cleaning_result ─────────────────────────────────────────────
    def node_cleaning_result(state: WorkflowGraphState) -> dict:
        """Terminal node for the cleaning flow.

        Fetches the first 15 rows of the cleaned (or current) version and
        produces a human-readable summary that names the saved version.
        """
        dataset_id = state["dataset_id"]
        version_id = state["active_version_id"]
        cleaning_decisions = state.get("cleaning_decisions") or []
        cleaning_plan_id = state.get("cleaning_plan_id")

        version = repos.dataset_version.get(version_id)
        if version is None or not version.storage_path:
            return {
                "response": NeedsClarificationResponse(
                    message="Dataset version has no stored artifact. Cannot show preview.",
                    dataset_id=dataset_id,
                    dataset_version_id=version_id,
                )
            }

        version_label = _version_label(version)
        was_cleaned = bool(state.get("resolved_version_id"))
        approved_ids = {d.step_id for d in cleaning_decisions if d.decision == "approve"}

        # ── Describe what was cleaned ──────────────────────────────────────
        step_descriptions: list[str] = []
        if approved_ids and cleaning_plan_id:
            # Look for the plan on the parent version (the pre-clean version).
            parent_vid = getattr(version, "parent_version_id", None)
            candidates = (
                repos.cleaning_plan.list_by_version(parent_vid)
                if parent_vid else []
            )
            if not candidates:
                candidates = repos.cleaning_plan.list_by_version(version_id)
            the_plan = next(
                (p for p in candidates if str(p.cleaning_plan_id) == str(cleaning_plan_id)),
                candidates[-1] if candidates else None,
            )
            if the_plan:
                for step in the_plan.plan_json.steps:
                    if str(step.step_id) in approved_ids:
                        col = step.issue.column_name or "table"
                        step_descriptions.append(
                            f"{step.recommendation.recommended_action} in '{col}'"
                        )

        if was_cleaned and step_descriptions:
            steps_text = "; ".join(step_descriptions)
            summary_text = (
                f"Applied {len(step_descriptions)} cleaning step(s): {steps_text}. "
                f"The cleaned dataset has been saved as **{version_label}**."
            )
        elif was_cleaned:
            summary_text = (
                f"Cleaning complete. "
                f"The dataset has been saved as **{version_label}**."
            )
        else:
            summary_text = (
                "No cleaning changes were needed — your data looks good. "
                f"Current version: **{version_label}**."
            )

        # ── Fetch first 15 rows ────────────────────────────────────────────
        tables = repos.dataset_table.list_by_version(version_id)
        if not tables:
            _ensure_tables_registered(version_id, version.storage_path, repos, storage)
            tables = repos.dataset_table.list_by_version(version_id)

        table_output: AnalyticsOutput
        if tables:
            main_table = tables[0].table_name
            try:
                with temp_duckdb_path() as tmp:
                    tmp.write_bytes(storage.read(version.storage_path))
                    info = get_table_info(tmp, main_table)
                    rows_dicts = read_preview(tmp, main_table, limit=15)
                columns = list(rows_dicts[0].keys()) if rows_dicts else info.columns
                preview_rows = [[str(r.get(c, "")) for c in columns] for r in rows_dicts]
                table_output = TableOutput(
                    dataset_version_id=version_id,
                    title=f"First 15 rows — {version_label}",
                    description=f"Preview of '{main_table}' after cleaning.",
                    columns=columns,
                    preview_rows=preview_rows,
                    row_count=info.row_count,
                )
            except Exception as exc:  # noqa: BLE001
                table_output = TextOutput(
                    dataset_version_id=version_id,
                    title="Preview unavailable",
                    content=f"Could not read preview: {exc}",
                )
        else:
            table_output = TextOutput(
                dataset_version_id=version_id,
                title="No tables found",
                content="The cleaned version contains no tables.",
            )

        return {
            "response": AnalysisResultResponse(
                dataset_id=dataset_id,
                dataset_version_id=version_id,
                summary_text=summary_text,
                outputs=[table_output],
            )
        }

    # ── Node: analyze ─────────────────────────────────────────────────────
    def node_analyze(state: WorkflowGraphState) -> dict:
        dataset_id = state["dataset_id"]
        version_id = state["active_version_id"]

        version = repos.dataset_version.get(version_id)
        if version is None or not version.storage_path:
            return {
                "response": NeedsClarificationResponse(
                    message="Dataset version has no DuckDB artifact. Cannot run analysis.",
                    dataset_id=dataset_id,
                    dataset_version_id=version_id,
                )
            }

        # Cleaning creates new versions without profiles — profile them now so the
        # planner has column metadata (is_likely_metric, is_likely_categorical, etc.)
        # and can build the correct aggregation spec rather than falling back to a
        # raw preview.
        if not repos.profile.list_by_version(version_id):
            try:
                _ensure_tables_registered(version_id, version.storage_path, repos, storage)
                create_profiles(
                    dataset_id=dataset_id,
                    dataset_version_id=version_id,
                    repos=repos,
                    storage=storage,
                )
            except Exception:  # noqa: BLE001
                pass  # best-effort; planner will fall back to heuristics

        dataset = repos.dataset.get(dataset_id)
        if dataset is None:
            return {
                "response": NeedsClarificationResponse(
                    message="Dataset not found.",
                    dataset_id=dataset_id,
                    dataset_version_id=version_id,
                )
            }

        context = build_dataset_context(
            dataset_id=dataset_id,
            dataset_version_id=version_id,
            dataset_repo=repos.dataset,
            version_repo=repos.dataset_version,
            table_repo=repos.dataset_table,
            profile_repo=repos.profile,
            saved_view_repo=repos.saved_view,
            saved_visual_repo=repos.saved_visual,
        )
        if context is None:
            return {
                "response": NeedsClarificationResponse(
                    message="Could not build dataset context for analysis.",
                    dataset_id=dataset_id,
                    dataset_version_id=version_id,
                )
            }

        planner = AnalyticsPlanner(llm=llm)
        question = state["question"]

        with temp_duckdb_path() as tmp_db:
            tmp_db.write_bytes(storage.read(version.storage_path))
            plan = planner.plan(
                question=question,
                context=context,
                recent_messages=state.get("recent_messages") or [],
                prior_output_refs=state.get("prior_output_refs") or [],
            )
            if plan.intent == AnalyticsIntent.unsupported:
                return {
                    "response": NeedsClarificationResponse(
                        message=(
                            "This question is outside the supported analytics scope. "
                            "Try asking for a table summary, chart, or aggregation."
                        ),
                        dataset_id=dataset_id,
                        dataset_version_id=version_id,
                    )
                }
            output = planner.execute(
                plan=plan,
                db_path=tmp_db,
                workspace_id=dataset.workspace_id,
                dataset_id=dataset_id,
                storage=storage,
                context=context,
            )

        outputs: list[AnalyticsOutput] = [output]
        summary = _interpretation(outputs, context, question, llm)
        return {
            "response": AnalysisResultResponse(
                dataset_id=dataset_id,
                dataset_version_id=version_id,
                summary_text=summary,
                outputs=outputs,
            )
        }

    # ── Assemble graph ────────────────────────────────────────────────────
    graph = StateGraph(WorkflowGraphState)

    graph.add_node("router", node_router)
    graph.add_node("classify_intent", node_classify_intent)
    graph.add_node("profile_and_plan", node_profile_and_plan)
    graph.add_node("pause_cleaning", node_pause_cleaning)
    graph.add_node("execute_cleaning", node_execute_cleaning)
    graph.add_node("cleaning_result", node_cleaning_result)
    graph.add_node("analyze", node_analyze)

    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", _route_from_router, {
        "classify_intent": "classify_intent",
        "execute_cleaning": "execute_cleaning",
        "profile_and_plan": "profile_and_plan",
    })
    graph.add_edge("classify_intent", "profile_and_plan")
    graph.add_conditional_edges("profile_and_plan", _route_after_profile_and_plan, {
        "pause_cleaning": "pause_cleaning",
        "cleaning_result": "cleaning_result",
        "analyze": "analyze",
        END: END,
    })
    graph.add_edge("pause_cleaning", END)
    graph.add_conditional_edges("execute_cleaning", _route_after_execute_cleaning, {
        "cleaning_result": "cleaning_result",
        "analyze": "analyze",
        END: END,
    })
    graph.add_edge("cleaning_result", END)
    graph.add_edge("analyze", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public orchestrator class (same interface as before)
# ---------------------------------------------------------------------------

class AnalyticsOrchestrator:
    def __init__(
        self,
        repos: Repos,
        storage: StorageBackend,
        llm: LLMProvider | None = None,
    ) -> None:
        self._graph = _build_graph(repos, storage, llm or FakeLLMProvider())

    def run(
        self,
        question: str,
        dataset_id: UUID,
        dataset_version_id: UUID,
        workspace_id: UUID | None,
        workflow_state: WorkflowState | None,
        cleaning_decisions: list[CleaningDecisionItem],
        feature_decisions: list,   # kept for API compat; unused in this flow
        recent_messages: list[RecentMessage],
        prior_output_refs: list[PriorOutputRef],
    ) -> WorkflowResponse:
        wf = workflow_state or WorkflowState(
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            dataset_version_id=dataset_version_id,
            question=question,
            stage=WorkflowStage.start,
        )
        active_version_id = wf.resolved_version_id or wf.dataset_version_id

        initial: WorkflowGraphState = {
            "question": question,
            "dataset_id": dataset_id,
            "workspace_id": workspace_id,
            "cleaning_decisions": cleaning_decisions,
            "recent_messages": recent_messages,
            "prior_output_refs": prior_output_refs,
            "workflow_stage": wf.stage,
            "workflow_intent": wf.intent,
            "active_version_id": active_version_id,
            "profile_id": wf.profile_id,
            "cleaning_plan_id": wf.cleaning_plan_id,
            "resolved_version_id": wf.resolved_version_id,
            "cleaning_approval_items": [],
            "response": None,
        }

        final: WorkflowGraphState = self._graph.invoke(initial)

        if final.get("response") is not None:
            return final["response"]

        return NeedsClarificationResponse(
            message="Workflow completed without producing a response.",
            dataset_id=dataset_id,
            dataset_version_id=active_version_id,
        )
