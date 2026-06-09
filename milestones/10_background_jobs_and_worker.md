# Milestone 10: Background Job System + One Worker

## Goal

Move heavy dataset processing out of FastAPI request handlers and into one background worker.

FastAPI should create jobs, return `job_id`, and serve job status/results.

The worker should execute queued jobs using existing services and the storage/DuckDB infrastructure from M9.

Use one simple worker process for now.

No frontend implementation. No LLM calls. No chat. No saved views. No saved visuals. No dynamic dashboards. No Celery/RQ unless already present and necessary.

---

## Architecture Rules

FastAPI should handle:

* request validation
* metadata reads/writes
* job creation
* job status/result lookup
* cheap validation endpoints

The worker should handle:

* upload import if it parses files or creates DuckDB artifacts
* dataset profiling
* cleaning execution
* feature execution
* visualization generation
* heavy DuckDB queries
* temporary file cleanup

Rules:

* Do not run heavy DuckDB/pandas work inside FastAPI request handlers.
* Do not duplicate business logic in the worker.
* Worker handlers should call existing services/tools.
* Existing dataset version files are immutable.
* Any job that changes reusable dataset state must create a new `DatasetVersion`.
* Jobs should store enough metadata for the frontend to poll progress and show results.
* Design job claiming so more workers can be added later, but do not add unnecessary distributed-systems complexity.

---

## M10A: Job Schemas, Models, Repository, and API

Implement job metadata.

Required job fields:

* job_id
* workspace_id
* dataset_id
* input_dataset_version_id, nullable where not applicable
* job_type
* status
* payload_json
* result_type
* result_id
* output_dataset_version_id
* error_message
* progress_message
* created_at
* started_at
* completed_at

Job types:

* upload_import
* profile_dataset
* execute_cleaning
* execute_features
* generate_visualizations

Statuses:

* queued
* running
* completed
* failed
* cancelled

Routes:

* `GET /jobs/{job_id}`
* `GET /datasets/{dataset_id}/jobs`

Optional:

* `POST /jobs/{job_id}/cancel`

Rules:

* Routes must stay thin.
* No DuckDB/pandas work in job routes.
* No worker loop in M10A.
* Do not migrate existing flows yet.
* Do not implement frontend.

Acceptance criteria:

* job schema/model exists
* job repository can create/read/list/update jobs
* job status route works
* dataset jobs route works
* tests cover job lifecycle metadata

---

## M10B: Worker Loop and Job Claiming

Implement one background worker process.

Worker command:

```bash
uv run python -m app.worker
```

Worker behavior:

1. claim next queued job
2. mark it running
3. execute handler based on `job_type`
4. mark completed or failed
5. store result metadata
6. sleep when no jobs exist

Use safe job claiming.

Preferred Postgres pattern if supported:

```sql
SELECT *
FROM jobs
WHERE status = 'queued'
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

If the existing repository setup makes this too large, implement the smallest safe repository-level claim method consistent with the current code and document the limitation.

Rules:

* One worker is enough for M10.
* Job handlers should call services, not duplicate business logic.
* Worker should clean temporary files after each job where applicable.
* Failed jobs should capture `error_message`.
* Completed jobs should store `result_type`, `result_id`, and/or `output_dataset_version_id` where applicable.
* Do not add Celery/RQ unless required by existing code.
* Do not migrate real heavy flows yet unless needed for a fake/test job.

Acceptance criteria:

* worker can claim and run a fake/test job
* failed job is marked failed
* completed job is marked completed
* no queued job causes worker to wait/sleep
* tests cover claim/run/fail behavior where feasible

---

## M10C: Move Cleaning Execution to Jobs

Migrate cleaning execution to the job system first.

Old behavior:

* `POST /cleaning-plans/{cleaning_plan_id}/execute` executes immediately

New behavior:

* `POST /cleaning-plans/{cleaning_plan_id}/execute` creates an `execute_cleaning` job
* route returns `job_id` and `status`
* worker executes cleaning
* worker creates `CleaningResult`
* worker creates cleaned `DatasetVersion`
* worker updates job with `result_type`, `result_id`, and `output_dataset_version_id`

Job payload should include:

* cleaning_plan_id
* decisions_id or decisions payload, according to existing implementation
* input_dataset_version_id if not inferable

Rules:

* Do not change cleaning business logic broadly.
* Do not mutate existing dataset version files.
* Do not put DuckDB/pandas logic inside routes.
* Preserve existing cleaning result behavior.
* Frontend can poll `GET /jobs/{job_id}`.
* If existing tests expect synchronous cleaning response, update tests to expect job response.

Acceptance criteria:

* cleaning execute route returns job response
* worker runs cleaning job end-to-end
* job links to `CleaningResult`
* job links to output `DatasetVersion`
* previous version remains unchanged
* tests cover route/job/worker flow

---

## M10D: Move Remaining Heavy Flows to Jobs

Migrate remaining heavy flows to jobs where appropriate.

Move to worker:

* `upload_import` if upload parsing creates DuckDB artifacts
* `profile_dataset`
* `execute_features`
* `generate_visualizations`

Keep in FastAPI:

* metadata reads
* list/get endpoints
* cheap validation routes
* saved result fetches
* small previews only if already cheap

Expected route behavior:

* endpoints that trigger heavy work should create a job
* response should include `job_id` and `status`
* result IDs should be available from job status after completion

Rules:

* Do not change business logic broadly.
* Do not implement frontend.
* Do not implement chat.
* Do not add saved views or saved visuals.
* Do not add dynamic dashboards.
* Do not add new analytics features.
* Keep routes thin.
* Every migrated endpoint should return `job_id`.

Acceptance criteria:

* upload import can run as a job where applicable
* profiling can run as a job
* feature execution can run as a job
* visualization generation can run as a job
* job status exposes result IDs
* docs explain how to start API + worker

---

## M10E: Documentation and Compatibility Tests

Finalize worker documentation and compatibility.

Update README with:

* how to run the API
* how to run the worker
* required env variables
* how job polling works
* which endpoints now return `job_id`
* note that one worker processes jobs sequentially
* note that more workers may be added later

Add/adjust tests for:

* job schema validation
* job repository create/read/list/update
* job status routes
* worker claim behavior
* worker success behavior
* worker failure behavior
* cleaning execution job flow
* migrated heavy flow job responses

Do not add:

* frontend
* chat
* saved views
* saved visuals
* dynamic dashboards
* Celery/RQ unless already required
* Supabase Auth
* LLM calls

Acceptance criteria:

* relevant M10 tests pass
* existing affected tests are updated for job-based behavior
* README documents API + worker execution
* worker can run without requiring live external LLM services
