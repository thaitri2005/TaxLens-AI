# Local Development

## Prerequisites

- Python 3.12
- Docker Desktop with Docker Compose

## Start the application

1. Copy `.env.example` to `.env`.
2. Run `docker compose up --build`.
3. Run `docker compose exec api alembic upgrade head`.
4. Open `http://localhost:8000/health`.

## Run quality checks locally

Install the project with `python -m pip install -e ".[dev]"`, then run:

```powershell
$env:PYTHONPATH = "src"
pytest
ruff check .
mypy src
```

The initial Compose profile runs PostgreSQL/pgvector and the API only. Workers, Airflow, MLflow, and monitoring are added in later phases.

