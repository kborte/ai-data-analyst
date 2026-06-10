"""End-to-end LangGraph simulation: traces the full flow for three user requests.

Cleaning approval is the correct first step. These tests pre-populate an empty
cleaning plan (no approval items) so the graph routes straight to the analyze
node, isolating SQL-generation behavior.

Dataset: country + product (long-format) with clear top products per country.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from app.dependencies import Repos
from app.schemas.analytics import TableOutput, VisualOutput, TextOutput
from app.schemas.cleaning import (
    CleaningPlan, CleaningPlanJson, CleaningPlanSummary,
)
from app.schemas.common import ArtifactStatus, DatasetVersionType
from app.schemas.dataset import Dataset, DatasetVersion, DatasetTable
from app.schemas.profile import ColumnProfile, DataProfile
from app.schemas.common import DataType
from app.schemas.workflow import (
    AnalysisResultResponse,
    NeedsApprovalResponse,
    NeedsClarificationResponse,
)
from app.services.analytics_orchestrator import AnalyticsOrchestrator
from app.tools.data.duckdb_service import create_version_duckdb
from app.tools.files.storage_service import LocalStorageBackend

_NOW = datetime.now(tz=UTC)

# ---------------------------------------------------------------------------
# Dataset: long-format, different top product per country
# USA: Apple×4, Banana×2, Cherry×1  → top = Apple
# UK:  Banana×4, Cherry×2, Apple×1  → top = Banana
# ---------------------------------------------------------------------------

_ROWS = [
    ("USA", "Apple",  1), ("USA", "Apple",  1), ("USA", "Apple",  1), ("USA", "Apple",  1),
    ("USA", "Banana", 1), ("USA", "Banana", 1),
    ("USA", "Cherry", 1),
    ("UK",  "Banana", 1), ("UK",  "Banana", 1), ("UK",  "Banana", 1), ("UK",  "Banana", 1),
    ("UK",  "Cherry", 1), ("UK",  "Cherry", 1),
    ("UK",  "Apple",  1),
]
_DF = pd.DataFrame(_ROWS, columns=["country", "product", "quantity"])


def _make_profile(version: DatasetVersion) -> DataProfile:
    return DataProfile(
        profile_id=uuid.uuid4(),
        dataset_version_id=version.dataset_version_id,
        table_name="purchases",
        row_count=len(_DF),
        column_count=3,
        column_profiles=[
            ColumnProfile(
                column_name="country", data_type=DataType.string,
                total_count=len(_DF), null_count=0, null_percent=0.0,
                unique_count=2, unique_percent=14.3,
                is_likely_metric=False, is_likely_id=False,
                is_likely_date=False, is_likely_categorical=True,
                top_values=["USA", "UK"],
            ),
            ColumnProfile(
                column_name="product", data_type=DataType.string,
                total_count=len(_DF), null_count=0, null_percent=0.0,
                unique_count=3, unique_percent=21.4,
                is_likely_metric=False, is_likely_id=False,
                is_likely_date=False, is_likely_categorical=True,
                top_values=["Apple", "Banana", "Cherry"],
            ),
            ColumnProfile(
                column_name="quantity", data_type=DataType.integer,
                total_count=len(_DF), null_count=0, null_percent=0.0,
                unique_count=1, unique_percent=7.1,
                is_likely_metric=True, is_likely_id=False,
                is_likely_date=False, is_likely_categorical=False,
            ),
        ],
        quality_issues=[],
        likely_metric_columns=["quantity"],
        created_at=_NOW,
    )


def _make_empty_cleaning_plan(version: DatasetVersion, profile: DataProfile) -> CleaningPlan:
    """No approval items — graph routes directly to analyze."""
    plan_id = uuid.uuid4()
    return CleaningPlan(
        cleaning_plan_id=plan_id,
        dataset_version_id=version.dataset_version_id,
        status=ArtifactStatus.completed,
        plan_json=CleaningPlanJson(
            plan_id=plan_id,
            dataset_version_id=version.dataset_version_id,
            profile_id=profile.profile_id,
            created_at=_NOW,
            summary=CleaningPlanSummary(
                total_steps=0, steps_requiring_approval=0,
                auto_approved_steps=0, auto_ignored_steps=0,
                estimated_row_count_change=0, estimated_columns_changed=[],
            ),
            global_assumptions=[],
            steps=[],
        ),
        created_at=_NOW,
    )


def _setup(tmp_path: Path):
    repos = Repos()
    storage = LocalStorageBackend(base_dir=str(tmp_path))

    ws_id = uuid.uuid4()
    dataset = Dataset(
        dataset_id=uuid.uuid4(), workspace_id=ws_id, name="Purchases",
        created_by_user_id=uuid.uuid4(), created_at=_NOW,
    )
    repos.dataset.save(dataset)

    storage_path = "v1_original.duckdb"
    db_path = tmp_path / storage_path
    create_version_duckdb({"purchases": _DF}, db_path)
    storage.save(storage_path, db_path.read_bytes())

    version = DatasetVersion(
        dataset_version_id=uuid.uuid4(), dataset_id=dataset.dataset_id,
        version_number=1, version_type=DatasetVersionType.original,
        storage_path=storage_path, created_by_user_id=uuid.uuid4(), created_at=_NOW,
    )
    repos.dataset_version.save(version)

    # Pre-populate table record, profile, and empty cleaning plan so graph skips
    # auto-profiling and cleaning approval, routing straight to analyze.
    repos.dataset_table.save(DatasetTable(
        table_id=uuid.uuid4(), dataset_version_id=version.dataset_version_id,
        table_name="purchases", row_count=len(_DF), column_count=3,
    ))
    profile = _make_profile(version)
    repos.profile.save(profile)
    repos.cleaning_plan.save(_make_empty_cleaning_plan(version, profile))

    return repos, storage, dataset, version


def _run(question, repos, storage, dataset, version, prior_refs=None):
    orch = AnalyticsOrchestrator(repos=repos, storage=storage)
    return orch.run(
        question=question,
        dataset_id=dataset.dataset_id,
        dataset_version_id=version.dataset_version_id,
        workspace_id=dataset.workspace_id,
        workflow_state=None,
        cleaning_decisions=[],
        feature_decisions=[],
        recent_messages=[],
        prior_output_refs=prior_refs or [],
    )


# ---------------------------------------------------------------------------
# Simulation 1: Table analysis — top product per country
# ---------------------------------------------------------------------------

def test_sim1_top_product_per_country(tmp_path):
    repos, storage, dataset, version = _setup(tmp_path)

    print("\n=== SIM 1 ===")
    print("question: 'For each country, identify the product with the highest purchase frequency.'")
    print(f"dataset_version_id={version.dataset_version_id}")

    response = _run(
        "For each country, identify the product with the highest purchase frequency.",
        repos, storage, dataset, version,
    )

    print(f"response_type: {response.response_type}")

    assert not isinstance(response, NeedsApprovalResponse), (
        f"Cleaning approval required — {len(response.items)} items. "
        "Test setup should have pre-populated an empty cleaning plan."
    )
    assert not isinstance(response, NeedsClarificationResponse), (
        f"needs_clarification: {response.message}"
    )
    assert isinstance(response, AnalysisResultResponse)

    print(f"summary_text: {response.summary_text[:120]}")
    print(f"outputs: {len(response.outputs)}")

    table_outputs = [o for o in response.outputs if isinstance(o, TableOutput)]
    assert len(table_outputs) >= 1, "Expected at least one TableOutput"

    first = table_outputs[0]
    print(f"\nTableOutput: columns={first.columns}, row_count={first.row_count}")
    print(f"source_spec: {first.source_spec_json.get('tool_name')}")
    for row in first.preview_rows[:5]:
        print(f"  {dict(zip(first.columns, row))}")

    # Must be aggregated (not raw data)
    assert first.row_count < len(_DF), (
        f"Got {first.row_count} rows — same as raw data ({len(_DF)}). "
        "Expected aggregated result."
    )
    # One row per country
    assert first.row_count == 2, f"Expected 2 rows (one per country), got {first.row_count}"

    # Correct top product per country
    rows_by_country = {
        str(dict(zip(first.columns, row)).get("country", "")).upper():
        dict(zip(first.columns, row))
        for row in first.preview_rows
    }
    usa_product = str(rows_by_country.get("USA", {}).get("product", "")).lower()
    uk_product  = str(rows_by_country.get("UK",  {}).get("product", "")).lower()

    print(f"\nUSA top product: {usa_product!r} (expected 'apple')")
    print(f"UK  top product: {uk_product!r}  (expected 'banana')")

    assert usa_product == "apple",  f"USA top product wrong: got {usa_product!r}"
    assert uk_product  == "banana", f"UK  top product wrong: got {uk_product!r}"

    print("\n[PASS] aggregated result, correct top products per country.")


# ---------------------------------------------------------------------------
# Simulation 2: Visual follow-up — bar chart
# ---------------------------------------------------------------------------

def test_sim2_visual_bar_chart(tmp_path):
    repos, storage, dataset, version = _setup(tmp_path)

    print("\n=== SIM 2 ===")
    print("question: 'Show this as a bar chart.'")

    response = _run("Show this as a bar chart.", repos, storage, dataset, version)

    print(f"response_type: {response.response_type}")

    assert not isinstance(response, NeedsApprovalResponse), "Blocked by cleaning approval"
    assert not isinstance(response, NeedsClarificationResponse), response.message
    assert isinstance(response, AnalysisResultResponse)

    print(f"outputs: {[getattr(o, 'output_type', '?') for o in response.outputs]}")

    visual_outputs = [o for o in response.outputs if isinstance(o, VisualOutput)]
    table_outputs  = [o for o in response.outputs if isinstance(o, TableOutput)]

    print(f"VisualOutputs={len(visual_outputs)}, TableOutputs={len(table_outputs)}")

    assert len(visual_outputs) >= 1, (
        "Visual request returned no VisualOutput. "
        f"Got table outputs: {[(o.title, o.row_count) for o in table_outputs]}"
    )

    vo = visual_outputs[0]
    print(f"  chart_type={vo.chart_type}, chart_spec_json keys={list(vo.chart_spec_json.keys())}")
    assert vo.chart_spec_json, "chart_spec_json is empty"
    assert vo.chart_spec_json.get("data"), "chart_spec_json.data is missing"

    print("\n[PASS] VisualOutput with chart_spec_json returned.")


# ---------------------------------------------------------------------------
# Simulation 3: Ambiguous request — "Show the best product."
# ---------------------------------------------------------------------------

def test_sim3_ambiguous_best_product(tmp_path):
    repos, storage, dataset, version = _setup(tmp_path)

    print("\n=== SIM 3 ===")
    print("question: 'Show the best product.'")

    response = _run("Show the best product.", repos, storage, dataset, version)

    print(f"response_type: {response.response_type}")

    assert not isinstance(response, NeedsApprovalResponse), "Blocked by cleaning approval"

    if isinstance(response, NeedsClarificationResponse):
        print(f"[PASS] needs_clarification: {response.message}")
        return

    assert isinstance(response, AnalysisResultResponse)
    table_outputs = [o for o in response.outputs if isinstance(o, TableOutput)]
    print(f"analysis_result — outputs: {[getattr(o, 'output_type', '?') for o in response.outputs]}")
    for to in table_outputs:
        print(f"  TableOutput: rows={to.row_count}, cols={to.columns}")
        if to.row_count == len(_DF):
            pytest.fail(
                f"'best' returned raw preview ({to.row_count} rows = full table). "
                "Expected aggregated result or needs_clarification."
            )
    print("[INFO] Ambiguous query returned analysis result (secondary behavior).")
