"""Tests for M12B compact dataset context builder."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.repositories.memory import (
    DataProfileRepository,
    DatasetRepository,
    DatasetTableRepository,
    DatasetVersionRepository,
    SavedViewRepository,
    SavedVisualRepository,
)
from app.schemas.analytics_context import _MAX_ARTIFACTS, _MAX_TOP_VALUES
from app.schemas.common import DataType, DatasetVersionType
from app.schemas.dataset import Dataset, DatasetTable, DatasetVersion
from app.schemas.profile import ColumnProfile, DataProfile, DataQualityIssue
from app.schemas.saved_view import SavedView, SavedViewSourceType
from app.schemas.saved_visual import SavedVisual, SavedVisualSourceType
from app.services.analytics_context import build_dataset_context

NOW = datetime.now(tz=UTC)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _dataset(workspace_id: uuid.UUID | None = None) -> Dataset:
    return Dataset(
        dataset_id=uuid.uuid4(),
        workspace_id=workspace_id or uuid.uuid4(),
        name="Sales Data",
        created_by_user_id=uuid.uuid4(),
        created_at=NOW,
    )


def _version(dataset_id: uuid.UUID, version_number: int = 1) -> DatasetVersion:
    return DatasetVersion(
        dataset_version_id=uuid.uuid4(),
        dataset_id=dataset_id,
        version_number=version_number,
        version_type=DatasetVersionType.original,
        display_name="Original upload",
        created_by_user_id=uuid.uuid4(),
        created_at=NOW,
    )


def _table(version_id: uuid.UUID, name: str = "sales") -> DatasetTable:
    return DatasetTable(
        table_id=uuid.uuid4(),
        dataset_version_id=version_id,
        table_name=name,
        row_count=1000,
        column_count=3,
    )


def _column(name: str, dtype: DataType = DataType.float_, **kw) -> ColumnProfile:
    return ColumnProfile(
        column_name=name,
        data_type=dtype,
        total_count=1000,
        null_count=kw.get("null_count", 0),
        null_percent=kw.get("null_percent", 0.0),
        unique_count=kw.get("unique_count", 100),
        unique_percent=kw.get("unique_percent", 10.0),
        is_likely_metric=kw.get("is_likely_metric", False),
        is_likely_date=kw.get("is_likely_date", False),
        is_likely_categorical=kw.get("is_likely_categorical", False),
        top_values=kw.get("top_values", []),
    )


def _profile(version_id: uuid.UUID, table_name: str, columns: list[ColumnProfile], quality_issues=None) -> DataProfile:
    return DataProfile(
        profile_id=uuid.uuid4(),
        dataset_version_id=version_id,
        table_name=table_name,
        row_count=1000,
        column_count=len(columns),
        column_profiles=columns,
        quality_issues=quality_issues or [],
        created_at=NOW,
    )


def _saved_view(workspace_id: uuid.UUID, dataset_id: uuid.UUID, version_id: uuid.UUID, name: str = "Revenue View") -> SavedView:
    return SavedView(
        saved_view_id=uuid.uuid4(),
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        dataset_version_id=version_id,
        name=name,
        source_type=SavedViewSourceType.aggregation,
        created_at=NOW,
    )


def _saved_visual(workspace_id: uuid.UUID, dataset_id: uuid.UUID, version_id: uuid.UUID, title: str = "Revenue Chart") -> SavedVisual:
    return SavedVisual(
        visual_id=uuid.uuid4(),
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        dataset_version_id=version_id,
        title=title,
        chart_type="line",
        source_type=SavedVisualSourceType.chart_spec,
        created_at=NOW,
    )


def _repos(dataset: Dataset, version: DatasetVersion, tables: list[DatasetTable], profiles: list[DataProfile]):
    ds_repo = DatasetRepository()
    v_repo = DatasetVersionRepository()
    t_repo = DatasetTableRepository()
    p_repo = DataProfileRepository()
    ds_repo.save(dataset)
    v_repo.save(version)
    for t in tables:
        t_repo.save(t)
    for p in profiles:
        p_repo.save(p)
    return ds_repo, v_repo, t_repo, p_repo


# ---------------------------------------------------------------------------
# Basic construction
# ---------------------------------------------------------------------------

class TestBuildDatasetContext:
    def test_returns_context_with_correct_ids(self):
        d = _dataset()
        v = _version(d.dataset_id)
        t = _table(v.dataset_version_id)
        ds_r, v_r, t_r, p_r = _repos(d, v, [t], [])

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        assert ctx is not None
        assert ctx.dataset_id == d.dataset_id
        assert ctx.dataset_version_id == v.dataset_version_id

    def test_carries_dataset_name_and_version_metadata(self):
        d = _dataset()
        v = _version(d.dataset_id)
        t = _table(v.dataset_version_id)
        ds_r, v_r, t_r, p_r = _repos(d, v, [t], [])

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        assert ctx.dataset_name == "Sales Data"
        assert ctx.version_number == 1
        assert ctx.display_name == "Original upload"

    def test_returns_none_when_dataset_missing(self):
        ds_r = DatasetRepository()
        v_r = DatasetVersionRepository()
        t_r = DatasetTableRepository()
        p_r = DataProfileRepository()

        ctx = build_dataset_context(
            dataset_id=uuid.uuid4(),
            dataset_version_id=uuid.uuid4(),
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        assert ctx is None

    def test_returns_none_when_version_missing(self):
        d = _dataset()
        ds_r = DatasetRepository()
        ds_r.save(d)
        v_r = DatasetVersionRepository()  # empty
        t_r = DatasetTableRepository()
        p_r = DataProfileRepository()

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=uuid.uuid4(),
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        assert ctx is None


# ---------------------------------------------------------------------------
# Table and column metadata
# ---------------------------------------------------------------------------

class TestTableContext:
    def test_includes_table_names(self):
        d = _dataset()
        v = _version(d.dataset_id)
        t1 = _table(v.dataset_version_id, "orders")
        t2 = _table(v.dataset_version_id, "customers")
        ds_r, v_r, t_r, p_r = _repos(d, v, [t1, t2], [])

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        names = {t.table_name for t in ctx.tables}
        assert names == {"orders", "customers"}

    def test_table_without_profile_has_profile_false(self):
        d = _dataset()
        v = _version(d.dataset_id)
        t = _table(v.dataset_version_id)
        ds_r, v_r, t_r, p_r = _repos(d, v, [t], [])

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        assert ctx.tables[0].has_profile is False
        assert ctx.tables[0].columns == []

    def test_table_with_profile_has_columns(self):
        d = _dataset()
        v = _version(d.dataset_id)
        t = _table(v.dataset_version_id, "sales")
        col_month = _column("month", DataType.date, is_likely_date=True)
        col_rev = _column("revenue", DataType.float_, is_likely_metric=True)
        p = _profile(v.dataset_version_id, "sales", [col_month, col_rev])
        ds_r, v_r, t_r, p_r = _repos(d, v, [t], [p])

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        tctx = ctx.tables[0]
        assert tctx.has_profile is True
        assert len(tctx.columns) == 2
        col_names = {c.column_name for c in tctx.columns}
        assert col_names == {"month", "revenue"}

    def test_column_flags_preserved(self):
        d = _dataset()
        v = _version(d.dataset_id)
        t = _table(v.dataset_version_id, "sales")
        col = _column("revenue", DataType.float_, is_likely_metric=True)
        p = _profile(v.dataset_version_id, "sales", [col])
        ds_r, v_r, t_r, p_r = _repos(d, v, [t], [p])

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        c = ctx.tables[0].columns[0]
        assert c.is_likely_metric is True
        assert c.is_likely_date is False

    def test_row_count_from_profile_preferred(self):
        d = _dataset()
        v = _version(d.dataset_id)
        t = DatasetTable(
            table_id=uuid.uuid4(),
            dataset_version_id=v.dataset_version_id,
            table_name="sales",
            row_count=999,  # stale metadata
            column_count=3,
        )
        col = _column("revenue")
        p = _profile(v.dataset_version_id, "sales", [col])  # profile has row_count=1000
        ds_r, v_r, t_r, p_r = _repos(d, v, [t], [p])

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        assert ctx.tables[0].row_count == 1000  # from profile

    def test_row_count_from_table_when_no_profile(self):
        d = _dataset()
        v = _version(d.dataset_id)
        t = _table(v.dataset_version_id)  # row_count=1000
        ds_r, v_r, t_r, p_r = _repos(d, v, [t], [])

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        assert ctx.tables[0].row_count == 1000


# ---------------------------------------------------------------------------
# No full dataset dumped
# ---------------------------------------------------------------------------

class TestContextCompactness:
    def test_top_values_capped(self):
        d = _dataset()
        v = _version(d.dataset_id)
        t = _table(v.dataset_version_id)
        many_values = list(range(50))
        col = _column("category", DataType.categorical, top_values=many_values)
        p = _profile(v.dataset_version_id, t.table_name, [col])
        ds_r, v_r, t_r, p_r = _repos(d, v, [t], [p])

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        assert len(ctx.tables[0].columns[0].top_values) <= _MAX_TOP_VALUES

    def test_quality_issue_count_not_full_issues(self):
        d = _dataset()
        v = _version(d.dataset_id)
        t = _table(v.dataset_version_id)
        col = _column("revenue")
        from app.schemas.common import ImpactLevel, IssueType
        issues = [
            DataQualityIssue(
                issue_type=IssueType.missing_values,
                table_name=t.table_name,
                column_name="revenue",
                description="Missing values",
                affected_rows_count=10,
                affected_rows_percent=1.0,
                impact_level=ImpactLevel.low,
            )
            for _ in range(3)
        ]
        p = _profile(v.dataset_version_id, t.table_name, [col], quality_issues=issues)
        ds_r, v_r, t_r, p_r = _repos(d, v, [t], [p])

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        tctx = ctx.tables[0]
        assert tctx.quality_issue_count == 3
        assert not hasattr(tctx, "quality_issues")

    def test_context_has_no_raw_row_data(self):
        d = _dataset()
        v = _version(d.dataset_id)
        t = _table(v.dataset_version_id)
        ds_r, v_r, t_r, p_r = _repos(d, v, [t], [])

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        assert not hasattr(ctx, "rows")
        assert not hasattr(ctx, "raw_data")
        for tctx in ctx.tables:
            assert not hasattr(tctx, "rows")


# ---------------------------------------------------------------------------
# Version scoping
# ---------------------------------------------------------------------------

class TestVersionScoping:
    def test_context_scoped_to_requested_version(self):
        d = _dataset()
        v1 = _version(d.dataset_id, version_number=1)
        v2 = _version(d.dataset_id, version_number=2)
        t1 = _table(v1.dataset_version_id, "orders_v1")
        t2 = _table(v2.dataset_version_id, "orders_v2")

        ds_r = DatasetRepository(); ds_r.save(d)
        v_r = DatasetVersionRepository(); v_r.save(v1); v_r.save(v2)
        t_r = DatasetTableRepository(); t_r.save(t1); t_r.save(t2)
        p_r = DataProfileRepository()

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v1.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        assert ctx.dataset_version_id == v1.dataset_version_id
        assert len(ctx.tables) == 1
        assert ctx.tables[0].table_name == "orders_v1"

    def test_profiles_from_other_versions_not_included(self):
        d = _dataset()
        v1 = _version(d.dataset_id, version_number=1)
        v2 = _version(d.dataset_id, version_number=2)
        t = _table(v1.dataset_version_id, "sales")
        col = _column("revenue")
        p_for_v2 = _profile(v2.dataset_version_id, "sales", [col])

        ds_r = DatasetRepository(); ds_r.save(d)
        v_r = DatasetVersionRepository(); v_r.save(v1); v_r.save(v2)
        t_r = DatasetTableRepository(); t_r.save(t)
        p_r = DataProfileRepository(); p_r.save(p_for_v2)

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v1.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        assert ctx.tables[0].has_profile is False


# ---------------------------------------------------------------------------
# Saved views and visuals
# ---------------------------------------------------------------------------

class TestSavedArtifactsInContext:
    def _setup(self):
        d = _dataset()
        v = _version(d.dataset_id)
        t = _table(v.dataset_version_id)
        ds_r, v_r, t_r, p_r = _repos(d, v, [t], [])
        sv_r = SavedViewRepository()
        svs_r = SavedVisualRepository()
        return d, v, ds_r, v_r, t_r, p_r, sv_r, svs_r

    def test_saved_views_included(self):
        d, v, ds_r, v_r, t_r, p_r, sv_r, svs_r = self._setup()
        sv = _saved_view(uuid.uuid4(), d.dataset_id, v.dataset_version_id)
        sv_r.save(sv)

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
            saved_view_repo=sv_r,
            saved_visual_repo=svs_r,
        )

        assert len(ctx.saved_views) == 1
        assert ctx.saved_views[0].name == "Revenue View"

    def test_saved_visuals_included(self):
        d, v, ds_r, v_r, t_r, p_r, sv_r, svs_r = self._setup()
        vis = _saved_visual(uuid.uuid4(), d.dataset_id, v.dataset_version_id)
        svs_r.save(vis)

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
            saved_view_repo=sv_r,
            saved_visual_repo=svs_r,
        )

        assert len(ctx.saved_visuals) == 1
        assert ctx.saved_visuals[0].chart_type == "line"

    def test_saved_artifacts_omitted_when_repos_not_provided(self):
        d, v, ds_r, v_r, t_r, p_r, _, _ = self._setup()

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
        )

        assert ctx.saved_views == []
        assert ctx.saved_visuals == []

    def test_saved_artifacts_capped_at_max(self):
        d, v, ds_r, v_r, t_r, p_r, sv_r, svs_r = self._setup()
        wid = uuid.uuid4()
        for i in range(_MAX_ARTIFACTS + 5):
            sv_r.save(_saved_view(wid, d.dataset_id, v.dataset_version_id, name=f"View {i}"))

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
            saved_view_repo=sv_r,
        )

        assert len(ctx.saved_views) <= _MAX_ARTIFACTS

    def test_saved_artifacts_from_other_versions_not_included(self):
        d = _dataset()
        v1 = _version(d.dataset_id, version_number=1)
        v2 = _version(d.dataset_id, version_number=2)
        t = _table(v1.dataset_version_id)

        ds_r = DatasetRepository(); ds_r.save(d)
        v_r = DatasetVersionRepository(); v_r.save(v1); v_r.save(v2)
        t_r = DatasetTableRepository(); t_r.save(t)
        p_r = DataProfileRepository()
        sv_r = SavedViewRepository()

        wid = uuid.uuid4()
        sv_r.save(_saved_view(wid, d.dataset_id, v2.dataset_version_id))  # belongs to v2

        ctx = build_dataset_context(
            dataset_id=d.dataset_id,
            dataset_version_id=v1.dataset_version_id,
            dataset_repo=ds_r,
            version_repo=v_r,
            table_repo=t_r,
            profile_repo=p_r,
            saved_view_repo=sv_r,
        )

        assert ctx.saved_views == []
