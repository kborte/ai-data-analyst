"""End-to-end LangGraph simulation: traces real behavior for three user requests.

Dataset: country + product (long-format, one row per purchase) with clear
most-frequent products that differ by country.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from app.dependencies import Repos
from app.schemas.analytics import (
    TableOutput, VisualOutput, TextOutput,
)
from app.schemas.common import DatasetVersionType
from app.schemas.dataset import Dataset, DatasetVersion
from app.schemas.workflow import (
    AnalysisResultResponse,
    NeedsApprovalResponse,
    NeedsClarificationResponse,
    WorkflowStage,
    WorkflowState,
)
from app.services.analytics_orchestrator import AnalyticsOrchestrator
from app.tools.data.duckdb_service import create_version_duckdb
from app.tools.files.storage_service import LocalStorageBackend

_NOW = datetime.now(tz=UTC)

# ---------------------------------------------------------------------------
# Test dataset: long-format purchases, different top product per country
# ---------------------------------------------------------------------------
# USA: Apple × 4, Banana × 2, Cherry × 1  → top = Apple
# UK:  Banana × 4, Cherry × 2, Apple × 1  → top = Banana

_ROWS = [
    # USA
    ("USA", "Apple", 1),
    ("USA", "Apple", 1),
    ("USA", "Apple", 1),
    ("USA", "Apple", 1),
    ("USA", "Banana", 1),
    ("USA", "Banana", 1),
    ("USA", "Cherry", 1),
    # UK
    ("UK", "Banana", 1),
    ("UK", "Banana", 1),
    ("UK", "Banana", 1),
    ("UK", "Banana", 1),
    ("UK", "Cherry", 1),
    ("UK", "Cherry", 1),
    ("UK", "Apple", 1),
]

_DF = pd.DataFrame(_ROWS, columns=["country", "product", "quantity"])


def _setup(tmp_path: Path):
    repos = Repos()
    storage = LocalStorageBackend(base_dir=str(tmp_path))

    ws_id = uuid.uuid4()
    dataset = Dataset(
        dataset_id=uuid.uuid4(),
        workspace_id=ws_id,
        name="Purchases",
        created_by_user_id=uuid.uuid4(),
        created_at=_NOW,
    )
    repos.dataset.save(dataset)

    storage_path = "v1_original.duckdb"
    db_path = tmp_path / storage_path
    create_version_duckdb({"purchases": _DF}, db_path)
    storage.save(storage_path, db_path.read_bytes())

    version = DatasetVersion(
        dataset_version_id=uuid.uuid4(),
        dataset_id=dataset.dataset_id,
        version_number=1,
        version_type=DatasetVersionType.original,
        storage_path=storage_path,
        created_by_user_id=uuid.uuid4(),
        created_at=_NOW,
    )
    repos.dataset_version.save(version)
    return repos, storage, dataset, version


def _run(question: str, repos, storage, dataset, version,
         prior_refs=None, workflow_state=None):
    orch = AnalyticsOrchestrator(repos=repos, storage=storage)
    return orch.run(
        question=question,
        dataset_id=dataset.dataset_id,
        dataset_version_id=version.dataset_version_id,
        workspace_id=dataset.workspace_id,
        workflow_state=workflow_state,
        cleaning_decisions=[],
        feature_decisions=[],
        recent_messages=[],
        prior_output_refs=prior_refs or [],
    )


# ---------------------------------------------------------------------------
# Simulation 1: Table analysis
# ---------------------------------------------------------------------------

def test_sim1_top_product_per_country(tmp_path, capsys):
    repos, storage, dataset, version = _setup(tmp_path)

    print("\n=== SIM 1: 'For each country, identify the product with the highest purchase frequency.' ===")
    print(f"dataset_id={dataset.dataset_id}")
    print(f"dataset_version_id={version.dataset_version_id}")

    response = _run(
        "For each country, identify the product with the highest purchase frequency.",
        repos, storage, dataset, version,
    )

    print(f"\nresponse_type: {response.response_type}")

    if isinstance(response, NeedsApprovalResponse):
        print(f"[BLOCKED] Cleaning approval required — {len(response.items)} item(s)")
        print("  This means the planner routed to pause_cleaning instead of analyze.")
        print("  FIRST BROKEN POINT: profile_and_plan creates a cleaning plan with approval items,")
        print("  blocking analysis even for analytical requests.")
        pytest.fail("Blocked by cleaning approval on analytical request")

    if isinstance(response, NeedsClarificationResponse):
        print(f"[BLOCKED] Needs clarification: {response.message}")
        pytest.fail(f"Got needs_clarification: {response.message}")

    assert isinstance(response, AnalysisResultResponse), f"Expected analysis_result, got {response.response_type}"

    print(f"summary_text: {response.summary_text[:120]}")
    print(f"outputs count: {len(response.outputs)}")

    for i, out in enumerate(response.outputs):
        otype = getattr(out, "output_type", "?")
        print(f"\nOutput[{i}]: output_type={otype}, title={out.title!r}")
        if isinstance(out, TableOutput):
            print(f"  columns: {out.columns}")
            print(f"  row_count: {out.row_count}")
            for row in out.preview_rows[:5]:
                print(f"  row: {dict(zip(out.columns, row))}")
        elif isinstance(out, VisualOutput):
            print(f"  chart_type: {out.chart_type}")
            chart_data = out.chart_spec_json.get("data", [])
            print(f"  chart_spec_json.data rows: {len(chart_data)}")

    # Assertions
    table_outputs = [o for o in response.outputs if isinstance(o, TableOutput)]
    assert len(table_outputs) >= 1, "Expected at least one TableOutput"

    first = table_outputs[0]
    assert first.row_count < len(_DF), (
        f"TableOutput has {first.row_count} rows — equals raw data, not an aggregated result. "
        f"Raw dataset has {len(_DF)} rows."
    )
    assert first.row_count == 2, (
        f"Expected 2 rows (one per country), got {first.row_count}"
    )

    # Check result correctness
    rows_by_country: dict[str, dict] = {}
    for row in first.preview_rows:
        d = dict(zip(first.columns, row))
        ctry = str(d.get("country", "")).upper()
        rows_by_country[ctry] = d

    usa_product = str(rows_by_country.get("USA", {}).get("product", "")).lower()
    uk_product = str(rows_by_country.get("UK", {}).get("product", "")).lower()

    print(f"\nUSA top product: {usa_product!r} (expected 'apple')")
    print(f"UK  top product: {uk_product!r} (expected 'banana')")

    assert usa_product == "apple", f"USA top product should be apple, got {usa_product!r}"
    assert uk_product == "banana", f"UK top product should be banana, got {uk_product!r}"

    print("\n[PASS] Sim 1: aggregated result returned, correct top products per country.")


# ---------------------------------------------------------------------------
# Simulation 2: Visual follow-up
# ---------------------------------------------------------------------------

def test_sim2_visual_bar_chart(tmp_path, capsys):
    repos, storage, dataset, version = _setup(tmp_path)

    print("\n=== SIM 2: 'Show this as a bar chart.' ===")

    response = _run(
        "Show this as a bar chart.",
        repos, storage, dataset, version,
    )

    print(f"response_type: {response.response_type}")

    if isinstance(response, NeedsApprovalResponse):
        print(f"[BLOCKED] Cleaning approval — {len(response.items)} item(s)")
        pytest.fail("Blocked by cleaning approval on visual request")

    if isinstance(response, NeedsClarificationResponse):
        print(f"[BLOCKED] Needs clarification: {response.message}")
        pytest.fail(f"Got needs_clarification: {response.message}")

    assert isinstance(response, AnalysisResultResponse)

    print(f"outputs: {[getattr(o, 'output_type', '?') for o in response.outputs]}")

    visual_outputs = [o for o in response.outputs if isinstance(o, VisualOutput)]
    table_outputs = [o for o in response.outputs if isinstance(o, TableOutput)]

    print(f"VisualOutputs: {len(visual_outputs)}, TableOutputs: {len(table_outputs)}")

    for vo in visual_outputs:
        has_data = bool(vo.chart_spec_json.get("data"))
        print(f"  VisualOutput: chart_type={vo.chart_type}, chart_spec_json.data present={has_data}")
        print(f"  chart_spec_json keys: {list(vo.chart_spec_json.keys())}")

    if not visual_outputs:
        print(f"[FIRST BROKEN POINT] No VisualOutput — got table outputs only:")
        for to in table_outputs:
            print(f"  TableOutput: title={to.title!r}, rows={to.row_count}, cols={to.columns}")
        pytest.fail("Visual request returned no VisualOutput with chart_spec_json")

    vo = visual_outputs[0]
    assert vo.chart_spec_json, "chart_spec_json is empty on VisualOutput"
    assert vo.chart_spec_json.get("data"), "chart_spec_json.data is missing or empty"

    print("\n[PASS] Sim 2: VisualOutput returned with chart_spec_json.")


# ---------------------------------------------------------------------------
# Simulation 3: Ambiguous request
# ---------------------------------------------------------------------------

def test_sim3_ambiguous_best_product(tmp_path, capsys):
    repos, storage, dataset, version = _setup(tmp_path)

    print("\n=== SIM 3: 'Show the best product.' ===")

    response = _run(
        "Show the best product.",
        repos, storage, dataset, version,
    )

    print(f"response_type: {response.response_type}")

    if isinstance(response, NeedsApprovalResponse):
        print(f"[BLOCKED] Cleaning approval — {len(response.items)} item(s)")
        pytest.fail("Blocked by cleaning approval on ambiguous request")

    if isinstance(response, NeedsClarificationResponse):
        print(f"[PASS] needs_clarification returned: {response.message}")
        return  # correct behavior

    if isinstance(response, AnalysisResultResponse):
        table_outputs = [o for o in response.outputs if isinstance(o, TableOutput)]
        text_outputs = [o for o in response.outputs if isinstance(o, TextOutput)]
        print(f"[NOTE] analysis_result returned — outputs: {[getattr(o, 'output_type', '?') for o in response.outputs]}")
        for to in table_outputs:
            print(f"  TableOutput: rows={to.row_count}, cols={to.columns}")
            if to.row_count == len(_DF):
                print(f"  [FIRST BROKEN POINT] Raw data preview returned for ambiguous query.")
                print(f"  'best' is treated as table_result intent and falls through to preview_table.")
        print(f"\n[INFO] Ambiguous query returned analysis result instead of needs_clarification.")
        print("  This is a secondary bug but not the first broken point.")
