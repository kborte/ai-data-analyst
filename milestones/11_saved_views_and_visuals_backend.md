# Milestone 11: Saved Views + Saved Visuals Backend

## Goal

Add backend support for saved table-like outputs and saved chart outputs inside a dataset playground.

This milestone supports the frontend tabs:

* Views
* Visuals

No frontend implementation. No dynamic dashboards. No drag-and-drop layouts. No dataset chat backend. No LLM calls.

Saved artifacts must be scoped to:

* workspace
* dataset
* dataset version

---

## Core Distinction

`VisualizationResult` and `SavedVisual` are different artifacts.

`VisualizationResult` is a generated chart output from a visualization plan, deterministic chart tool, or future chat request.

It may be temporary or execution-linked.

`SavedVisual` is a user-saved reusable chart asset shown in the dataset Visuals tab.

A `VisualizationResult` may become a `SavedVisual` only after explicit user action, such as “Save to Visuals”.

Do not assume every generated chart is automatically saved.

Similarly:

`TableResult` or query output is a generated table-like output.

`SavedView` is a user-saved reusable table-like asset shown in the dataset Views tab.

Do not assume every generated table is automatically saved.

---

## Product Rules

A saved view is a reusable table-like result.

Examples:

* revenue by month and channel
* customer segment summary
* campaign ROAS summary
* pivot-style category by month table
* joined orders and customers result
* filtered high-value customers table
* chat-generated table output, later

A saved visual is a reusable chart result.

Examples:

* revenue over time
* revenue by channel
* ad spend vs revenue
* AOV by segment
* monthly campaign performance

Saved views and saved visuals do **not** create new `DatasetVersion`s.

They are artifacts over a selected `DatasetVersion`.

If the user wants to add a result back into the reusable dataset state, that belongs to feature/derived-table execution and should create a new `DatasetVersion`.

Do not implement dynamic dashboards in M11.

---

## Storage Rules

Supabase Postgres stores metadata.

Supabase Storage or the configured storage backend stores large artifacts.

Do not store large table result rows in Postgres.

Saved view data should be stored through the storage abstraction.

Saved visual chart specs can be stored in Postgres JSONB if reasonably small.

Large chart data should be stored through the storage abstraction if needed.

Temporary local files are allowed only as scratch files and must be cleaned up.

---

## M11A: Saved View Schemas, Models, Repository, and Storage

Implement saved views as first-class backend artifacts.

Required fields:

* saved_view_id
* workspace_id
* dataset_id
* dataset_version_id
* name
* description
* source_type
* source_spec_json
* storage_backend
* storage_bucket
* storage_path
* storage_format
* row_count
* column_count
* created_at
* created_by_user_id if existing project patterns support it
* metadata_json if useful

Suggested `source_type` values:

* query
* aggregation
* pivot
* join
* filter
* feature_result
* visualization_result
* chat_output
* manual

Suggested `storage_format` values:

* csv
* parquet
* json

Rules:

* saved views are scoped to a dataset version
* saved views do not mutate dataset versions
* saved view metadata lives in Postgres
* saved view data lives in storage
* do not implement API routes in M11A
* do not implement saved visuals in M11A
* do not implement chat
* do not implement frontend

Acceptance criteria:

* saved view schema/model exists
* saved view repository exists
* saved view metadata can be created/read/listed/deleted
* saved view artifact can be saved through storage abstraction
* tests cover saved view schema/repository/storage behavior

---

## M11B: Saved View API, Preview, and Download

Implement thin API routes for saved views.

Routes:

* `GET /datasets/{dataset_id}/versions/{dataset_version_id}/views`
* `POST /datasets/{dataset_id}/versions/{dataset_version_id}/views`
* `GET /views/{view_id}`
* `DELETE /views/{view_id}`
* `GET /views/{view_id}/preview`
* `GET /views/{view_id}/download?format=csv`

Optional if easy:

* `GET /views/{view_id}/download?format=xlsx`

Preview behavior:

* return limited rows only
* include columns
* include row_count if known
* do not return entire large artifacts

Download behavior:

* return CSV bytes/stream or signed URL, depending on current storage abstraction
* do not load huge artifacts into memory unnecessarily if avoidable
* if only CSV is supported, reject unsupported formats clearly

Rules:

* routes must stay thin
* no heavy analysis in routes
* no arbitrary query execution in routes
* validate that view belongs to requested dataset/version where applicable
* do not implement saved visuals
* do not implement frontend
* do not implement chat

Acceptance criteria:

* views can be listed by dataset version
* view detail route works
* view preview returns limited rows
* view download works for CSV or returns a valid URL/response
* delete removes metadata and artifact where feasible
* tests cover route behavior

---

## M11C: Saved Visual Schemas, Models, Repository, and API

Implement saved visuals as first-class backend artifacts.

A saved visual is a saved chart result created from:

* existing `VisualizationResult`
* chart spec generated by visualization planner
* chart spec returned by future chat output
* saved view if chart data is based on a saved table
* direct chart query result

Required fields:

* visual_id
* workspace_id
* dataset_id
* dataset_version_id
* title
* description
* chart_type
* chart_spec_json
* source_type
* source_visualization_result_id if applicable
* source_view_id if applicable
* source_spec_json
* data_storage_backend, nullable
* data_storage_bucket, nullable
* data_storage_path, nullable
* created_at
* created_by_user_id if existing project patterns support it
* metadata_json if useful

Routes:

* `GET /datasets/{dataset_id}/versions/{dataset_version_id}/visuals`
* `POST /datasets/{dataset_id}/versions/{dataset_version_id}/visuals`
* `GET /visuals/{visual_id}`
* `DELETE /visuals/{visual_id}`
* `GET /visuals/{visual_id}/data` if chart data is stored separately

Rules:

* saved visuals are scoped to a dataset version
* saved visuals do not mutate dataset versions
* store chart specs in Postgres JSONB when reasonably small
* store large chart data artifacts in storage if needed
* do not implement dashboard layouts
* do not implement frontend
* do not generate PNG server-side in this milestone
* PNG download should be a frontend/client-side feature later

Acceptance criteria:

* saved visual schema/model exists
* saved visual repository exists
* saved visual API works
* visuals can be listed by dataset version
* visual can be created from chart spec
* visual can reference existing `VisualizationResult`
* visual can be deleted
* tests cover schema/repository/routes

---

## M11D: Compatibility Helpers for Generated Outputs

Add service helpers so generated outputs can be saved explicitly.

Implement helpers such as:

* `save_view_from_table_result`
* `save_view_from_storage_artifact`
* `save_visual_from_chart_spec`
* `save_visual_from_visualization_result`

Rules:

* do not add actual chat/LLM logic in M11
* do not add dynamic dashboards
* do not mutate dataset versions
* saved views and visuals must preserve `dataset_version_id`
* if source version is older than current dataset version, keep the original version reference
* do not automatically save every generated result
* saving must be explicit

Acceptance criteria:

* existing visualization result can be saved as a saved visual
* chart spec can be saved as a saved visual
* table-like result can be saved as a saved view
* saved artifacts keep correct workspace/dataset/version scope
* tests cover version scoping and explicit-save behavior

---

## M11E: Documentation and Tests

Finalize documentation and compatibility tests.

Update README or backend docs with:

* what saved views are
* what saved visuals are
* distinction between generated results and saved artifacts
* version scoping
* available routes
* storage behavior
* what is intentionally not included: dashboards, chat, frontend

Add/adjust tests for:

* saved view schemas/models
* saved view repository
* saved view storage behavior
* saved view API routes
* saved view preview/download
* saved visual schemas/models
* saved visual repository
* saved visual API routes
* saving visual from existing visualization result
* version scoping for views/visuals

Do not add:

* frontend
* dataset chat backend
* dynamic dashboards
* drag-and-drop layouts
* PNG server-side generation
* Supabase Auth
* LLM calls

Acceptance criteria:

* relevant M11 tests pass
* docs explain saved views and saved visuals
* generated results are not automatically saved
* saved artifacts are scoped to dataset versions
