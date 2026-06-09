# CLAUDE.md

## Project

This project is an agentic AI data analyst app.

The app helps users upload messy business datasets, understand data quality issues, approve safe cleaning/feature suggestions, ask dataset-scoped analytical questions, generate reusable views/visuals, and preserve intermediate dataset versions.

Use a staged milestone approach. Implement only the milestone section explicitly requested.

---

## Execution Discipline

When working on a milestone:

* Implement only the requested milestone section.
* Do not expand the task into a broader architecture rewrite.
* Do not use subagents.
* Do not review the whole codebase unless explicitly asked.
* Read only files needed for the current task.
* Do not print full file contents unless asked.
* Before editing, give a plan with max 3 bullets unless the prompt says otherwise.
* After editing, summarize with max 5 bullets unless the prompt says otherwise.
* Run only relevant tests first.
* Run the full suite only if cheap or explicitly requested.
* If something is ambiguous, choose the smallest working implementation consistent with existing code.

Do not implement out-of-scope features just because related code is nearby.

---

## Product Contract

Inside a dataset, the user can:

* ask analytical questions
* generate table-like outputs with aggregations, pivots, joins, filters, or comparisons
* generate visualizations
* ask to add calculated features or metrics
* ask to clean the data
* save dataset versions, saved views, and saved visuals
* download table outputs or visual outputs

Use this rule:

```text
If the request changes the reusable dataset state:
  create a new DatasetVersion.

If the request creates a reusable table-like output:
  create a SavedView.

If the request creates a reusable chart:
  create a SavedVisual.

If the request is only a one-time answer:
  return the answer without persistence unless the user saves/downloads it.
```

Examples:

* “What was revenue over the last 6 months?” → text/table answer, no new version.
* “Show revenue by month and channel” → table output; can be saved as a view.
* “Plot revenue over time” → visual output; can be saved as a visual.
* “Add AOV as a column” → feature execution; creates a new dataset version.
* “Clean missing revenue values” → cleaning execution; creates a new dataset version.
* “Join orders and customers for this table” → saved view if saved.
* “Add joined orders_customers as a reusable table in the dataset” → new dataset version.

Chat must not silently mutate data. Dataset mutation requires explicit user approval/action.

---

## Code Style

Use:

* Python 3.12
* FastAPI for backend routes
* Pydantic for schemas
* SQLAlchemy + Alembic for persistence
* PostgreSQL/Supabase Postgres for metadata
* Supabase Storage for persistent file artifacts
* DuckDB for per-version analytical dataset artifacts
* pytest for tests
* Ruff for linting/formatting
* uv for Python dependency and command management

Backend structure should follow:

```text
route -> service -> repository/storage/tool
```

Routes must stay thin.

Routes should not contain:

* pandas logic
* DuckDB transformation logic
* LLM orchestration logic
* business logic
* storage implementation details

Services orchestrate workflows.

Repositories handle database persistence.

Storage backends handle persistent files.

Tools handle deterministic low-level operations such as:

* file parsing
* profiling
* cleaning execution
* feature execution
* DuckDB operations
* chart spec generation

---

## Domain Model Invariants

A `Dataset` is a logical analysis container, not a single uploaded file.

A dataset can have:

* many `DataSource`s
* many `UploadedFile`s through `DatasetSource`
* many `DatasetVersion`s

A `DatasetVersion` is a materialized state of the dataset.

A `DatasetVersion` can have many `DatasetTable`s.

Analysis artifacts belong to a `DatasetVersion`, not directly to an `UploadedFile`.

Profiling, cleaning, feature engineering, visualization, saved views, saved visuals, and chat should operate on a selected `DatasetVersion`.

Uploading an additional file to an existing dataset must not create a new `Dataset`.

Cleaning and feature execution create new `DatasetVersion`s.

Visualization, saved views, saved visuals, and chat outputs read from a selected `DatasetVersion` and do not mutate it.

Existing dataset versions must not be overwritten.

---

## Dataset Version Rules

Do not encode version type or version number into the primary key.

`DatasetVersion` should include:

* `dataset_version_id`
* `dataset_id`
* `parent_version_id`
* `version_number`
* `version_type`
* `display_name`
* `description`
* storage metadata
* row/column counts if applicable
* created metadata

Multiple versions may share the same `version_type`.

Example:

```text
v1 original
v2 cleaned
v3 cleaned
v4 enriched
```

Version numbers should be unique within each dataset.

Use beginner-facing labels where relevant:

* Original upload
* Cleaned copy
* Copy with calculated metrics
* Current copy

---

## Storage and Execution Architecture

Use this architecture for uploaded and derived user data:

* Supabase Postgres stores metadata, plans, decisions, jobs, lineage, and result records.
* Supabase Storage stores persistent files: raw uploads, DuckDB dataset version files, and generated result artifacts.
* DuckDB work happens inside backend services/workers using temporary local files only.
* Do not store raw uploads or `.duckdb` binary files in Postgres.
* Do not store persistent dataset files on local disk.
* Temporary local files are allowed only as scratch files during one request/job and must be cleaned up.

Dataset version storage rule:

* Each materialized `DatasetVersion` should point to one `.duckdb` artifact in storage.
* A `.duckdb` version file may contain many tables.
* Existing `.duckdb` version files are immutable.
* Cleaning and feature execution create new `.duckdb` version files.
* Visualization reads from an existing `.duckdb` version and does not mutate it.

Storage path convention:

```text
raw uploads:
workspaces/{workspace_id}/datasets/{dataset_id}/raw_uploads/{uploaded_file_id}_{filename}

dataset versions:
workspaces/{workspace_id}/datasets/{dataset_id}/versions/v{version_number}_{version_type}.duckdb

result artifacts:
workspaces/{workspace_id}/datasets/{dataset_id}/results/{artifact_id}.{ext}
```

Postgres should store storage metadata such as:

* `storage_backend`
* `storage_bucket`
* `storage_path`
* `storage_format`
* `row_count`
* `column_count`

---

## Supabase Rules

Supabase Postgres is the metadata/control database.

Supabase Storage is for persistent file artifacts.

Do not use Supabase Postgres for arbitrary dynamic user data tables unless a milestone explicitly asks for it.

Do not store large table outputs directly in Postgres.

Use storage paths and metadata references instead.

Do not add Supabase Auth unless a milestone explicitly asks for authentication.

---

## DuckDB Rules

DuckDB is the analytical execution layer and dataset artifact format.

Use DuckDB for:

* imported dataset versions
* multi-table dataset snapshots
* profiling reads
* cleaning execution
* feature execution
* visualization query execution
* saved view generation later

Do not treat DuckDB as the app metadata database.

Do not use one shared mutable DuckDB file for all users or all datasets.

Prefer one immutable `.duckdb` file per materialized dataset version.

Safe pattern:

```text
read v1_original.duckdb
write v2_cleaned.duckdb
```

Unsafe pattern:

```text
keep mutating current.duckdb forever
```

---

## Background Job Rules

Heavy data-processing work should not run inside FastAPI request handlers long-term.

FastAPI should:

* validate requests
* create jobs
* return `job_id`
* serve job status/results
* read/write metadata

Workers should:

* parse uploaded files
* create DuckDB version files
* profile datasets
* execute cleaning
* execute features
* generate visualization data
* run heavy DuckDB queries

Use one worker first.

Design job claiming so multiple workers can be added later, but do not add distributed systems complexity unless explicitly requested.

---

## Cleaning Rules

Cleaning is human-in-the-loop.

Use this model:

```text
CleaningPlan = immutable proposal
CleaningDecisions = user approvals/rejections/modifications
CleaningResult = what actually happened
DatasetVersion = resulting cleaned copy
```

Do not mutate `CleaningPlan.plan_json.steps` to store approvals.

Per-step approval belongs in `CleaningDecisions`.

Cleaning execution must be deterministic.

LLMs may suggest plans, but deterministic code applies approved operations.

Original datasets must not be overwritten.

Row-count-changing operations require human approval.

Human approval is required for:

* key metric columns
* ID columns
* date columns
* join/pivot/filter columns
* issues affecting at least 10% of rows
* operations that drop rows or change row counts

Low-impact issues may be ignored when:

* affected rows are below 10%
* the column is not used in key metrics
* the issue does not affect joins, pivots, or filters

---

## Feature Engineering Rules

Feature engineering is human-in-the-loop.

Use this model:

```text
FeaturePlan = immutable proposal
FeatureDecisions = user approvals/rejections
FeatureResult = execution log
DatasetVersion = new enriched copy
```

Do not mutate `FeaturePlan.plan_json.features` to store approvals.

Feature execution must be deterministic.

Do not execute arbitrary Python or arbitrary model-generated formulas.

`custom_formula` may exist in schemas but should not execute unless a later milestone explicitly implements safe formula execution.

Feature engineering may create:

* new columns in existing tables
* derived tables
* reusable metrics

If the feature becomes part of the reusable dataset state, create a new `DatasetVersion`.

---

## Visualization Rules

Visualization generation should be deterministic unless a milestone explicitly adds LLM-based chart planning.

Use broad chart types:

* bar
* line
* pie
* scatter

Visualization reads from a selected `DatasetVersion`.

Visualization does not mutate dataset versions.

Generated chart specs should be frontend-friendly JSON.

Saved visuals are separate artifacts.

Do not implement dynamic dashboards unless explicitly requested.

---

## Saved Views and Saved Visuals

A saved view is a saved table-like result.

Examples:

* grouped aggregation
* pivot-style summary
* joined result
* filtered table
* feature-derived table
* chat-generated table output

A saved visual is a saved chart result.

Saved views and saved visuals must be scoped to:

* `workspace_id`
* `dataset_id`
* `dataset_version_id`

Saved views should support:

* preview
* delete
* download as CSV/Excel if supported
* reuse in future analysis

Saved visuals should support:

* render
* delete
* download as PNG client-side if supported
* download chart data if supported

Do not implement dynamic dashboards in the MVP.

Do not add drag-and-drop dashboard layouts unless explicitly requested.

Large saved view data should live in storage, not Postgres.

Postgres stores metadata and storage paths.

---

## Dataset Chat Rules

Chat is scoped to:

* workspace
* dataset
* selected dataset version

Chat outputs can be:

* text
* table result
* visual result

Table outputs should support:

* Save as view
* Download CSV
* Download Excel if supported

Visual outputs should support:

* Save to visuals
* Download PNG
* Download data

Chat should not directly mutate dataset versions.

Table outputs may be saved as views only through explicit user action.

Visual outputs may be saved as visuals only through explicit user action.

Do not execute arbitrary unsafe SQL from the model.

Prefer structured query specs and deterministic tools.

---

## Frontend Product Model

The frontend should use the user’s mental model, not raw backend object names.

User-facing navigation:

* Workspaces
* Workspace page with datasets
* Dataset playground

Dataset playground sections:

* Tables
* Versions
* Views
* Visuals
* Chat

Recommended routes:

```text
/workspaces
/workspaces/{workspaceId}
/workspaces/{workspaceId}/datasets/{datasetId}?tab=tables
/workspaces/{workspaceId}/datasets/{datasetId}?tab=versions
/workspaces/{workspaceId}/datasets/{datasetId}?tab=views
/workspaces/{workspaceId}/datasets/{datasetId}?tab=visuals
/workspaces/{workspaceId}/datasets/{datasetId}?tab=chat
```

Dataset page rule:

* The dataset page must always have a selected/current dataset version.
* Tables, views, visuals, and chat outputs must be scoped to a dataset version.
* If a view or visual was created from an older version, show that clearly.

Use beginner-friendly labels:

* Current copy
* Original upload
* Cleaned copy
* Copy with calculated metrics
* Tables
* Saved views
* Saved visuals

Hide technical terms by default:

* `DatasetVersion`
* `DatasetTable`
* `VisualizationResult`
* `SavedView`
* `storage_path`
* `artifact`
* `metadata`
* `execution_log_json`

Use “Show details” for technical metadata if needed.

---

## LLM Rules

Do not call external LLM APIs unless the milestone explicitly asks for it.

All LLM access should go through a provider/service abstraction.

Do not call OpenAI, Anthropic, or other providers directly from random routes/services.

Use a wrapper such as:

```text
llm provider -> llm service -> domain service
```

Fake providers should be used in tests.

LLMs may propose plans, queries, or explanations.

Deterministic tools should execute data operations.

---

## Testing Rules

Tests must be deterministic.

Tests should not require live external services unless explicitly marked integration tests.

Mock or fake:

* Supabase Storage
* LLM providers
* external APIs

Use small in-test DataFrames/files.

Do not require real user data.

---

## Milestone Roadmap

Completed or existing:

* M1: repo skeleton + schemas
* M2: file upload + in-memory repositories
* M3: deterministic profiling
* M4: cleaning plan generation
* M5: cleaning decisions + deterministic cleaning execution
* M6: feature engineering
* M7: SQL database persistence
* M8: visualization generation

Next backend milestones:

* M9: Supabase Storage + DuckDB Dataset Versions
* M10: Background Job System + One Worker
* M11: Saved Views + Saved Visuals Backend
* M12: Dataset Chat Backend
* M13: Production Hardening

Frontend milestones:

* FE1: Dataset Playground
* FE2: Chat/save/download polish if needed
