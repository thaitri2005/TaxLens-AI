# M6 Azure deployment contract

M6 deploys the existing separated services without changing the domain or
retrieval contracts. The rollout is deliberately phased: the foundation,
database, and secret infrastructure are provisioned first; Container Apps is
the next phase; Airflow is evaluated only after the core API and web services
are operational in Azure.

## Target topology

```text
Azure Container Registry
        │
        ├── TaxLens web Container App
        ├── TaxLens API Container App
        └── Airflow scheduler/webserver deployment (later phase)

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

Production configuration requires `AZURE_STORAGE_ACCOUNT_URL` with managed
identity. The raw and normalized prefixes map to the Terraform-created
`raw-documents` and `normalized-text` containers. Raw PDFs and normalized text
must not remain on the API container filesystem.

The development PostgreSQL server uses Azure's `0.0.0.0` firewall sentinel so
Azure-hosted Container Apps can reach it without creating one firewall rule per
rotating ACA egress IP. This is a development compromise; production should
use private networking or a controlled network boundary.

## Image contract

The API image always contains Tesseract with `eng` and `vie` language data, the
pinned `multilingual-e5-small` model, and the FastAPI application with bounded
job scripts.

The API Dockerfile installs the cached runtime dependency manifest from
`requirements/api-runtime.txt` before copying application source. This keeps
source edits from reinstalling PyTorch, Azure SDKs, or the embedding stack.
Build the production image with:

```powershell
docker build -f apps/api/Dockerfile -t taxlens-api:cloud .
```

The local Compose build keeps `PIP_EXTRAS=dev` by default.

## Phase 4 image preparation

Container Apps pulls image tags from the Basic ACR. The current development
rollout uses the `phase4` tag plus Terraform revision suffixes; production
should switch to immutable Git SHA tags. Build and push both images before
applying the Terraform plan:

```powershell
az acr login --name taxlensdevacr
docker build -f apps/api/Dockerfile -t taxlensdevacr.azurecr.io/taxlens-api:phase4 .
docker push taxlensdevacr.azurecr.io/taxlens-api:phase4
docker build -f apps/web/Dockerfile --build-arg API_ORIGIN=http://taxlens-dev-api -t taxlensdevacr.azurecr.io/taxlens-web:phase4 .
docker push taxlensdevacr.azurecr.io/taxlens-web:phase4
```

The web image keeps `http://api:8000` as its local default and uses the
Container Apps internal API name on ingress port 80 in the cloud image. The
API app is internal-only, so insecure HTTP is limited to the private
Container Apps environment; public traffic still reaches the web app over
HTTPS.

## Required deployment jobs

Run these as explicit release steps, not in the API web process:

1. Apply Alembic migrations.
2. Deploy or update API and web revisions.
3. Run `/health` and `/ready` smoke checks.
4. Verify Blob round-trip, search, and Q&A citations.
5. Add and verify the scheduled ingestion deployment in the later Airflow phase.

## M6.4 operational hardening

The core cloud slice remains intentionally low-cost: both Container Apps use
scale-to-zero with a maximum of one replica, while PostgreSQL and Blob Storage
hold durable state. Container Apps send application logs to the shared Log
Analytics workspace. API request and Airflow job logs include request/job IDs,
status, duration, and failure events without logging passwords, tokens, query
contents, or document text.

For each release, verify:

```powershell
$web = "https://taxlens-dev-web.wonderfulfield-8256aab7.eastasia.azurecontainerapps.io"
Invoke-WebRequest "$web/health" -UseBasicParsing
Invoke-WebRequest "$web/login" -UseBasicParsing
Invoke-WebRequest "$web/api/auth/session" -UseBasicParsing
```

Then authenticate through the web UI and verify one search, one question, one
document detail view, and one administrator action. Use the Container Apps log
stream or Log Analytics to confirm `request_completed`, `job_started`, and
`job_completed` events when an internal job is run.

The current PostgreSQL firewall allows Azure services and an optional local
developer IP. This is acceptable for the student development environment but
is not the final production network boundary. Private networking is deferred
until a dedicated VNet/private endpoint budget is approved; removing the local
rule and the Azure-services sentinel is a required production checklist item.

Use immutable image tags (for example, a Git SHA) for production releases.
The current `m63-auth` image tags are development release identifiers and must
not be reused for unrelated builds.

## Cloud corpus bootstrap

Use the API image as a one-off worker for migrations, ingestion, processing, and
embedding. For long OCR jobs, run the worker locally with Azure PostgreSQL and
Blob credentials rather than holding an ACA exec websocket open. The workflow
is idempotent and stores all durable output in Azure.

After the first official import, run `scripts/repair_document_metadata.py`
against the curated manifest so document titles, issuing agencies, issue dates,
and official portal links are not lost when a source requires a direct PDF URL.

## Required production settings

Production must provide non-default values for database credentials,
`HF_TOKEN`, `DATABASE_SSL_MODE=require`, `AIRFLOW_INTERNAL_TOKEN`, storage
configuration, and web/API service URLs. Container Apps should inject the
Key Vault secrets through the managed identity; local `.env` defaults must not
be used as production secrets.
