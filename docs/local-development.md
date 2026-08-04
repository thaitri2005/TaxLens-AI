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

## Seed, process, and search the sample corpus

```powershell
docker compose exec -T api alembic upgrade head
docker compose exec -T api python scripts/seed.py
docker compose exec -T api python scripts/process_corpus.py
docker compose exec -T api python scripts/embed_corpus.py
Invoke-RestMethod 'http://localhost:8000/search?q=invoice&legal_status=EFFECTIVE' |
  ConvertTo-Json -Depth 5
```

The search endpoint supports `document_number`, `document_type`, `legal_status`,
`issuing_agency`, `effective_from`, `effective_to`, and `limit` filters.

# Hugging Face inference

For the intelligence-workflow milestone, set `HF_TOKEN=hf_...` in your local `.env` file. Do not commit it or place it in `.env.example`. `HF_CHAT_MODEL` and `HF_CHAT_ROUTING_POLICY` select the model and routed provider policy independently, so changing either never requires a code change.

The next cited-Q&A endpoint will call the chat provider only when query planning and evidence-sufficiency checks pass. Queries with no evidence, conflicting document statuses, or missing structural locators return an evidence-only/unsupported response instead.
