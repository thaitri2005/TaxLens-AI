# Azure deployment

The development environment runs in resource group `taxlens-dev-rg` (East Asia), managed
by Terraform in `infra/terraform`. How the parts fit together is in
[architecture.md](architecture.md); day-to-day procedures are in
[operations.md](operations.md).

## Resources

| Resource | Name | Size and scaling |
| --- | --- | --- |
| Web Container App | `taxlens-dev-web` | 0.25 vCPU, 0–1 replicas, public HTTPS |
| API Container App | `taxlens-dev-api` | 1 vCPU / 2 GiB, 0–1 replicas, internal only |
| Airflow scheduler | `taxlens-dev-airflow-scheduler` | 0.5 vCPU / 1 GiB, 1 replica |
| Airflow webserver | `taxlens-dev-airflow-web` | 0.5 vCPU / 1 GiB, 0–1 replicas |
| PostgreSQL Flexible Server | `taxlens-dev-pg` | `B_Standard_B1ms`, 32 GB, `vector` extension; databases `taxlens` and `airflow` |
| Storage account | `taxlensdevartifacts` | Blob containers `raw-documents`, `normalized-text`, `terraform-state`; file share `airflow-logs` |
| Container Registry | `taxlensdevacr` | Basic |
| Key Vault | `taxlensdevkv` | Application secrets, read by a user-assigned managed identity |
| Log Analytics | — | Console logs of all Container Apps |

Scale to zero keeps the environment cheap; the cost is a cold start of up to a minute
for the first request after idle. Only the Airflow scheduler is always on.

## Images

All images are tagged with the commit SHA and never reused.

- **API** (`apps/api/Dockerfile`): Python 3.12, Tesseract with `vie` and `eng`, the pinned
  `multilingual-e5-small` model (offline at runtime), the application, the job scripts,
  and the evaluation datasets. Dependencies are installed from
  `requirements/api-runtime.txt` before the source is copied, so a code change does not
  reinstall PyTorch. `OMP_THREAD_LIMIT=1` keeps Tesseract from contending for the single
  vCPU.
- **Web** (`apps/web/Dockerfile`): the Next.js app, built with the API's internal
  address (`http://taxlens-dev-api`).
- **Airflow** (`airflow/Dockerfile`): Airflow 2.10 with the DAG files baked in.

Build and publish them with the **Publish release images** workflow
([ci-cd.md](ci-cd.md)), not by hand.

## Startup and migrations

The API runs as a single replica and applies pending Alembic migrations itself, in a
background thread after uvicorn starts: `/health` answers the liveness probe at once and
`/ready` returns 503 until the schema is current. A failed migration keeps the revision
unready and logs `migrations_failed`.

## Configuration

Secrets come from Key Vault through the managed identity; everything else is a plain
environment variable set by Terraform.

| Setting | Purpose |
| --- | --- |
| `DATABASE_*`, `DATABASE_SSL_MODE=require` | PostgreSQL connection |
| `OBJECT_STORAGE_BACKEND=azure_blob`, `AZURE_STORAGE_ACCOUNT_URL`, `AZURE_STORAGE_CONTAINER`, `AZURE_STORAGE_NORMALIZED_CONTAINER` | Blob Storage through the managed identity |
| `HF_TOKEN` (secret), `HF_CHAT_BASE_URL`, `HF_CHAT_MODEL`, `HF_CHAT_ROUTING_POLICY` | Answer model. Any OpenAI-compatible endpoint works; set an empty routing policy for non-Hugging Face endpoints. |
| `AUTH_INTERNAL_TOKEN` (secret), `NEXTAUTH_SECRET` (secret) | Web-to-API identity signing and Auth.js sessions |
| `AIRFLOW_INTERNAL_TOKEN` (secret) | Airflow-to-API job calls |
| `TAXLENS_DAILY_SOURCE_LIMIT`, `TAXLENS_PROCESS_BATCH_SIZE`, `TAXLENS_PROCESS_MAX_BATCHES` | Daily DAG volumes |
| `OCR_*`, `EMBEDDING_*`, `QA_*` | Processing and retrieval settings; defaults in `src/taxlens/config.py` |

The Hugging Face router returns HTTP 402 when the account has no inference credits; every
answer is then `PROVIDER_UNAVAILABLE`, and the API logs
`chat_provider_error status=402`.

Terraform variables that hold secrets (`postgres_admin_password`, `hf_token`,
`auth_internal_token`, `nextauth_secret`, `airflow_admin_password`,
`airflow_internal_token`) come from GitHub secrets in the deploy workflow, or from an
ignored `terraform.tfvars` locally. See [infra/terraform/README.md](../infra/terraform/README.md).

## Networking

The API has internal ingress only; the web app reaches it over the private Container
Apps network, and only the web app is public. PostgreSQL is public-network enabled with
Azure's `0.0.0.0` "Azure services" rule, because Container Apps egress IPs rotate, plus an
optional developer IP (`postgres_allowed_ip`) for laptop runs. This is a development
compromise.

## Before production

- Private networking (VNet integration, private endpoints for PostgreSQL and Storage);
  remove the Azure-services and developer firewall rules.
- More than one API replica, which needs a shared rate limiter (the current one is in
  memory) and moving jobs out of the API process.
- Processing in a Container Apps Job so OCR never shares CPU with requests.
- A paid inference endpoint with credits and monitoring.
