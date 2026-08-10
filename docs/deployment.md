# Azure deployment and operations

The Azure development deployment runs the existing separated services without
changing the domain or retrieval contracts. The rollout was deliberately
phased: foundation, database, secrets, Container Apps, Airflow, and protected
CI/CD were validated independently before image promotion.

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
pinned `multilingual-e5-small` model, the FastAPI application with bounded job
scripts, and the versioned evaluation datasets under `data/evaluation`. The
last item is required because Airflow invokes retrieval evaluation inside the
API image rather than mounting the repository at runtime.

The API Dockerfile installs the cached runtime dependency manifest from
`requirements/api-runtime.txt` before copying application source. This keeps
source edits from reinstalling PyTorch, Azure SDKs, or the embedding stack.
Build the production image with:

```powershell
docker build -f apps/api/Dockerfile -t taxlens-api:cloud .
```

The local Compose build keeps `PIP_EXTRAS=dev` by default.

## Image preparation and release

Container Apps pulls immutable image tags from the Basic ACR. Use the protected
GitHub Actions release workflow rather than manually building production
images:

1. Run `release-images.yml` on `main`.
2. Copy the commit-SHA image tag from the workflow summary.
3. Run `deploy.yml` with `apply=false` and review the plan.
4. Run it again with `apply=true` only after approval.

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
5. Verify the separately deployed Airflow scheduler and webserver.

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
Development revisions use immutable commit-SHA tags. Do not reuse a tag for
different image contents; publish a new tag for every release.

## M7 Airflow deployment

Airflow is a separately scaled deployment. It uses a dedicated
`airflow` database on the existing PostgreSQL Flexible Server, a scheduler
Container App with one replica, and a webserver Container App that can scale to
zero. The scheduler is the component that must remain running for daily runs;
the webserver can be started only when the UI is needed. The DAG image contains
the DAG files, so cloud deployment does not depend on a local volume mount.

Before enabling it, add these ignored Terraform variables to
`infra/terraform/terraform.tfvars`:

```hcl
airflow_enabled              = true
airflow_web_external_enabled = true
airflow_admin_password       = "<strong-local-only-password>"
airflow_internal_token       = "<strong-random-local-only-token>"
airflow_image                = "taxlensdevacr.azurecr.io/taxlens-airflow:<immutable-tag>"
```

The API receives the same internal token through Key Vault, while the DAG
receives it through a separate secret reference. Airflow never receives the HF
token and does not access PostgreSQL application tables directly; it calls the
allowlisted internal API job endpoints in sequence. `airflow_enabled` remains
false by default in the Terraform module, but it is explicitly enabled in the
current development environment. The deployed DAG is paused by default; run
it manually from the Airflow UI only after reviewing the smoke-run plan.

## Cloud corpus bootstrap

Use the API image as a one-off worker for migrations, ingestion, processing, and
embedding. For long OCR jobs, run the worker locally with Azure PostgreSQL and
Blob credentials rather than holding an ACA exec websocket open. The workflow
is idempotent and stores all durable output in Azure.

After the first official import, run `scripts/repair_document_metadata.py`
against the curated manifest so document titles, issuing agencies, issue dates,
and official portal links are not lost when a source requires a direct PDF URL.

The scheduled processing task uses bounded batches (`TAXLENS_PROCESS_BATCH_SIZE`
and `TAXLENS_PROCESS_MAX_BATCHES`) because standard Container Apps HTTP ingress
requests are limited to 240 seconds. If OCR backlog grows beyond one scheduled
batch budget, increase the number of batches or move processing to a dedicated
Container Apps Job/worker rather than increasing the synchronous request size.
The Azure Terraform configuration pins the scheduler batch size to `1`; only
increase it after measuring the slowest document-processing request safely
below that limit.

Failed document versions are excluded from later scheduled batches by default.
This prevents an image-only or persistently malformed PDF from being retried on
every daily run. Use the internal processing endpoint with `retry_failed=true`
after correcting the underlying OCR or document issue.

## Required production settings

Production must provide non-default values for database credentials,
`HF_TOKEN`, `DATABASE_SSL_MODE=require`, `AIRFLOW_INTERNAL_TOKEN`, storage
configuration, and web/API service URLs. Container Apps should inject the
Key Vault secrets through the managed identity; local `.env` defaults must not
be used as production secrets.
