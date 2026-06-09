"""
Per-job-type handlers.

Signature: handler(job, repos, storage, llm) -> dict

Return a dict of result fields to merge into the job on completion
(e.g. result_type, result_id, output_dataset_version_id).
Return {} if there are no result fields.
Raise any exception to mark the job failed.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.schemas.cleaning import CleaningDecisionItem, CleaningDecisions, CleaningDecisionsJson
from app.schemas.job import Job
from app.services.cleaning_execution_service import CleaningExecutionService


def handle_noop(job: Job, repos: Any, storage: Any, llm: Any) -> dict:
    """Placeholder for job types not yet fully migrated."""
    return {}


def handle_execute_cleaning(job: Job, repos: Any, storage: Any, llm: Any) -> dict:
    p = job.payload_json
    cleaning_plan_id = UUID(p["cleaning_plan_id"])
    decisions_id = UUID(p["decisions_id"])
    executed_by_user_id = UUID(p["executed_by_user_id"])
    decision_items = [CleaningDecisionItem(**d) for d in p["decisions"]]

    decisions = CleaningDecisions(
        cleaning_decisions_id=decisions_id,
        cleaning_plan_id=cleaning_plan_id,
        decided_by_user_id=executed_by_user_id,
        decisions_json=CleaningDecisionsJson(decisions=decision_items),
        created_at=datetime.now(tz=UTC),
    )
    service = CleaningExecutionService(
        repos.dataset_version,
        repos.dataset_table,
        repos.cleaning_plan,
        repos.cleaning_result,
        storage,
    )
    result = service.execute_cleaning_plan(
        workspace_id=job.workspace_id,
        dataset_id=job.dataset_id,
        input_dataset_version_id=job.input_dataset_version_id,
        cleaning_plan_id=cleaning_plan_id,
        decisions=decisions,
        executed_by_user_id=executed_by_user_id,
    )
    return {
        "result_type": "cleaning_result",
        "result_id": result.cleaning_result_id,
        "output_dataset_version_id": result.output_dataset_version_id,
    }


def handle_upload_import(job: Job, repos: Any, storage: Any, llm: Any) -> dict:
    from app.services.upload_service import upload_dataset  # noqa: PLC0415

    p = job.payload_json
    pending_path: str = p["pending_storage_path"]
    filename: str = p["filename"]
    dataset_name: str | None = p.get("dataset_name")
    existing_dataset_id: UUID | None = (
        UUID(p["existing_dataset_id"]) if p.get("existing_dataset_id") else None
    )

    content = storage.read(pending_path)
    result = upload_dataset(
        content=content,
        filename=filename,
        workspace_id=job.workspace_id,
        dataset_name=dataset_name,
        repos=repos,
        storage=storage,
        existing_dataset_id=existing_dataset_id,
    )
    return {
        "result_type": "dataset_version",
        "output_dataset_version_id": result.dataset_version.dataset_version_id,
    }


def handle_profile_dataset(job: Job, repos: Any, storage: Any, llm: Any) -> dict:
    from app.services.profiling_service import create_profiles  # noqa: PLC0415

    p = job.payload_json
    dataset_version_id = UUID(p["dataset_version_id"])

    profiles = create_profiles(
        dataset_id=job.dataset_id,
        dataset_version_id=dataset_version_id,
        repos=repos,
        storage=storage,
    )
    profile_ids = [str(pr.profile_id) for pr in profiles]
    return {
        "result_type": "data_profile",
        "result_id": profiles[0].profile_id if profiles else None,
        "payload_json": {**job.payload_json, "profile_ids": profile_ids},
    }


def handle_execute_features(job: Job, repos: Any, storage: Any, llm: Any) -> dict:
    from app.schemas.features import FeatureDecisionItem, FeatureDecisions, FeatureDecisionsJson  # noqa: PLC0415
    from app.services.feature_service import FeatureService  # noqa: PLC0415

    p = job.payload_json
    feature_plan_id = UUID(p["feature_plan_id"])
    decisions_id = UUID(p["decisions_id"])
    executed_by_user_id = UUID(p["executed_by_user_id"])
    decision_items = [FeatureDecisionItem(**d) for d in p["decisions"]]

    decisions = FeatureDecisions(
        feature_decisions_id=decisions_id,
        feature_plan_id=feature_plan_id,
        decided_by_user_id=executed_by_user_id,
        decisions_json=FeatureDecisionsJson(decisions=decision_items),
        created_at=datetime.now(tz=UTC),
    )
    service = FeatureService(
        repos.profile,
        repos.dataset_version,
        repos.dataset_table,
        repos.feature_plan,
        repos.feature_result,
        llm,
        storage,
    )
    result = service.execute_feature_plan(
        workspace_id=job.workspace_id,
        dataset_id=job.dataset_id,
        input_dataset_version_id=job.input_dataset_version_id,
        feature_plan_id=feature_plan_id,
        decisions=decisions,
        executed_by_user_id=executed_by_user_id,
    )
    return {
        "result_type": "feature_result",
        "result_id": result.feature_result_id,
        "output_dataset_version_id": result.output_dataset_version_id,
    }


def handle_generate_visualizations(job: Job, repos: Any, storage: Any, llm: Any) -> dict:
    from app.schemas.visualization import VisualizationDecisionItem, VisualizationDecisions, VisualizationDecisionsJson  # noqa: PLC0415
    from app.services.visualization_service import VisualizationService  # noqa: PLC0415

    p = job.payload_json
    visualization_plan_id = UUID(p["visualization_plan_id"])
    decisions_id = UUID(p["decisions_id"])
    generated_by_user_id = UUID(p["generated_by_user_id"])
    decision_items = [VisualizationDecisionItem(**d) for d in p["decisions"]]

    decisions = VisualizationDecisions(
        visualization_decisions_id=decisions_id,
        visualization_plan_id=visualization_plan_id,
        decided_by_user_id=generated_by_user_id,
        decisions_json=VisualizationDecisionsJson(decisions=decision_items),
        created_at=datetime.now(tz=UTC),
    )
    service = VisualizationService(
        repos.profile,
        repos.dataset_table,
        repos.visualization_plan,
        repos.visualization_result,
        llm,
    )
    result = service.generate(visualization_plan_id, decisions)
    return {
        "result_type": "visualization_result",
        "result_id": result.visualization_result_id,
    }


# Map job_type string -> handler callable
HANDLERS: dict[str, Any] = {
    "upload_import": handle_upload_import,
    "profile_dataset": handle_profile_dataset,
    "execute_cleaning": handle_execute_cleaning,
    "execute_features": handle_execute_features,
    "generate_visualizations": handle_generate_visualizations,
}
