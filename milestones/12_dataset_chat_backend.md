# Milestone 12: Dataset Analytics Planner Lite

## Goal

Implement a lightweight dataset-aware analytics planner for asking questions over a selected `DatasetVersion`.

The system should support the core MVP loop:

* user asks an analytical question
* backend builds compact dataset context
* planner creates a structured analytics plan
* deterministic tools execute the validated plan
* backend returns a typed output
* table/visual outputs can be stored as artifacts when needed
* user can explicitly save useful outputs as `SavedView` or `SavedVisual`

M12 is not full chat infrastructure. It is an end-to-end analytics planner with optional lightweight multi-turn context.

## Core User Flow

Example:

User:

> Show revenue by month and channel.

Backend:

1. Receives the question scoped to `dataset_id` and `dataset_version_id`.
2. Builds compact context for the selected dataset version.
3. Uses a planner to classify the request.
4. Produces a structured plan.
5. Validates the plan.
6. Executes a safe deterministic tool against the selected DuckDB-backed dataset version.
7. Returns a typed output:

   * text
   * table
   * visual
   * mixed
8. Stores large table/visual data artifacts if needed.
9. Allows explicit saving through M11 helpers.

## Lightweight Multi-Turn Support

M12 may support follow-up questions by allowing the client to pass recent message history and prior output references in the request.

Examples:

* “now show that as a chart”
* “break it down by channel”
* “sort it descending”
* “save this visual”
* “what about last month?”

The backend may use recent messages only to resolve the current question.

M12 should not persist conversations.

Durable chat history, conversation records, tool-run history, and activity timeline belong to M13.

## Non-Goals

Do not implement:

* full chat UI
* durable conversation persistence
* long-term memory
* chat history tables
* dataset activity timeline
* full autonomous agent loops
* dynamic dashboards
* report generation
* cleaning execution
* feature execution
* arbitrary raw SQL execution
* broad LLM architecture rewrites
* production transaction hardening

Transactions, cleanup, retries, stale artifact handling, and broader storage/DB consistency hardening belong to M13.

## Planner Scope

The planner should classify the user request into one of these intents:

1. `text_answer`

   * direct explanation, summary, or interpretation

2. `table_result`

   * aggregation, filtered table, grouped summary, ranking, pivot-style table, or simple join

3. `visual_result`

   * chart request or question best answered visually

4. `mixed_result`

   * short explanation plus table and/or visual output

5. `save_table_result`

   * explicit request to save a prior table output as `SavedView`

6. `save_visual_result`

   * explicit request to save a prior visual output as `SavedVisual`

7. `unsupported`

   * request is outside the MVP tool scope

The planner may be rule-based or LLM-based.

If using an LLM, the LLM must only produce structured plans. Backend code must validate and execute the plan.

## Analytics Plan Contract

The planner should output a structured plan with fields such as:

* `intent`
* `dataset_id`
* `dataset_version_id`
* `reasoning_summary`
* `tool_name`
* `tool_spec`
* `expected_output_type`
* `needs_storage`
* `suggested_title`
* `suggested_description`
* optional `prior_output_ref`

The planner must not output arbitrary SQL.

The planner must not directly save outputs.

The planner must preserve `dataset_version_id`.

## Request Contract

The analytics request should include:

* `question`
* `dataset_id`
* `dataset_version_id`
* optional `recent_messages`
* optional `prior_output_refs`

Recent messages are client-provided context only.

They should not be persisted in M12.

## Recent Message Contract

A recent message may include:

* `role`: `user` or `assistant`
* `content`
* optional `output_refs`

Output refs may include:

* `output_id`
* `output_type`
* `title`
* `dataset_version_id`
* optional `source_spec_json`
* optional `chart_spec_json`
* optional `storage_backend`
* optional `storage_bucket`
* optional `storage_path`

The purpose is to let the planner resolve follow-up questions such as “show that as a chart” or “save this.”

## Typed Outputs

### Text Output

Used for direct answers.

Fields:

* `output_type`: `text`
* `dataset_version_id`
* `title`
* `content`
* optional `references`

### Table Output

Used for table-like analytical results.

Fields:

* `output_type`: `table`
* `dataset_version_id`
* `title`
* `description`
* `columns`
* `preview_rows`
* `row_count`
* `source_spec_json`
* optional `storage_backend`
* optional `storage_bucket`
* optional `storage_path`
* optional `storage_format`
* `can_save_as_view`: true

Large table outputs should be stored as artifacts.

Table outputs should not automatically create `SavedView`.

### Visual Output

Used for generated chart results.

Fields:

* `output_type`: `visual`
* `dataset_version_id`
* `title`
* `description`
* `chart_type`
* `chart_spec_json`
* `source_spec_json`
* optional `data_storage_backend`
* optional `data_storage_bucket`
* optional `data_storage_path`
* `can_save_to_visuals`: true

Visual outputs should not automatically create `SavedVisual`.

### Mixed Output

Used when the answer needs a short explanation plus one or more structured outputs.

Fields:

* `output_type`: `mixed`
* `dataset_version_id`
* `title`
* `summary`
* `outputs`

## Dataset Context Builder

Build compact context for the selected dataset version.

Include:

* dataset metadata
* dataset version metadata
* table names
* column names
* column types
* row counts where available
* profile summaries where available
* small safe previews only if already supported
* saved view/visual references only if useful and cheap

Do not include full datasets.

Do not include large row samples.

The context should be compact enough to pass to a planner or LLM.

## Safe Tools

Implement deterministic tools that operate on the selected DuckDB-backed dataset version.

MVP tools:

1. `preview_table`

   * preview selected columns from one table

2. `aggregate_table`

   * group by columns
   * aggregate metric columns
   * sort and limit

3. `filter_table`

   * select rows matching validated filters
   * select columns
   * sort and limit

4. `simple_join`

   * conservative join between two known tables
   * validated join keys
   * selected output columns
   * enforced row limit

5. `generate_visual`

   * generate a chart spec from a validated visual spec
   * reuse existing visualization utilities where possible

6. `save_table_result`

   * explicitly save a generated table output as `SavedView`
   * use existing M11 helpers

7. `save_visual_result`

   * explicitly save a generated visual output as `SavedVisual`
   * use existing M11 helpers

Allowed aggregations:

* count
* sum
* avg
* min
* max
* median if already safely supported

All tools must:

* validate table names
* validate column names
* enforce limits
* preserve `dataset_version_id`
* avoid mutation
* avoid arbitrary raw SQL from the user or LLM

## Storage Rules

Small outputs can be returned directly.

Large table outputs should be written to configured storage as result artifacts.

Use the existing storage abstraction from M9.

Suggested path pattern:

`workspaces/{workspace_id}/datasets/{dataset_id}/results/{result_id}.{format}`

Supported table artifact format for MVP:

* CSV

Optional:

* Parquet
* JSON

Do not store large result rows in Postgres.

Postgres should store only metadata and storage references.

## Save Rules

Generated outputs are not saved automatically.

If the user explicitly saves a table output:

* use M11 compatibility helpers
* create `SavedView`
* preserve `dataset_version_id`

If the user explicitly saves a visual output:

* use M11 compatibility helpers
* create `SavedVisual`
* preserve `dataset_version_id`

Follow-up requests like “save this” should use `prior_output_refs` or recent message output refs.

If no prior output reference is available, return a clear error asking for the output to save.

## API Routes

Suggested routes:

* `POST /datasets/{dataset_id}/versions/{dataset_version_id}/analytics/ask`
* `POST /analytics/table-results/save-as-view`
* `POST /analytics/visual-results/save-as-visual`

The ask route should:

* accept a user question
* accept optional recent message history
* accept optional prior output references
* build context
* create/validate a structured plan
* execute safe tools
* return typed output

Save routes should:

* require explicit user action
* call M11 compatibility helpers
* not regenerate analytics unless necessary

Routes must stay thin.

## M12A: Schemas and Plan Contracts

Implement schemas for:

* analytics request
* analytics response
* recent messages
* prior output references
* planner output
* text output
* table output
* visual output
* mixed output
* structured tool specs
* explicit save payloads

Acceptance criteria:

* all outputs preserve `dataset_version_id`
* table outputs expose `can_save_as_view`
* visual outputs expose `can_save_to_visuals`
* recent messages are accepted but not persisted
* prior output refs can represent table/visual outputs
* planner output is structured and validated
* invalid plans fail validation
* arbitrary raw SQL is not allowed as a plan output

## M12B: Dataset Context Builder

Implement compact context building for the selected dataset version.

Acceptance criteria:

* context includes dataset/version/table/column metadata
* context handles missing profiles gracefully
* context does not dump full datasets
* context is suitable for planner input
* context remains scoped to one `dataset_version_id`

## M12C: Safe Analytics Tools + Storage

Implement deterministic tools for:

* preview table
* aggregate table
* filter table
* simple join if feasible
* visual output generation

Also implement result artifact storage for large table outputs.

Acceptance criteria:

* tools validate table and column names
* tools enforce row limits
* tools operate on selected DuckDB-backed `DatasetVersion`
* tools return typed outputs
* large table outputs can be stored using the existing storage abstraction
* tools do not mutate dataset versions
* tools do not save views/visuals automatically
* tools do not execute arbitrary raw user SQL

## M12D: Lightweight Planner Service

Implement a lightweight planner service.

The planner should:

* accept a user question
* accept compact dataset context
* optionally use recent messages and prior output refs
* classify the request intent
* produce a structured validated plan
* select the appropriate safe tool
* return unsupported for out-of-scope requests

For MVP, use a rule-based planner if LLM integration is not ready.

If an LLM abstraction exists, keep calls behind the internal LLM service and validate all outputs.

Acceptance criteria:

* planner returns structured plans
* planner handles follow-up questions when recent messages or prior output refs are provided
* planner does not produce arbitrary SQL
* planner handles unsupported requests safely
* planner preserves `dataset_version_id`
* deterministic tools execute the plan, not the LLM directly

## M12E: Analytics API + Explicit Save Flow

Implement thin API routes for:

* asking an analytics question
* saving a table result as `SavedView`
* saving a visual result as `SavedVisual`

Acceptance criteria:

* ask endpoint returns typed text/table/visual/mixed output
* ask endpoint accepts optional recent messages and prior output refs
* recent messages are not persisted
* generated outputs are not automatically saved
* save endpoints use M11 helpers
* saved outputs preserve `dataset_version_id`
* routes stay thin

## M12F: Documentation and Tests

Add focused tests and docs.

Tests should cover:

* planner schema validation
* recent message schema validation
* prior output ref schema validation
* dataset context builder
* safe analytics tools
* storage-backed table outputs
* planner follow-up resolution
* analytics ask endpoint
* explicit save-as-view flow
* explicit save-as-visual flow
* invalid table/column handling
* unsupported request handling
* dataset version scoping

Documentation should explain:

* M12 is analytics planner lite, not full chat
* lightweight multi-turn is supported only through client-provided recent messages
* conversations are not persisted in M12
* outputs are scoped to the selected dataset version
* planner creates structured plans only
* deterministic tools execute validated specs
* arbitrary raw user SQL is not supported
* generated outputs are not automatically saved
* large outputs are stored as artifacts
* saved views/visuals use M11 helpers
