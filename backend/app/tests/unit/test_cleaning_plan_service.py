"""Unit tests for CleaningPlanService (M4B)."""

import uuid
from datetime import UTC, datetime

import pytest

from app.repositories.memory import CleaningPlanRepository, DataProfileRepository
from app.schemas.common import ImpactLevel, IssueType
from app.schemas.profile import DataProfile, DataQualityIssue
from app.services.cleaning_plan_service import CleaningPlanService

_VERSION_ID = uuid.uuid4()


def _make_profile(issues: list[DataQualityIssue], metric_cols: list[str] | None = None) -> DataProfile:
    profile = DataProfile(
        profile_id=uuid.uuid4(),
        dataset_version_id=_VERSION_ID,
        table_name="orders",
        row_count=100,
        column_count=max(len({i.column_name for i in issues if i.column_name}), 1),
        column_profiles=[],
        quality_issues=issues,
        likely_metric_columns=metric_cols or [],
        created_at=datetime.now(tz=UTC),
    )
    return profile


def _issue(issue_type: IssueType, column: str | None) -> DataQualityIssue:
    return DataQualityIssue(
        issue_type=issue_type,
        table_name="orders",
        column_name=column,
        description="test",
        affected_rows_count=5,
        affected_rows_percent=5.0,
        impact_level=ImpactLevel.medium,
    )


def _make_service() -> tuple[CleaningPlanService, DataProfileRepository, CleaningPlanRepository]:
    profile_repo = DataProfileRepository()
    plan_repo = CleaningPlanRepository()
    service = CleaningPlanService(profile_repo, plan_repo)
    return service, profile_repo, plan_repo


# ---------------------------------------------------------------------------
# 1. Service creates a cleaning plan from profile
# ---------------------------------------------------------------------------


def test_service_creates_plan() -> None:
    service, profile_repo, _ = _make_service()
    profile = _make_profile([_issue(IssueType.whitespace, "country")])
    profile_repo.save(profile)

    plan = service.create_cleaning_plan(profile.profile_id, _VERSION_ID)

    assert plan.cleaning_plan_id is not None
    assert plan.dataset_version_id == _VERSION_ID
    assert len(plan.plan_json.steps) == 1


# ---------------------------------------------------------------------------
# 2. Plan is saved in repository
# ---------------------------------------------------------------------------


def test_plan_is_saved_in_repo() -> None:
    service, profile_repo, plan_repo = _make_service()
    profile = _make_profile([_issue(IssueType.whitespace, "country")])
    profile_repo.save(profile)

    plan = service.create_cleaning_plan(profile.profile_id, _VERSION_ID)

    retrieved = plan_repo.get(plan.cleaning_plan_id)
    assert retrieved is not None
    assert retrieved.cleaning_plan_id == plan.cleaning_plan_id


def test_plan_retrievable_by_version() -> None:
    service, profile_repo, plan_repo = _make_service()
    profile = _make_profile([_issue(IssueType.whitespace, "country")])
    profile_repo.save(profile)

    plan = service.create_cleaning_plan(profile.profile_id, _VERSION_ID)

    plans = plan_repo.list_by_version(_VERSION_ID)
    assert any(p.cleaning_plan_id == plan.cleaning_plan_id for p in plans)


# ---------------------------------------------------------------------------
# 3. Summary counts are correct
# ---------------------------------------------------------------------------


def test_summary_counts_mixed_steps() -> None:
    service, profile_repo, _ = _make_service()
    issues = [
        _issue(IssueType.whitespace, "country"),           # auto-approved
        _issue(IssueType.duplicate_rows, None),             # requires approval
        _issue(IssueType.high_cardinality_category, "tag"), # auto-ignored
    ]
    profile = _make_profile(issues)
    profile_repo.save(profile)

    plan = service.create_cleaning_plan(profile.profile_id, _VERSION_ID)
    summary = plan.plan_json.summary

    assert summary is not None
    assert summary.total_steps == 3
    assert summary.steps_requiring_approval == 1
    assert summary.auto_ignored_steps == 1
    assert summary.auto_approved_steps == 1


def test_summary_row_count_change() -> None:
    service, profile_repo, _ = _make_service()
    issue = DataQualityIssue(
        issue_type=IssueType.duplicate_rows,
        table_name="orders",
        description="dups",
        affected_rows_count=10,
        affected_rows_percent=10.0,
        impact_level=ImpactLevel.high,
    )
    profile = _make_profile([issue])
    profile_repo.save(profile)

    plan = service.create_cleaning_plan(profile.profile_id, _VERSION_ID)
    assert plan.plan_json.summary.estimated_row_count_change == 10


# ---------------------------------------------------------------------------
# 4. Empty profile issues produce valid plan with zero steps
# ---------------------------------------------------------------------------


def test_empty_issues_yields_zero_steps() -> None:
    service, profile_repo, _ = _make_service()
    profile = _make_profile([])
    profile_repo.save(profile)

    plan = service.create_cleaning_plan(profile.profile_id, _VERSION_ID)

    assert plan.plan_json.steps == []
    assert plan.plan_json.summary.total_steps == 0
    assert plan.plan_json.summary.steps_requiring_approval == 0


# ---------------------------------------------------------------------------
# 5. Missing profile raises ValueError
# ---------------------------------------------------------------------------


def test_missing_profile_raises() -> None:
    service, _, _ = _make_service()
    with pytest.raises(ValueError, match="not found"):
        service.create_cleaning_plan(uuid.uuid4(), _VERSION_ID)


# ---------------------------------------------------------------------------
# Extra: plan JSON metadata is populated
# ---------------------------------------------------------------------------


def test_plan_json_metadata_populated() -> None:
    service, profile_repo, _ = _make_service()
    profile = _make_profile([_issue(IssueType.whitespace, "country")])
    profile_repo.save(profile)

    plan = service.create_cleaning_plan(profile.profile_id, _VERSION_ID)
    pj = plan.plan_json

    assert pj.plan_id == plan.cleaning_plan_id
    assert pj.profile_id == profile.profile_id
    assert pj.dataset_version_id == _VERSION_ID
    assert pj.schema_version == "1.0"
    assert pj.global_assumptions
