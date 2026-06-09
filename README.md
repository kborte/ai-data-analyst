# AI Data Analyst

A modular, human-in-the-loop AI-assisted data analysis application.

Users upload messy business datasets, step through a structured analysis workflow, and receive inspectable, explainable outputs at every stage. LLMs propose; humans decide; deterministic code executes.

---

## Features

### Upload
- Upload CSV or Excel files (multi-sheet supported)
- Upload text context documents (`.txt`, `.md`) to ground analysis in business context
- Each upload is saved as a raw artifact in storage and materialized as a `.duckdb` version file
- Multiple files can be added to an existing dataset without creating a new dataset

### Data Profiling
- Automatic column-type detection (numeric, categorical, date, ID)
- Per-column statistics: null rate, unique count, min/max/mean/median, top values
- Quality issue detection: missing values, date-stored-as-text, type mismatches
- Likely-metric, likely-ID, likely-categorical, and likely-date column classification

### Cleaning — Human-in-the-Loop
- Deterministic cleaning plan generated from profile quality issues
- Each step carries an impact estimate (rows affected, columns changed)
- High-impact steps enriched with LLM-generated rationale (one OpenAI call per plan)
- Human approves, rejects, or modifies each step before execution
- Cleaning executes deterministically; original dataset is never overwritten
- A new `DatasetVersion` is created from each approved cleaning run

### Feature Engineering — Human-in-the-Loop
- Deterministic feature suggestions: ratios, rolling windows, date extraction, aggregations
- LLM supplements with up to 4 additional feature ideas (validated against real column names)
- Human approves or rejects each suggested feature
- Approved features are executed deterministically and create a new `DatasetVersion`

### Visualization
- Deterministic chart suggestions from profile metadata (bar, line, scatter, histogram, pie)
- LLM supplements with up to 3 additional chart ideas when deterministic output is sparse
- Chart specs are validated against actual column names before being proposed
- Human reviews and approves chart suggestions before rendering

### Storage
- Two storage backends: `local` (dev) and `supabase` (production)
- Raw uploads and `.duckdb` version artifacts stored in the configured backend
- DuckDB used only as a local scratch tool during request processing — no persistent local files in Supabase mode
- Storage paths follow a predictable convention:
  ```
  raw uploads:  workspaces/{wid}/datasets/{did}/raw_uploads/{fid}_{filename}
  versions:     workspaces/{wid}/datasets/{did}/versions/v{n}_{type}.duckdb
  results:      workspaces/{wid}/datasets/{did}/results/{artifact_id}.{ext}
  ```

---

## Project Structure

```
ai-data-analyst/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app entrypoint
│   │   ├── core/
│   │   │   ├── config.py            # pydantic-settings, reads .env
│   │   │   └── logging.py
│   │   ├── api/routes/
│   │   │   ├── uploads.py           # POST /workspaces/{id}/datasets/upload
│   │   │   ├── profiles.py          # POST /datasets/{id}/versions/{id}/profile
│   │   │   ├── cleaning.py          # cleaning plan + decisions + execution
│   │   │   ├── features.py          # feature plan + decisions + execution
│   │   │   ├── visualization.py     # visualization plan + decisions + generation
│   │   │   └── health.py            # GET /health
│   │   ├── services/
│   │   │   ├── upload_service.py    # saves raw file + creates .duckdb version
│   │   │   ├── profiling_service.py # reads .duckdb, runs profiler per table
│   │   │   ├── cleaning_plan_service.py
│   │   │   ├── cleaning_execution_service.py
│   │   │   ├── feature_service.py
│   │   │   └── visualization_service.py
│   │   ├── tools/
│   │   │   ├── data/
│   │   │   │   ├── profiler.py          # column stats + quality issues
│   │   │   │   ├── duckdb_service.py    # create/read/inspect .duckdb artifacts
│   │   │   │   ├── cleaning_executor.py
│   │   │   │   ├── feature_executor.py
│   │   │   │   └── feature_planner.py
│   │   │   ├── files/
│   │   │   │   ├── storage_service.py   # StorageBackend protocol + Local/Supabase impls
│   │   │   │   ├── csv_loader.py
│   │   │   │   └── excel_loader.py
│   │   │   ├── charts/
│   │   │   │   ├── chart_planner.py
│   │   │   │   └── chart_executor.py
│   │   │   └── llm/
│   │   │       ├── provider.py          # LLMProvider protocol + OpenAI/Fake impls
│   │   │       └── prompts.py           # structured prompts for cleaning/feature/chart enrichment
│   │   ├── repositories/
│   │   │   ├── database.py          # SQLAlchemy-backed repositories
│   │   │   └── memory.py            # in-memory repositories (tests/dev)
│   │   ├── db/
│   │   │   ├── models.py            # SQLAlchemy ORM models
│   │   │   └── session.py
│   │   ├── schemas/                 # Pydantic schemas for all domain entities
│   │   └── tests/
│   │       ├── fixtures/            # simple_sales.csv, company_context.txt
│   │       └── unit/                # 299 pytest tests
│   ├── alembic/                     # DB migration scripts
│   ├── pyproject.toml
│   ├── .env.example                 # copy to .env and fill in
│   └── alembic.ini
├── frontend/
│   └── app/
│       ├── page.tsx                 # workflow overview + navigation
│       ├── cleaning-plan/page.tsx   # cleaning review UI
│       ├── metrics-plan/page.tsx    # feature engineering review UI
│       ├── charts-preview/page.tsx  # visualization review UI
│       └── components/              # CleaningReviewFlow, MetricsReviewFlow, ChartReviewFlow
├── milestones/                      # milestone specification docs
├── docker-compose.yml               # local PostgreSQL
└── README.md
```

---

## API Overview

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/workspaces/{wid}/datasets/upload` | Upload CSV/Excel, create dataset + version |
| `POST` | `/workspaces/{wid}/context-documents/upload` | Upload text context |
| `POST` | `/datasets/{did}/versions/{vid}/profile` | Profile all tables in a version |
| `GET` | `/profiles/{pid}` | Fetch a profile |
| `POST` | `/datasets/{did}/versions/{vid}/cleaning-plans` | Generate cleaning plan |
| `GET` | `/cleaning-plans/{cid}` | Fetch a cleaning plan |
| `POST` | `/cleaning-plans/{cid}/decisions/validate` | Submit human decisions |
| `POST` | `/cleaning-plans/{cid}/execute` | Execute approved cleaning steps |
| `GET` | `/cleaning-results/{rid}` | Fetch cleaning result |
| `POST` | `/datasets/{did}/versions/{vid}/feature-plans` | Generate feature plan |
| `POST` | `/feature-plans/{fid}/decisions/validate` | Submit feature decisions |
| `POST` | `/feature-plans/{fid}/execute` | Execute approved features |
| `POST` | `/datasets/{did}/versions/{vid}/visualization-plans` | Generate visualization plan |
| `POST` | `/visualization-plans/{vid}/decisions/validate` | Submit chart decisions |
| `POST` | `/visualization-plans/{vid}/generate` | Generate chart data |
| `GET` | `/datasets/{did}/versions/{vid}/views` | List saved views for a version |
| `POST` | `/datasets/{did}/versions/{vid}/views` | Save a new view |
| `GET` | `/views/{vid}` | Get saved view metadata |
| `DELETE` | `/views/{vid}` | Delete a saved view |
| `GET` | `/views/{vid}/preview` | Preview up to 100 rows |
| `GET` | `/views/{vid}/download?format=csv` | Download view artifact |
| `GET` | `/datasets/{did}/versions/{vid}/visuals` | List saved visuals for a version |
| `POST` | `/datasets/{did}/versions/{vid}/visuals` | Save a new visual |
| `GET` | `/visuals/{vid}` | Get saved visual metadata |
| `DELETE` | `/visuals/{vid}` | Delete a saved visual |
| `GET` | `/visuals/{vid}/data` | Get chart spec and data |

Interactive docs at `http://localhost:8000/docs` when the backend is running.

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `STORAGE_BACKEND` | Yes | `local` (dev) or `supabase` (production) |
| `LOCAL_STORAGE_DIR` | Local only | Root dir for local storage (default: `storage/uploads`) |
| `OPENAI_API_KEY` | Optional | If set, enables LLM enrichment of plans; blank → deterministic-only |
| `LLM_MODEL` | No | OpenAI model (default: `gpt-4o-mini`) |
| `SUPABASE_URL` | Supabase mode | `https://<project-ref>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase mode | Service role key (not the anon key) |
| `SUPABASE_STORAGE_BUCKET` | Supabase mode | Bucket name (default: `ai-data-analyst`) |
| `STORAGE_TEMP_DIR` | No | Temp dir for DuckDB scratch files (default: `/tmp/ai_data_analyst`) |

---

## Database Setup

### Option A — Local PostgreSQL

```bash
docker compose up -d db
```

Starts PostgreSQL on port 5432: user `postgres`, password `postgres`, database `ai_data_analyst`.

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_data_analyst
STORAGE_BACKEND=local
LOCAL_STORAGE_DIR=storage/uploads
```

### Option B — Supabase

1. Create a project at [supabase.com](https://supabase.com).
2. Go to **Settings → Database → Connection string** and copy the **Transaction pooler** URI (port 6543).
3. Go to **Storage**, create a private bucket named `ai-data-analyst`.
4. Set in `.env`:

```
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
STORAGE_BACKEND=supabase
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...
SUPABASE_STORAGE_BUCKET=ai-data-analyst
```

> Use the **service role key**, not the anon key — the anon key returns 403 on storage writes.

### Run Migrations

```bash
cd backend
.venv/bin/alembic upgrade head
```

---

## Running the Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# make sure DATABASE_URL is set in .env
uvicorn app.main:app --reload
# → http://localhost:8000/health
# → http://localhost:8000/docs  (interactive API explorer)
```

---

## Running the Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

The frontend connects to the backend at `http://localhost:8000` by default.

---

## Running Tests

```bash
cd backend
pytest
```

Tests use:
- `LocalStorageBackend(tmp_path)` — no Supabase credentials needed
- SQLite in-memory for DB repository tests — no PostgreSQL needed
- `FakeLLMProvider` — no OpenAI key needed

Run a specific test file:

```bash
pytest app/tests/unit/test_upload_routes.py -v
```

Run with coverage:

```bash
pytest --tb=short -q
```

---

## Lint and Format

```bash
cd backend
ruff check app/
ruff format app/
```

---

## Saved Views and Saved Visuals

### Concepts

A **SavedView** is a user-saved, reusable table-like result. Examples: revenue grouped by month and channel, a filtered high-value customers table, a joined orders-customers summary. View data is stored as a file artifact (CSV/Parquet) in the storage backend; Postgres stores only the metadata and storage path.

A **SavedVisual** is a user-saved, reusable chart result. Examples: a line chart of revenue over time, a bar chart of spend by channel. The chart spec is stored as JSONB in Postgres; larger chart data may optionally point to a storage artifact.

### SavedView vs a generated table result

Generating a table output — from a chat query, an aggregation route, or a feature result — does **not** automatically create a `SavedView`. A `SavedView` is only created by an explicit user action: calling `POST .../views` or one of the service-layer helpers. One-time table outputs can be downloaded as CSV without being saved as a view.

### SavedVisual vs VisualizationResult

A `VisualizationResult` is the raw execution output of a `VisualizationPlan`. It is a job artifact and may be temporary or plan-linked. A `SavedVisual` is the user-promoted, reusable version of a chart that appears in the dataset Visuals tab. Promoting a `VisualizationResult` to a `SavedVisual` requires an explicit user action — not every generated chart becomes a saved visual.

### Version scoping

Every `SavedView` and `SavedVisual` is scoped to the `dataset_version_id` it was created from. If a view or visual was created from an older dataset version it retains that version reference — it is never silently re-scoped to the current version. This preserves artifact lineage.

### Explicit-save helpers

Four helpers in `app/services/saved_artifacts.py` allow other services to create saved artifacts without going through the HTTP layer:

| Helper | Creates |
|---|---|
| `save_view_from_table_result` | `SavedView` from in-memory columns and rows; uploads CSV to storage |
| `save_view_from_storage_artifact` | `SavedView` pointing at an already-existing storage artifact |
| `save_visual_from_chart_spec` | `SavedVisual` from an in-memory `ChartSpec` |
| `save_visual_from_visualization_result` | `SavedVisual` from an existing `VisualizationResult` |

All four helpers require the caller to pass `workspace_id`, `dataset_id`, and `dataset_version_id` explicitly. Nothing is saved automatically.

### Storage behavior

- Saved view data is written to `workspaces/{wid}/datasets/{did}/views/{view_id}.{fmt}`.
- Saved visual chart specs are stored inline in Postgres JSONB when small.
- Postgres stores metadata and storage pointers only — no large row data is written to the database.
- Deleting a saved view or visual removes both the metadata record and the storage artifact where applicable.

### What is intentionally not in scope

- Frontend implementation (views/visuals tabs are a future frontend milestone)
- Dataset chat backend
- Dynamic dashboards or drag-and-drop layouts
- PNG server-side generation — PNG download is a client-side feature
- Supabase Auth
- LLM calls

---

## Dataset Analytics Planner (M12)

### What M12 is

M12 implements a **lightweight analytics planner** for asking data questions over a selected `DatasetVersion`. It is **not** a full chat system. There are no conversation records, no server-side chat history, and no persistent memory.

The full pipeline for a single request:

1. Route receives `question`, optional `recent_messages`, optional `prior_output_refs`, `dataset_id`, `dataset_version_id`.
2. Service builds a compact **dataset context** (tables, columns, types, row counts, profile summaries).
3. **Planner** classifies the question into a structured `AnalyticsPlan` with an intent and a validated tool spec.
4. A **deterministic tool** executes the plan against the DuckDB-backed dataset version.
5. Route returns a typed output: `text`, `table`, `visual`, or `mixed`.
6. Large table outputs are stored as file artifacts; small outputs are returned inline.
7. The user may explicitly save a useful output as a `SavedView` or `SavedVisual`.

### Lightweight multi-turn support

Follow-up questions (e.g. "now show that as a chart", "save this") are supported only through **client-provided context**:

- `recent_messages` — the client passes its own message history for the current session; each assistant message may carry `output_refs` (references to prior table/visual outputs).
- `prior_output_refs` — the client passes explicit references to outputs it wants to act on.

The backend **does not persist** these messages. They are consumed within the current request and discarded. Durable conversation storage belongs to a later milestone.

### Outputs are scoped to the selected dataset version

Every output (`TextOutput`, `TableOutput`, `VisualOutput`, `MixedOutput`) carries a `dataset_version_id` that matches the version the question was asked against. Saving an output preserves that version reference — a `SavedView` or `SavedVisual` always records which version it came from.

### Planner contract

The planner produces a structured `AnalyticsPlan`, not executable code. Supported intents:

| Intent | Description |
|---|---|
| `text_answer` | Direct explanation, summary, or interpretation |
| `table_result` | Aggregation, filter, ranking, or join |
| `visual_result` | Chart — bar, line, pie, scatter |
| `mixed_result` | Short explanation plus table and/or visual |
| `save_table_result` | Explicit save of a prior table output |
| `save_visual_result` | Explicit save of a prior visual output |
| `unsupported` | Request is outside the supported tool scope |

The planner selects from typed tool specs (`PreviewTableSpec`, `AggregateTableSpec`, `FilterTableSpec`, `SimpleJoinSpec`, `GenerateVisualSpec`). **No raw SQL is produced by the planner or LLM.** All tool specs are validated before execution.

### Deterministic tools execute validated specs

All data operations run through deterministic tools in `app/tools/analytics/query_tools.py`:

| Tool | Operation |
|---|---|
| `run_preview_table` | Preview selected columns from a table |
| `run_aggregate_table` | Group-by with metric aggregations |
| `run_filter_table` | Row filtering with validated filter specs |
| `run_simple_join` | Validated join between two known tables |
| `run_generate_visual` | Chart spec generation via existing visualization utilities |

All tools:
- validate table names against the live DuckDB file
- validate column names against the actual DataFrame
- enforce row limits
- operate in read-only mode (no dataset mutation)
- return typed outputs with `dataset_version_id` preserved

### Arbitrary raw SQL is not supported

Users cannot submit raw SQL queries. The planner produces validated structural specs; deterministic Python code (pandas operations) executes them. This prevents injection and keeps execution auditable.

### Generated outputs are not automatically saved

Asking a question never creates a `SavedView` or `SavedVisual`. Outputs are ephemeral unless the user explicitly saves them:

- `POST /analytics/table-results/save-as-view` — save a table output as a `SavedView`
- `POST /analytics/visual-results/save-as-visual` — save a visual output as a `SavedVisual`

Both routes delegate to the M11 explicit-save helpers.

### Large outputs are stored as artifacts

Table outputs exceeding `INLINE_LIMIT` (500) rows are written as CSV artifacts to the configured storage backend. The `TableOutput` schema carries `storage_path`, `storage_backend`, and `storage_format` when an artifact exists. Small outputs are returned inline in `preview_rows` with the full `row_count` available.

Storage path pattern for result artifacts:

```
workspaces/{workspace_id}/datasets/{dataset_id}/results/{artifact_id}.csv
```

### Saved views and visuals use M11 helpers

When the user saves an output, the analytics routes call the service-layer helpers from M11 (`app/services/saved_artifacts.py`):

- `save_view_from_table_result` — uploads CSV to storage, persists `SavedView` metadata
- `save_view_from_storage_artifact` — points `SavedView` at an existing artifact
- `save_visual_from_chart_spec` — persists `SavedVisual` with chart spec JSON

All helpers require explicit `workspace_id`, `dataset_id`, and `dataset_version_id` from the caller.

### API routes

| Method | Path | Description |
|---|---|---|
| `POST` | `/datasets/{dataset_id}/versions/{dataset_version_id}/analytics/ask` | Ask an analytics question; returns typed output |
| `POST` | `/analytics/table-results/save-as-view` | Explicitly save a table result as a SavedView |
| `POST` | `/analytics/visual-results/save-as-visual` | Explicitly save a visual result as a SavedVisual |

### What is intentionally not in scope for M12

- Durable conversation persistence and chat history (M13)
- Dataset activity timeline
- Full autonomous agent loops
- Dynamic dashboards
- Arbitrary raw SQL from users or LLMs
- Cleaning or feature engineering execution
- Production transaction hardening (M13)
