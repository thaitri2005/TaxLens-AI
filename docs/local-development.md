# Local development

## Prerequisites

- Python 3.12
- Docker Desktop with Docker Compose
- Node.js 20, only to run the web app outside Docker

## Start the stack

```powershell
Copy-Item .env.example .env       # set AUTH_INITIAL_ADMIN_PASSWORD; HF_TOKEN for answers
docker compose up -d postgres api web
docker compose exec -T api alembic upgrade head
docker compose exec -T api python scripts/seed.py
```

`seed.py` loads the sample documents in `data/seed` and creates the administrator from
`AUTH_INITIAL_ADMIN_*`. It is safe to run again.

| Service | URL |
| --- | --- |
| Web app | <http://localhost:3000> |
| API and its OpenAPI docs | <http://localhost:8000/docs> |
| Airflow (profile `airflow`) | <http://localhost:8080> |
| MLflow (profile `llmops`) | <http://localhost:5000> |

Locally, documents and extracted text are stored under `data/local`
(`OBJECT_STORAGE_BACKEND=local`). The API container includes Tesseract and the embedding
model; a host Python environment usually has neither, which is why the commands below run
inside the container.

## Checks

The checks CI runs:

```powershell
python -m pip install -e ".[dev]"
python -m ruff check src tests scripts
python -m mypy src
python -m pytest
cd apps/web; npm ci; npm run build
```

CI type-checks against the newest SQLAlchemy 2.x (2.1 at the time of writing), whose
`Select` typing differs from 2.0. Type annotations on SQLAlchemy statements that must
satisfy both are written as `Select[Any]`.

## Build a corpus

Collect, process, and embed a small batch from the government portal:

```powershell
docker compose exec -T api python scripts/collect_sources.py --since-days 60 --limit 20
docker compose exec -T api python scripts/process_corpus.py
docker compose exec -T api python scripts/embed_corpus.py
```

Each step skips work already done, so the commands can be rerun at any time.

## Scripts

| Script | Purpose |
| --- | --- |
| `collect_sources.py` | Lists tax documents from `--source government` (default), `mof`, or `all`, and downloads new ones. `--since-days` or `--from-year` sets the window, `--limit` caps downloads, `--dry-run` only counts. See [sources.md](sources.md). |
| `process_corpus.py` | Extracts text (native or OCR) and chunks pending versions. `--rechunk-outdated` re-chunks from stored text after a chunker change; `--retry-failed` retries failed versions; `--reocr` OCRs again; `--all` reprocesses everything. |
| `embed_corpus.py` | Embeds every passage without a current embedding, 500 at a time, printing progress. |
| `evaluate_tax_retrieval.py` | Runs the labelled retrieval evaluation and stores the report ([evaluation.md](evaluation.md)). |
| `evaluate_retrieval.py` | Prints ranked results for one ad hoc `--query`. |
| `evaluate_qa.py` | Runs the cheap, no-judge Q&A evaluation. |
| `benchmark_ocr.py` | Word error rate of OCR settings against a born-digital PDF. |
| `prune_non_tax_documents.py` | Lists, or with `--apply` deletes, documents whose titles are not about tax. |
| `seed.py` | Sample documents and the initial administrator. |
| `ingest_manifest.py`, `repair_document_metadata.py` | Ingest or repair the hand-picked documents in `data/corpus/tax_documents.json`. |
| `ingest_sources.py`, `discover_sources.py` | Earlier single-page connectors, kept for ingesting one explicit official URL. `collect_sources.py` replaces them for collection. |

## Airflow and MLflow

```powershell
docker compose --profile airflow up -d airflow-postgres airflow-init airflow-scheduler airflow-webserver
docker compose --profile llmops up -d mlflow
```

The DAGs call the local API's internal job endpoints exactly as in Azure; see
[airflow.md](airflow.md).

## Answers

Q&A needs `HF_TOKEN` with Hugging Face inference credits, or any OpenAI-compatible
endpoint through `HF_CHAT_BASE_URL`, `HF_CHAT_MODEL`, and an empty
`HF_CHAT_ROUTING_POLICY`. Without one, search and the library work and every question
returns `PROVIDER_UNAVAILABLE`.

## API overview

All endpoints except `/health`, `/ready`, and the internal ones require the signed
identity the web proxy adds ([authentication.md](authentication.md)); use the web app,
or the OpenAPI page with a test identity, to call them.

| Endpoint | Purpose |
| --- | --- |
| `GET /search?q=…&mode=hybrid` | Ranked passages. Filters: `document_number`, `document_type`, `source_name`, `legal_status`, `issuing_agency`, `effective_from`, `effective_to`. |
| `POST /questions` | Cited answer to `{"question": "…"}`. |
| `GET /documents/overview`, `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/chunks` | Document library ([architecture.md](architecture.md#document-library)). |
| `GET /evaluation/retrieval/latest` | The latest retrieval evaluation report. |
| `/admin/*` | Account management (administrators). |
| `/internal/airflow/*` | Background jobs for Airflow, with `X-TaxLens-Internal-Token`. |
