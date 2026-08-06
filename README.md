# TaxLens AI

TaxLens is a Vietnamese tax-regulatory intelligence workspace. It discovers official documents, extracts and indexes their contents, supports hybrid keyword/semantic retrieval, and returns evidence-grounded answers with links to the official source.

## Current architecture

```text
Next.js web app
        │
        ▼
FastAPI API ─── PostgreSQL + pgvector
   │       │
   │       ├── native PDF extraction → local Tesseract OCR fallback
   │       ├── baked multilingual-e5-small embeddings
   │       └── Hugging Face routed chat inference
   │
Apache Airflow → authenticated API jobs
                 discovery → processing → embedding → evaluation
```

The API and web app are separate services. Airflow is a required scheduled-ingestion component. LangGraph controls the Q&A workflow and LangChain is used only at the provider/prompt boundary. MLflow and deterministic RAGAS-style evaluation are available for evaluation runs, but are disabled during normal user traffic.

## Run locally

Prerequisites: Python 3.12 and Docker Desktop with Compose.

```powershell
Copy-Item .env.example .env
docker compose up -d
```

Airflow and MLflow are optional local profiles. Start them only when needed:

```powershell
docker compose --profile airflow --profile llmops up -d
docker compose --profile airflow --profile llmops down
```

Open:

| Service | URL |
| --- | --- |
| Web app | `http://localhost:3000` |
| API | `http://localhost:8000` |
| API docs | `http://localhost:8000/docs` |
| Airflow | `http://localhost:8080` |
| MLflow | `http://localhost:5000` |

The Airflow user is created from `AIRFLOW_ADMIN_USERNAME` and `AIRFLOW_ADMIN_PASSWORD`. If the Airflow metadata volume already exists, changing `.env` does not change the stored password; reset it with:

```powershell
docker compose --profile airflow exec -T airflow-scheduler airflow users reset-password --username admin --password <new-password>
```

Run the daily DAG from Airflow by unpausing `tax_regulation_discovery_daily` and triggering it manually. It executes discovery, processing/OCR, embedding, and retrieval evaluation in order.

## Development checks

```powershell
$env:PYTHONPATH = "src"
python -m pytest
python -m ruff check src tests scripts
python -m mypy src
```

For optional evaluation dependencies:

```powershell
python -m pip install -e ".[dev,llmops]"
```

Run semantic evaluation inside the API container because the embedding model is baked into that image:

```powershell
docker compose exec -T -e MLFLOW_ENABLED=true -e MLFLOW_TRACKING_URI=http://mlflow:5000 api python scripts/evaluate_qa.py
```

Host-side `--keyword-only` mode is only a smoke test and is not comparable to production semantic-hybrid retrieval.

## Cost-conscious design decisions

- `intfloat/multilingual-e5-small` is packaged into the API image and runs on CPU; embeddings are stored in PostgreSQL/pgvector.
- Native PDF extraction runs first. Vietnamese/English Tesseract OCR is used only when native extraction is unusable. No managed OCR service is required.
- Chat inference uses configurable Hugging Face Inference Providers and the `:cheapest` routing policy by default. The model and provider remain replaceable through environment settings.
- MLflow and evaluation services are opt-in; they do not add normal request costs.

## Milestones

- M0–M5: local ingestion, OCR, hybrid retrieval, citations, API, frontend, evaluation, and hardening complete.
- M5.5: LangGraph, LangChain adapter, Airflow scheduling, MLflow tracking, and semantic QA evaluation complete.
- M6: Azure foundation, PostgreSQL/pgvector, Key Vault, managed identity, RBAC, private API/public web Container Apps, cloud migrations, official-document OCR, embeddings, hybrid search, and grounded Q&A are complete.

## Azure deployment

The current cloud slice is available at:

```text
https://taxlens-dev-web--phase4webfix6.wonderfulfield-8256aab7.eastasia.azurecontainerapps.io
```

It contains two official documents, OCR-processed chunks, pgvector
embeddings, hybrid search, and cited Q&A. See `docs/deployment.md` for the
deployment contract and cloud bootstrap workflow.

Known development limitations: PostgreSQL currently uses the Azure-services
firewall sentinel, the government catalog can require a curated manifest, and
Airflow is not deployed to Azure yet.

See `IMPLEMENTATION_PLAN.md`, `projectstructure.txt`, and `docs/` for the authoritative implementation blueprint and local operating instructions.
