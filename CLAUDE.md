Create Milestone 1 for this project.

Read and follow `CLAUDE.md` first. Do not proceed beyond Milestone 1.

## Goal

Create the initial repo skeleton and core Pydantic schemas for an agentic AI data analyst app.

For this milestone, build only:

1. clean repository structure
2. backend FastAPI health endpoint
3. core Pydantic schemas
4. minimal frontend placeholder
5. pytest/ruff setup
6. basic tests for health endpoint and schema construction
7. README files if useful

Do not implement file upload, data processing, LLM calls, database persistence, chart rendering, authentication, or integrations.

## Required repo structure

Create this structure, adjusting only if framework defaults require minor changes:

```text
ai-data-analyst/
  backend/
    app/
      __init__.py
      main.py

      core/
        __init__.py
        config.py
        errors.py
        logging.py

      api/
        __init__.py
        routes/
          __init__.py
          health.py

      schemas/
        __init__.py
        common.py
        user.py
        workspace.py
        source.py
        dataset.py
        context_document.py
        profile.py
        cleaning.py
        features.py
        visualization.py
        insights.py
        analysis_run.py

      services/
        __init__.py

      tools/
        __init__.py
        files/
          __init__.py
        data/
          __init__.py
        charts/
          __init__.py
        llm/
          __init__.py
          provider.py

      repositories/
        __init__.py

      tests/
        __init__.py
        unit/
          __init__.py
          test_health.py
          test_schemas.py

    pyproject.toml
    README.md

  frontend/
    app/
      page.tsx
    package.json
    README.md

  docker-compose.yml
  CLAUDE.md
  README.md
```

## Backend requirements

Implement a minimal FastAPI app.

Add:

```text
GET /health
```

Expected response:

```json
{
  "status": "ok",
  "service": "ai-data-analyst-backend"
}
```

## Config requirements

In `backend/app/core/config.py`, include minimal config for:

```text
APP_NAME
ENV
STORAGE_BACKEND
LOCAL_STORAGE_DIR
```

Use local storage default:

```text
STORAGE_BACKEND = "local"
LOCAL_STORAGE_DIR = "storage/uploads"
```

Do not implement actual upload/storage logic yet.

## Schema requirements

Use Pydantic schemas with UUIDs and timezone-aware datetimes where appropriate.

Create schemas for:

* User
* Workspace
* WorkspaceMembership
* DataSource
* UploadedFile
* Dataset
* DatasetSource
* DatasetVersion
* DatasetTable
* DatasetPreview
* DatasetColumn
* ContextDocument
* ContextSummary
* NumericSummary
* DateSummary
* ColumnProfile
* DataQualityIssue
* DataProfile
* CleaningPlan
* CleaningPlanJson
* CleaningStep
* CleaningIssue
* CleaningRecommendation
* CleaningOperation
* CleaningPreview
* CleaningDecisions
* CleaningDecisionsJson
* CleaningDecisionItem
* ResolvedCleaningPlanJson
* ResolvedCleaningStep
* CleaningResult
* CleaningExecutionLogJson
* CleaningStepResult
* FeaturePlan
* FeaturePlanJson
* FeatureDefinition
* FeatureDecisions
* FeatureDecisionsJson
* FeatureDecisionItem
* FeatureResult
* FeatureExecutionLogJson
* VisualizationSpec
* VisualizationResult
* Insight
* InsightReport
* AnalysisRun
* AnalysisStage
* AnalysisArtifactRef

In `schemas/common.py`, define string enums for:

* ArtifactStatus
* WorkspaceRole
* DataSourceKind
* UploadedFileKind
* DatasetSourceRole
* DatasetVersionType
* DataType
* ImpactLevel
* ApprovalStatus
* DefaultDecision
* UserDecision
* IssueType
* CleaningOperationType
* FeatureOperationType
* ChartType
* InsightSeverity
* AnalysisRunStatus
* ExecutionStatus

Make schemas practical and typed, but do not over-engineer.

Use `dict[str, Any]` for flexible JSON fields like metadata, parameters, summaries, warnings, and specs.

## DatasetVersion schema requirement

Do not encode version type or version number into the primary key.

`DatasetVersion` must include:

```text
dataset_version_id: UUID
dataset_id: UUID
parent_version_id: UUID | None
version_number: int
version_type: DatasetVersionType
display_name: str | None
description: str | None
storage_path: str | None
row_count: int | None
column_count: int | None
created_by_user_id: UUID
created_at: datetime
metadata: dict[str, Any]
```

Multiple versions may share the same `version_type`.

Example: a user may clean and save several times, creating multiple versions where `version_type = cleaned`.

Conceptually, version numbers should be unique within each dataset:

```text
unique(dataset_id, version_number)
```

Do not implement database constraints yet, but design schemas with this model in mind.

## Cleaning schema requirements

Cleaning steps should be stored as JSON for flexibility.

The cleaning model should support:

```text
CleaningPlan.plan_json
CleaningDecisions.decisions_json
CleaningResult.execution_log_json
```

Each cleaning step should contain:

```text
step_id
sequence_order
issue
recommendation
operation
preview
```

Each issue should contain:

```text
issue_type
table_name
column_name
description
affected_rows_count
affected_rows_percent
sample_values
```

Each recommendation should contain:

```text
action_type
recommended_action
rationale
impact_level
affects_key_metrics
requires_human_approval
default_decision
```

Each operation should contain:

```text
operation_type
parameters
```

Each preview should contain:

```text
rows_before
estimated_rows_after
estimated_rows_removed
columns_changed
metrics_potentially_affected
```

Include comments/docstrings explaining:

* low-impact issues may be ignored when affected rows are below 10%, the column is not used in key metrics, and the issue does not affect joins/pivots/filters
* human approval is required for row-count-changing operations, key metric columns, ID/date columns, or issues affecting at least 10% of rows
* original datasets must not be overwritten
* cleaning execution should create a new dataset version in later milestones

## LLM provider abstraction

In `tools/llm/provider.py`, create:

* `LLMProvider` protocol or abstract base class
* `FakeLLMProvider`

Do not call external LLM APIs.

## Frontend requirements

Create a minimal Next.js page with:

* project title
* short product description
* placeholder sections:

  * upload dataset
  * profile data
  * cleaning plan
  * feature engineering
  * visualization
  * insight report

No real API integration yet.

## Testing requirements

Add tests for:

1. health endpoint
2. constructing representative schema objects for:

   * User
   * Workspace
   * DataSource
   * UploadedFile
   * Dataset
   * DatasetVersion
   * DatasetTable
   * ContextDocument
   * DataProfile
   * CleaningPlan
   * CleaningDecisions
   * CleaningResult
   * FeaturePlan
   * VisualizationSpec
   * InsightReport
   * AnalysisRun

Tests must be deterministic and must not require external services.

## Code quality

Set up `backend/pyproject.toml` with:

* pytest
* ruff
* Python 3.12 target
* reasonable line length

Use type hints.

Keep files small and readable.

## README requirements

Create a root README explaining:

* project purpose
* milestone scope
* domain model summary
* repo structure
* how to run backend
* how to run tests
* how to run frontend

## Acceptance criteria

Milestone 1 is complete when:

1. repo skeleton exists
2. FastAPI app starts
3. `/health` works
4. core schemas exist
5. schema tests pass
6. health test passes
7. README exists
8. no out-of-scope features are implemented

Before editing files, briefly restate your implementation plan.

After editing files, summarize:

* files created
* tests added
* commands to run
* assumptions/limitations
