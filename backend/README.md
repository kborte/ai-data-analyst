# Backend — AI Data Analyst

FastAPI backend. Python 3.12+.

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/health`

## Tests

```bash
pytest
```

## Lint

```bash
ruff check app/
ruff format app/
```
