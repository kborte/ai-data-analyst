# AI Data Analyst

A modular, human-in-the-loop AI-assisted data analysis application.

## Purpose

Users upload CSV/Excel datasets and text context, then walk through a structured workflow:
profile → clean → enrich → visualize → interpret. Every step produces inspectable artifacts.
LLMs suggest; humans decide; deterministic executors act.

## Milestone 1 Scope

- Repository skeleton
- FastAPI backend with `/health` endpoint
- Core Pydantic schemas for all domain entities
- Minimal Next.js frontend placeholder
- pytest + ruff setup
- Health and schema construction tests

Not implemented yet: file upload, data processing, LLM calls, database, charts, auth.

## Domain Model Summary

| Entity | Purpose |
|---|---|
| Workspace | Top-level container for users, datasets, runs |
| DataSource | Where data came from (uploaded file, API, etc.) |
| UploadedFile | Physical file metadata |
| Dataset | Logical analytical unit (e.g. "May Revenue") |
| DatasetVersion | Immutable snapshot; cleaning/enrichment creates new versions |
| DatasetTable | One table/sheet within a version |
| ContextDocument | Business context from uploaded text |
| DataProfile | Statistical profile + quality issues |
| CleaningPlan | AI-proposed cleaning steps (JSON) |
| CleaningDecisions | Per-step human decisions |
| CleaningResult | Execution log + output version reference |
| FeaturePlan | AI-proposed derived metrics |
| VisualizationSpec | Chart spec (not rendered yet) |
| InsightReport | Structured insight report with caveats |
| AnalysisRun | Reproducibility record linking all artifacts |

## Repo Structure

```
ai-data-analyst/
  backend/
    app/
      main.py          # FastAPI entrypoint
      core/            # config, errors, logging
      api/routes/      # HTTP route handlers
      schemas/         # Pydantic schemas
      services/        # Business logic (future)
      tools/           # File, data, chart, LLM tools
      repositories/    # Persistence abstractions (future)
      tests/unit/      # pytest tests
    pyproject.toml
  frontend/
    app/page.tsx       # Placeholder UI
    package.json
  docker-compose.yml
```

## Run Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
# → http://localhost:8000/health
```

## Run Tests

```bash
cd backend
pytest
```

## Run Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```
