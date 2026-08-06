# M6 Azure deployment contract

M6 deploys the existing separated services without changing the domain or
retrieval contracts.

## Target topology

```text
Azure Container Registry
        │
        ├── TaxLens web Container App
        ├── TaxLens API Container App
        └── Airflow scheduler/webserver Container Apps

Azure Database for PostgreSQL Flexible Server + pgvector
Azure Blob Storage (raw and normalized artifacts)
Azure Key Vault / managed identity (secrets)
Log Analytics (container logs)
```

MLflow is evaluation-only for the portfolio MVP. It is not required in the
normal production request path. Airflow remains a required scheduled-ingestion
service; its metadata database must be durable and its DAG image must contain
the DAG files rather than relying on a local volume mount.

## Storage contract

The application uses `ObjectStorage`, implemented by:

- `LocalObjectStorage` for local Compose and tests;
- `AzureBlobStorage` when `OBJECT_STORAGE_BACKEND=azure_blob`.

Production configuration requires either `AZURE_STORAGE_ACCOUNT_URL` with
managed identity or `AZURE_STORAGE_CONNECTION_STRING` from Key Vault. Raw PDFs
and normalized text must not remain on the API container filesystem.

## Image contract

The API image always contains Tesseract with `eng` and `vie` language data, the
pinned `multilingual-e5-small` model, and the FastAPI application with bounded
job scripts.

Build a production dependency set without development tools:

```powershell
docker build -f apps/api/Dockerfile --build-arg PIP_EXTRAS=cloud -t taxlens-api:cloud .
```

The local Compose build keeps `PIP_EXTRAS=dev` by default.

## Required deployment jobs

Run these as explicit release steps, not in the API web process:

1. Apply Alembic migrations.
2. Deploy or update API and web revisions.
3. Start or update Airflow scheduler and webserver revisions.
4. Run `/health` and `/ready` smoke checks.
5. Verify Blob round-trip, search, Q&A, citations, and one scheduled DAG task.

## Required production settings

Production must provide non-default values for database credentials,
`HF_TOKEN`, `AIRFLOW_INTERNAL_TOKEN`, storage configuration, and web/API
service URLs. Local `.env` defaults must not be used as production secrets.
