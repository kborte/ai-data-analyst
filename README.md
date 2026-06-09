# AI Data Analyst

A modular, human-in-the-loop AI-assisted data analysis application.

## Purpose

Users upload CSV/Excel datasets and text context, then walk through a structured workflow:
profile → clean → enrich → visualize → interpret. Every step produces inspectable artifacts.
LLMs suggest; humans decide; deterministic executors act.

## Repo Structure

```
ai-data-analyst/
  backend/
    app/
      main.py            # FastAPI entrypoint
      core/              # config, logging
      api/routes/        # HTTP route handlers
      schemas/           # Pydantic schemas
      services/          # Business logic orchestration
      tools/             # File, data, chart, LLM tools
        data/            # profiler, DuckDB utilities, feature/cleaning executors
        files/           # storage abstraction, loaders, filename helpers
        llm/             # LLM provider abstraction
        charts/          # chart planner and executor
      repositories/      # DB persistence (SQLAlchemy)
      db/                # ORM models + Alembic migrations
      tests/
    pyproject.toml
    .env.example         # copy to .env and fill in
    alembic.ini
  frontend/
    app/page.tsx
    package.json
  milestones/            # milestone specs
  docker-compose.yml
```

## Domain Model

| Entity | Purpose |
|---|---|
| Workspace | Top-level container |
| DataSource | Where data came from (upload, API, …) |
| UploadedFile | Physical file metadata + raw storage path |
| Dataset | Logical analysis unit (e.g. "May Revenue") |
| DatasetVersion | Immutable snapshot; cleaning/enrichment always creates a new version |
| DatasetTable | One table/sheet within a version; identified by name inside the version's `.duckdb` |
| ContextDocument | Business context from uploaded text |
| DataProfile | Statistical profile + quality issues per table |
| CleaningPlan / Decisions / Result | Human-in-the-loop cleaning workflow |
| FeaturePlan / Decisions / Result | Human-in-the-loop feature engineering |
| VisualizationPlan / Result | Chart specs generated deterministically + optionally with LLM |

---

## Storage Architecture

```
Supabase Postgres  →  metadata, plans, decisions, jobs, lineage
Supabase Storage   →  raw uploads, .duckdb version artifacts, result files
DuckDB             →  analytical execution (temp local scratch files only)
```

**Persistent files always live in storage (local or Supabase), never on the backend server's disk.**
Temp local `.duckdb` scratch files are created during a single request and deleted immediately after — they are not persisted.

Storage paths follow this convention:

```
raw uploads:
  workspaces/{workspace_id}/datasets/{dataset_id}/raw_uploads/{file_id}_{filename}

dataset versions:
  workspaces/{workspace_id}/datasets/{dataset_id}/versions/v{n}_{type}.duckdb

result artifacts:
  workspaces/{workspace_id}/datasets/{dataset_id}/results/{artifact_id}.{ext}
```

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in the required values.

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `STORAGE_BACKEND` | Yes | `local` (dev) or `supabase` (production) |
| `LOCAL_STORAGE_DIR` | Local only | Directory for local storage files (default: `storage/uploads`) |
| `OPENAI_API_KEY` | For LLM enrichment | OpenAI API key; leave blank to use deterministic-only mode |
| `LLM_MODEL` | No | OpenAI model name (default: `gpt-4o-mini`) |
| `SUPABASE_URL` | Supabase mode | `https://<project-ref>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase mode | Service role key (not the anon key) — bypasses RLS |
| `SUPABASE_STORAGE_BUCKET` | Supabase mode | Storage bucket name (default: `ai-data-analyst`) |
| `STORAGE_TEMP_DIR` | No | Temp dir for DuckDB scratch files (default: `/tmp/ai_data_analyst`) |

---

## Database Setup

### Option A — Local PostgreSQL (dev)

```bash
docker compose up -d db
```

`docker-compose.yml` starts PostgreSQL on port 5432 with user `postgres`, password `postgres`, database `ai_data_analyst`.

Set in `backend/.env`:

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_data_analyst
STORAGE_BACKEND=local
LOCAL_STORAGE_DIR=storage/uploads
```

### Option B — Supabase Postgres (production / shared dev)

1. Create a project at [supabase.com](https://supabase.com).
2. Go to **Settings → Database → Connection string** and copy the **Transaction pooler** URI (port 6543).
3. Set in `backend/.env`:

```
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
STORAGE_BACKEND=supabase
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...
SUPABASE_STORAGE_BUCKET=ai-data-analyst
```

> **Use the service role key, not the anon key.** The anon key is subject to RLS and will return 403 on storage writes.

### Run Migrations

```bash
cd backend
.venv/bin/alembic upgrade head
# or: uv run alembic upgrade head
```

### Reset Local Database

```bash
cd backend
.venv/bin/alembic downgrade base
.venv/bin/alembic upgrade head
```

---

## Supabase Storage Setup

1. In the Supabase Dashboard go to **Storage**.
2. Create a new bucket named `ai-data-analyst` (or whatever you set in `SUPABASE_STORAGE_BUCKET`).
3. Set the bucket to **private** — the backend uses the service role key and does not require public URLs.

The backend will automatically create folders inside the bucket using the path convention above. No manual folder setup is required.

---

## Local Dev Storage Mode

Set `STORAGE_BACKEND=local` and `LOCAL_STORAGE_DIR=storage/uploads` in `backend/.env`.

Files are written under `backend/storage/uploads/`. This directory is gitignored.

**Tests always use a temporary directory** injected via `LocalStorageBackend(tmp_path)` — they never write to the real `LOCAL_STORAGE_DIR` and do not need Supabase credentials.

---

## Run Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# start PostgreSQL (local or Supabase connection string in .env)
uvicorn app.main:app --reload
# → http://localhost:8000/health
```

---

## Run Tests

```bash
cd backend
pytest
# Tests use LocalStorageBackend(tmp_path) — no Supabase credentials needed.
# DB repo tests use SQLite in-memory — no PostgreSQL needed.
```

---

## Lint and Format

```bash
cd backend
ruff check app/
ruff format app/
```

---

## Run Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```
