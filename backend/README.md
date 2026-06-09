# AI Data Analyst — Backend

FastAPI backend for agentic dataset analysis. Python 3.12+, PostgreSQL, DuckDB, Supabase Storage.

---

## Features

- Upload CSV and Excel datasets
- Automatic data profiling (column types, nulls, metrics)
- Human-in-the-loop cleaning plan generation and execution
- Feature engineering (calculated columns, derived metrics)
- Visualization plan generation and chart spec rendering
- Background job system — heavy processing runs in a worker process
- DuckDB-backed dataset version artifacts (one `.duckdb` file per materialized version)
- Supabase Storage for persistent file artifacts (or local disk in dev mode)

---

## Project Structure

```
backend/
├── app/
│   ├── api/routes/          # Thin FastAPI routes
│   ├── core/                # Config and logging
│   ├── db/                  # SQLAlchemy models and session
│   ├── repositories/        # Database-backed and in-memory repos
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # Business logic orchestration
│   ├── tools/               # Low-level tools (DuckDB, profiling, storage, LLM)
│   ├── worker/              # Background job worker
│   └── tests/
├── alembic/                 # Database migrations
├── pyproject.toml
└── README.md
```

---

## Setup

```bash
cd backend
uv sync
```

Or with pip:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Running the API

```bash
uv run uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/health`

The API is available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## Running the Worker

The worker claims and processes one queued job at a time. Run it in a separate terminal:

```bash
uv run python -m app.worker
```

The worker polls for queued jobs every 5 seconds when the queue is empty. It processes jobs sequentially — one job at a time per worker process. To increase throughput, run multiple worker processes (each uses `SELECT ... FOR UPDATE SKIP LOCKED` to safely claim jobs without conflicts).

**The API and worker must share the same database and storage configuration** (same `DATABASE_URL`, same `STORAGE_BACKEND` settings).

---

## Running Tests

```bash
uv run pytest
```

Specific test file:

```bash
uv run pytest app/tests/unit/test_jobs_api.py -v
```

---

## Linting

```bash
uv run ruff check app/
uv run ruff format app/
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/ai_data_analyst` | PostgreSQL connection URL. Use Supabase Transaction Pooler URL in production. |
| `STORAGE_BACKEND` | `local` | `local` for local disk, `supabase` for Supabase Storage. |
| `LOCAL_STORAGE_DIR` | `storage/uploads` | Root directory for local file storage (only used when `STORAGE_BACKEND=local`). |
| `SUPABASE_URL` | *(empty)* | Your Supabase project URL (required when `STORAGE_BACKEND=supabase`). |
| `SUPABASE_SERVICE_ROLE_KEY` | *(empty)* | Supabase service role key — **not** the anon/publishable key (required when `STORAGE_BACKEND=supabase`). |
| `SUPABASE_STORAGE_BUCKET` | `ai-data-analyst` | Supabase Storage bucket name. |
| `OPENAI_API_KEY` | *(empty)* | OpenAI API key. If empty, a fake LLM provider is used (returns empty suggestions). |
| `LLM_MODEL` | `gpt-4o-mini` | OpenAI model name for plan generation. |
| `STORAGE_TEMP_DIR` | `/tmp/ai_data_analyst` | Directory for temporary DuckDB scratch files. Cleaned up after each job. |

### Example `.env` (local dev)

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/ai_data_analyst
STORAGE_BACKEND=local
LOCAL_STORAGE_DIR=storage/uploads
OPENAI_API_KEY=sk-...
```

### Example `.env` (Supabase)

```env
DATABASE_URL=postgresql://postgres.your-ref:password@aws-0-region.pooler.supabase.com:6543/postgres
STORAGE_BACKEND=supabase
SUPABASE_URL=https://your-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...
SUPABASE_STORAGE_BUCKET=ai-data-analyst
OPENAI_API_KEY=sk-...
```

---

## Database Setup

### Local PostgreSQL

```bash
createdb ai_data_analyst
uv run alembic upgrade head
```

### Supabase Postgres

1. Create a Supabase project.
2. In **Settings → Database**, copy the **Transaction pooler** connection string (port 6543).
3. Set `DATABASE_URL` to the pooler URL.
4. Run migrations:

```bash
uv run alembic upgrade head
```

---

## Supabase Storage Setup

1. In your Supabase project, go to **Storage**.
2. Create a bucket named `ai-data-analyst` (or whatever you set `SUPABASE_STORAGE_BUCKET` to).
3. Set the bucket to **private** (the backend uses the service role key to read/write).
4. Set `STORAGE_BACKEND=supabase` and provide `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in your `.env`.

---

## Storage Architecture

- **Supabase Postgres** stores metadata: datasets, versions, profiles, cleaning plans, jobs, and all other structured records.
- **Supabase Storage** (or local disk in dev) stores binary file artifacts:
  - Raw uploads: `workspaces/{workspace_id}/datasets/{dataset_id}/raw_uploads/{file_id}_{filename}`
  - DuckDB version artifacts: `workspaces/{workspace_id}/datasets/{dataset_id}/versions/v{n}_{type}.duckdb`
  - Result artifacts: `workspaces/{workspace_id}/datasets/{dataset_id}/results/{artifact_id}.{ext}`
- **DuckDB** is used as a local scratch file during job processing only. Scratch files live under `STORAGE_TEMP_DIR` and are deleted after each job succeeds or fails.
- Each materialized `DatasetVersion` points to one `.duckdb` artifact. Version files are immutable.

---

## Background Job System

Heavy processing does not run inside API request handlers. Instead:

1. The API creates a **queued job** and returns `job_id` immediately.
2. The **worker** picks up the job, executes it, and marks it completed or failed.
3. Clients poll `GET /jobs/{job_id}` to check status and retrieve result IDs.

### Endpoints that return `job_id`

| Endpoint | Job type | Result fields set on completion |
|---|---|---|
| `POST /workspaces/{workspace_id}/datasets/upload` | `upload_import` | `output_dataset_version_id` |
| `POST /datasets/{dataset_id}/versions/{version_id}/profile` | `profile_dataset` | `result_id` (profile ID) |
| `POST /cleaning-plans/{cleaning_plan_id}/execute` | `execute_cleaning` | `result_id` (cleaning result), `output_dataset_version_id` |
| `POST /feature-plans/{feature_plan_id}/execute` | `execute_features` | `result_id` (feature result), `output_dataset_version_id` |
| `POST /visualization-plans/{visualization_plan_id}/generate` | `generate_visualizations` | `result_id` (visualization result) |

### Polling pattern

```
POST /workspaces/.../datasets/upload  →  { "job_id": "...", "status": "queued" }

GET /jobs/{job_id}  →  { "status": "running", ... }
GET /jobs/{job_id}  →  { "status": "completed", "output_dataset_version_id": "..." }
```

Poll `GET /jobs/{job_id}` until `status` is `"completed"` or `"failed"`. On completion, use the result fields to fetch the output:

- `output_dataset_version_id` → `GET /datasets/{dataset_id}/versions` or use directly
- `result_id` with `result_type="data_profile"` → `GET /profiles/{result_id}`
- `result_id` with `result_type="cleaning_result"` → `GET /cleaning-results/{result_id}`

### Job statuses

| Status | Meaning |
|---|---|
| `queued` | Waiting to be claimed by a worker |
| `running` | Currently being processed |
| `completed` | Finished successfully; result fields are populated |
| `failed` | Error occurred; `error_message` contains the traceback |
| `cancelled` | Cancelled via `POST /jobs/{job_id}/cancel` |

### Worker notes

- One worker processes jobs **sequentially** (one at a time).
- Multiple workers can run in parallel — job claiming uses `SELECT ... FOR UPDATE SKIP LOCKED` to prevent double-claiming.
- If the worker crashes mid-job, the job remains in `running` state. Restart the worker to resume processing new jobs. (Dead job detection is not implemented in M10.)

---

## API Reference

### Health

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |

### Uploads

| Method | Path | Returns | Description |
|---|---|---|---|
| POST | `/workspaces/{workspace_id}/datasets/upload` | Job | Queue a dataset import job |
| POST | `/workspaces/{workspace_id}/context-documents/upload` | ContextDocumentUploadResponse | Upload a context document (synchronous) |

### Profiling

| Method | Path | Returns | Description |
|---|---|---|---|
| POST | `/datasets/{dataset_id}/versions/{version_id}/profile` | Job | Queue a profiling job |
| GET | `/profiles/{profile_id}` | DataProfile | Get a saved profile |

### Cleaning

| Method | Path | Returns | Description |
|---|---|---|---|
| POST | `/datasets/{dataset_id}/versions/{version_id}/cleaning-plans` | CleaningPlan | Generate a cleaning plan |
| GET | `/cleaning-plans/{cleaning_plan_id}` | CleaningPlan | Get a cleaning plan |
| POST | `/cleaning-plans/{cleaning_plan_id}/decisions/validate` | ValidateDecisionsResponse | Validate decisions |
| POST | `/cleaning-plans/{cleaning_plan_id}/execute` | Job | Queue a cleaning execution job |
| GET | `/cleaning-results/{cleaning_result_id}` | CleaningResult | Get a cleaning result |

### Feature Engineering

| Method | Path | Returns | Description |
|---|---|---|---|
| POST | `/datasets/{dataset_id}/versions/{version_id}/feature-plans` | FeaturePlan | Generate a feature plan |
| POST | `/feature-plans/{feature_plan_id}/decisions/validate` | ValidateFeatureDecisionsResponse | Validate decisions |
| POST | `/feature-plans/{feature_plan_id}/execute` | Job | Queue a feature execution job |

### Visualization

| Method | Path | Returns | Description |
|---|---|---|---|
| POST | `/datasets/{dataset_id}/versions/{version_id}/visualization-plans` | VisualizationPlan | Generate a visualization plan |
| POST | `/visualization-plans/{visualization_plan_id}/decisions/validate` | ValidateVisualizationDecisionsResponse | Validate decisions |
| POST | `/visualization-plans/{visualization_plan_id}/generate` | Job | Queue a visualization generation job |

### Jobs

| Method | Path | Returns | Description |
|---|---|---|---|
| GET | `/jobs/{job_id}` | Job | Get job status and result fields |
| GET | `/datasets/{dataset_id}/jobs` | list[Job] | List all jobs for a dataset |
| POST | `/jobs/{job_id}/cancel` | Job | Cancel a queued or running job |
