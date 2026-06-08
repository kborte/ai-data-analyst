# Milestone 1: Repo skeleton and schemas

## Build only

- repo skeleton
- FastAPI health endpoint
- core Pydantic schemas
- minimal frontend placeholder
- pytest/ruff setup
- basic tests
- README

Do not build upload, auth, database persistence, LLM calls, charts, or integrations.

## Structure

backend/app:
- main.py
- core/config.py
- core/errors.py
- core/logging.py
- api/routes/health.py
- schemas/common.py
- schemas/user.py
- schemas/workspace.py
- schemas/source.py
- schemas/dataset.py
- schemas/context_document.py
- schemas/profile.py
- schemas/cleaning.py
- schemas/features.py
- schemas/visualization.py
- schemas/insights.py
- schemas/analysis_run.py
- tools/llm/provider.py
- tests/unit/test_health.py
- tests/unit/test_schemas.py

frontend:
- app/page.tsx

## Health endpoint

GET /health returns:

{
  "status": "ok",
  "service": "ai-data-analyst-backend"
}

## Config

Add:
- APP_NAME
- ENV
- STORAGE_BACKEND = local
- LOCAL_STORAGE_DIR = storage/uploads

## Schemas

Use UUIDs, timezone-aware datetimes, string enums, and dict[str, Any] for flexible JSON.

Create schemas for:
- User
- Workspace
- WorkspaceMembership
- DataSource
- UploadedFile
- Dataset
- DatasetSource
- DatasetVersion
- DatasetTable
- DatasetPreview
- DatasetColumn
- ContextDocument
- ContextSummary
- DataProfile
- ColumnProfile
- DataQualityIssue
- CleaningPlan
- CleaningPlanJson
- CleaningStep
- CleaningDecisions
- CleaningDecisionsJson
- CleaningResult
- CleaningExecutionLogJson
- FeaturePlan
- FeaturePlanJson
- FeatureDefinition
- FeatureResult
- VisualizationSpec
- VisualizationResult
- Insight
- InsightReport
- AnalysisRun
- AnalysisStage

DatasetVersion must have:
- dataset_version_id
- dataset_id
- parent_version_id
- version_number
- version_type
- display_name
- description
- storage_path
- row_count
- column_count
- created_by_user_id
- created_at
- metadata

Do not encode version type/number in the ID.

Cleaning steps are stored in CleaningPlanJson.steps as JSON-compatible typed objects.

## Tests

Add tests for:
- health endpoint
- representative schema construction

## Done when

- backend starts
- /health works
- pytest passes
- ruff passes or reports no major issues
- README explains how to run