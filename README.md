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
