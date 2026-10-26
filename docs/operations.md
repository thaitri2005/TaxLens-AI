# Operations

Running TaxLens locally, releasing it, and operating the Azure development environment
(`taxlens-dev-rg`). Azure commands assume an authenticated Azure CLI (`az login`) and
PowerShell unless shown otherwise.

## Local development

### Prerequisites

- Python 3.12
- Docker Desktop with Docker Compose
- Node.js 22, only to run the web app outside Docker

### Start the stack

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

### Checks

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

### Build a corpus

Collect, process, and embed a small batch from the government portal:

```powershell
docker compose exec -T api python scripts/collect_sources.py --since-days 60 --limit 20
docker compose exec -T api python scripts/process_corpus.py
docker compose exec -T api python scripts/embed_corpus.py
```

Each step skips work already done, so the commands can be rerun at any time.

### Scripts

| Script | Purpose |
| --- | --- |
| `collect_sources.py` | Lists tax documents from `--source government` (default), `mof`, or `all`, and downloads new ones. `--since-days` or `--from-year` sets the window, `--limit` caps downloads, `--dry-run` only counts. See [pipeline.md](pipeline.md). |
| `process_corpus.py` | Extracts text (native or OCR) and chunks pending versions. `--rechunk-outdated` re-chunks from stored text after a chunker change; `--retry-failed` retries failed versions; `--reocr` OCRs again; `--all` reprocesses everything. |
| `embed_corpus.py` | Embeds every passage without a current embedding, 500 at a time, printing progress. |
| `evaluate_tax_retrieval.py` | Runs the labelled retrieval evaluation and stores the report ([retrieval.md](retrieval.md#evaluation)). `--dataset data/evaluation/gold_set_v1.csv` runs the [gold set](retrieval.md#gold-set). |
| `evaluate_retrieval.py` | Prints ranked results for one ad hoc `--query`. |
| `evaluate_qa.py` | Runs the cheap, no-judge Q&A evaluation. |
| `benchmark_ocr.py` | Word error rate of OCR settings against a born-digital PDF. |
| `prune_non_tax_documents.py` | Lists, or with `--apply` deletes, documents whose titles are not about tax. |
| `seed.py` | Sample documents and the initial administrator. |
| `ingest_manifest.py`, `repair_document_metadata.py` | Ingest or repair the hand-picked documents in `data/corpus/tax_documents.json`. |
| `ingest_sources.py`, `discover_sources.py` | Earlier single-page connectors, kept for ingesting one explicit official URL. `collect_sources.py` replaces them for collection. |

### Airflow and MLflow

```powershell
docker compose --profile airflow up -d airflow-postgres airflow-init airflow-scheduler airflow-webserver
docker compose --profile llmops up -d mlflow
```

The DAGs call the local API's internal job endpoints exactly as in Azure; see
[pipeline.md](pipeline.md#airflow).

### Answers

Q&A needs `HF_TOKEN` with Hugging Face inference credits, or any OpenAI-compatible
endpoint through `HF_CHAT_BASE_URL`, `HF_CHAT_MODEL`, and an empty
`HF_CHAT_ROUTING_POLICY`. Without one, search and the library work and every question
returns `PROVIDER_UNAVAILABLE`.

### API overview

All endpoints except `/health`, `/ready`, and the internal ones require the signed
identity the web proxy adds ([architecture.md](architecture.md#authentication)); use the web app,
or the OpenAPI page with a test identity, to call them.

| Endpoint | Purpose |
| --- | --- |
| `GET /search?q=…&mode=hybrid&limit=10&offset=0` | Ranked passages, a page at a time (`offset` up to 200). The Search tab also calls `GET /documents?q=…` to list documents whose number or title matches. Filters: `document_number`, `document_type`, `source_name`, `legal_status`, `issuing_agency`, `effective_from`, `effective_to`. |
| `POST /questions` | Cited answer to `{"question": "…"}`. |
| `GET /documents/overview`, `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/chunks` | Document library ([architecture.md](architecture.md#document-library)). |
| `GET /evaluation/retrieval/latest` | The latest retrieval evaluation report. |
| `/admin/*` | Account management, and `GET /admin/documents/export`: a CSV of every collected document's metadata (administrators). |
| `/internal/airflow/*` | Background jobs for Airflow, with `X-TaxLens-Internal-Token`. |

## Contributing

`main` is protected by a ruleset: changes arrive through a pull request, the **Backend
checks**, **Frontend build**, and **Terraform validation** jobs must pass, and the branch
must be up to date with `main`. Force pushes and deleting `main` are blocked. The
repository owner is on the bypass list and may push directly; run the checks below
before doing so, because a direct push skips the pull-request gate.

```powershell
git switch main; git pull                     # always start from the latest main
git switch -c fix/short-description
# ...change, then run the checks in "Local development"...
git push -u origin fix/short-description      # open the pull request from the link printed
```

Keep pull requests small and focused, and delete the branch after merging.

## Release

1. Merge to `main` and wait for **CI** to pass (backend checks, web build, Terraform
   validation).
2. Run **Publish release images** on `main`. It builds the API, web, and Airflow images
   tagged with the commit SHA.
3. Run **Plan or deploy Azure infrastructure** with that tag and `apply=true`; approve the
   `azure-deploy` environment. The API applies database migrations itself after it starts.

Before deploying, check that no Airflow run is in progress: a deploy restarts the API and
kills its jobs. Check which image is live with:

```powershell
az containerapp show -g taxlens-dev-rg -n taxlens-dev-api --query "properties.template.containers[0].image" -o tsv
```

After a deploy, sign in and open each tab once. The first request after idle wakes the API
and can take a minute; the page says so.

### GitHub Actions

| Workflow | Trigger | What it does |
| --- | --- | --- |
| **CI** (`ci.yml`) | Pull requests and pushes to `main` | Ruff, MyPy, and Pytest; a production Next.js build with test-only placeholder secrets; Terraform init, format, and validate without a backend. |
| **Publish release images** (`release-images.yml`) | Manual, `azure-release` environment | Builds the API, web, and Airflow images, tags them with the commit SHA, and prints the three image references. |
| **Plan or deploy Azure infrastructure** (`deploy.yml`) | Manual, apply job behind the `azure-deploy` environment | Takes a published image tag, writes temporary Terraform variables from GitHub secrets, and produces a reviewable plan; applies it only with `apply=true`. |

Both Azure workflows sign in with OIDC and need these secrets:

- `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
- for deploys: `TF_VAR_POSTGRES_ADMIN_PASSWORD`, `TF_VAR_HF_TOKEN`,
  `TF_VAR_AUTH_INTERNAL_TOKEN`, `TF_VAR_NEXTAUTH_SECRET`, `TF_VAR_AIRFLOW_ADMIN_PASSWORD`,
  `TF_VAR_AIRFLOW_INTERNAL_TOKEN`, and optionally `TF_VAR_POSTGRES_ALLOWED_IP` to keep the
  developer PostgreSQL firewall rule.

The OIDC principal needs `Storage Blob Data Contributor` on the Terraform state storage
account, `Contributor` and `User Access Administrator` on `taxlens-dev-rg`, and
`Key Vault Secrets Officer` on `taxlensdevkv`. Developer access is kept separately for
emergency recovery.

### Terraform

Terraform for the development environment in `taxlens-dev-rg`. What it creates is described in
[architecture.md](architecture.md#azure-deployment).

| File | Contents |
| --- | --- |
| `main.tf` | Resource group, Log Analytics, storage (Blob containers, Airflow log share), Container Registry, PostgreSQL with `vector`, Key Vault and secrets, managed identity and RBAC, API and web Container Apps |
| `airflow.tf` | Airflow metadata database, scheduler and webserver Container Apps (when `airflow_enabled`) |
| `variables.tf`, `outputs.tf`, `versions.tf` | Inputs, outputs, providers, and the remote state backend |

#### Normal use

Deployments run through GitHub Actions (**Plan or deploy Azure infrastructure**), which
supplies the image tags and secrets; see [Release](#release). Run
Terraform locally only to inspect or recover.

#### Local use

Requires Terraform 1.8+ and the Azure CLI. State is in the private `terraform-state`
container of `taxlensdevartifacts`, authenticated with Azure AD; your identity needs
`Storage Blob Data Contributor` on that account.

```powershell
az login
terraform init
terraform plan
```

Put inputs in an ignored `terraform.tfvars` (never commit it):

```hcl
subscription_id         = "<subscription id>"
postgres_admin_password = "<password>"
postgres_allowed_ip     = ""            # your public IP for laptop runs, or empty
hf_token                = "<Hugging Face token>"
auth_internal_token     = "<random secret>"
nextauth_secret         = "<random secret>"
api_image               = "taxlensdevacr.azurecr.io/taxlens-api:<commit sha>"
web_image               = "taxlensdevacr.azurecr.io/taxlens-web:<commit sha>"
airflow_enabled         = true
airflow_image           = "taxlensdevacr.azurecr.io/taxlens-airflow:<commit sha>"
airflow_admin_password  = "<password>"
airflow_internal_token  = "<random secret>"
```

Review every plan before `terraform apply`. State contains secret values, which is why it
is kept only in the private backend.

For a laptop collection run, prefer a temporary firewall rule with the Azure CLI
([below](#ministry-of-finance-from-a-laptop-in-vietnam)) over changing `postgres_allowed_ip`.

## Growing the corpus

### Government portal (from Azure)

Run the `taxlens_corpus_maintenance` DAG with `backfill_dry_run` to see how many documents
are missing, then `backfill_corpus` until none remain. Each run collects up to 300.

### Ministry of Finance (from a laptop in Vietnam)

The Ministry's site rejects connections from Azure ([design decision](architecture.md#collect-the-ministry-of-finance-database-from-a-machine-in-vietnam)).

1. Allow your public IP on the PostgreSQL server:

   ```powershell
   $ip = (Invoke-RestMethod https://api.ipify.org)
   az postgres flexible-server firewall-rule create -g taxlens-dev-rg --server-name taxlens-dev-pg --name laptop --start-ip-address $ip --end-ip-address $ip
   ```

2. In one terminal, install the cloud extras, point the settings at Azure, and run:

   ```powershell
   pip install -e ".[cloud]"
   $env:DATABASE_HOST = "taxlens-dev-pg.postgres.database.azure.com"
   $env:DATABASE_USER = "taxlensadmin"
   $env:DATABASE_PASSWORD = "<PostgreSQL admin password>"
   $env:DATABASE_SSL_MODE = "require"
   $env:OBJECT_STORAGE_BACKEND = "azure_blob"
   $env:AZURE_STORAGE_CONNECTION_STRING = (az storage account show-connection-string -g taxlens-dev-rg -n taxlensdevartifacts -o tsv)
   python scripts/collect_sources.py --source mof --from-year 1990 --dry-run
   python scripts/collect_sources.py --source mof --from-year 1990 --limit 300
   ```

   The script stops within seconds if the database or storage is unreachable, so a
   missing setting never wastes the ten-minute listing. The listing is cached for 24 hours
   (`--refresh-listing` to fetch it again).

3. Run the maintenance DAG with `process_and_embed`.
4. Remove the firewall rule:
   `az postgres flexible-server firewall-rule delete -g taxlens-dev-rg --server-name taxlens-dev-pg --name laptop --yes`.

### Stopping Airflow to save cost

The Airflow scheduler is the only always-on Container App. When no collection is needed,
stop both Airflow apps; the site keeps working, but **the daily DAG does not run** while the
scheduler is stopped, and a stopped app stays stopped until started again:

```powershell
az containerapp stop  -g taxlens-dev-rg -n taxlens-dev-airflow-scheduler
az containerapp stop  -g taxlens-dev-rg -n taxlens-dev-airflow-web
az containerapp start -g taxlens-dev-rg -n taxlens-dev-airflow-scheduler   # and -web for the UI
az containerapp show  -g taxlens-dev-rg -n taxlens-dev-airflow-scheduler --query properties.runningStatus -o tsv
```

### During long backfills

Pause the daily DAG while a long backfill runs, so its processing and embedding do not
compete for the API's memory and CPU, and unpause it afterwards.

## Airflow from the command line

`az containerapp exec` passes the command split on spaces and does not honour quotes, so
JSON configuration cannot be passed directly. Simple commands work:

```powershell
az containerapp exec -g taxlens-dev-rg -n taxlens-dev-airflow-scheduler --command "airflow dags pause tax_regulation_discovery_daily"
az containerapp exec -g taxlens-dev-rg -n taxlens-dev-airflow-scheduler --command "airflow dags unpause tax_regulation_discovery_daily"
az containerapp exec -g taxlens-dev-rg -n taxlens-dev-airflow-scheduler --command "airflow dags list-runs -d taxlens_corpus_maintenance"
```

Trigger DAGs with configuration from the UI. Azure rate-limits `exec` sessions; after a
`429 Too Many Requests`, wait the ten minutes it asks for. `exec` into the API fails with
"Could not find a replica" while the API is scaled to zero.

## Logs

| What | Where |
| --- | --- |
| A DAG task, including the job's output | Airflow UI → task → **Logs** |
| API requests and job start/finish events | `az containerapp logs show -g taxlens-dev-rg -n taxlens-dev-api --type console --tail 300` |
| The same, searchable and older | Log Analytics workspace, `ContainerAppConsoleLogs_CL` |
| Raw Airflow task log files | `airflow-logs` file share in `taxlensdevartifacts` |

API logs contain `job_started`, `job_completed`, and `job_failed` events with the job ID,
exit code, and duration, never document text, queries, or secrets.

The file share stores the colons in Airflow run IDs as the private-use character U+F022
(the SMB mapping), so `az storage file list` cannot open run folders such as
`run_id=manual__2026-10-20T02:23:38+07:00`. Use the File REST API with the character
URL-encoded as `%EF%80%A2` and `+` as `%2B`:

```bash
sas=$(az storage share generate-sas --account-name taxlensdevartifacts -n airflow-logs \
  --permissions rl --expiry "$(date -u -d '+1 hour' +%Y-%m-%dT%H:%MZ)" -o tsv \
  --account-key "$(az storage account keys list -g taxlens-dev-rg -n taxlensdevartifacts --query '[0].value' -o tsv)")
c=%EF%80%A2
run="run_id=manual__2026-10-20T02${c}23${c}38%2B07${c}00"
curl -s "https://taxlensdevartifacts.file.core.windows.net/airflow-logs/dag_id=taxlens_corpus_maintenance/$run/task_id=run_maintenance/attempt%3D1.log?$sas"
```

## Troubleshooting

| Symptom | Cause | Action |
| --- | --- | --- |
| No new documents for days | The Airflow scheduler is stopped (`runningStatus` is `Stopped`) or the daily DAG is paused | Start the scheduler ([Stopping Airflow](#stopping-airflow-to-save-cost)) and unpause the DAG. |
| Pages are slow for a minute, then fine | The API was scaled to zero | None; the web client retries while it starts. |
| "Expired identity" | An API image from before October 2026 accepted identities for only 60 s, less than a cold start | Deploy a current release. |
| A job fails with exit code -9 after about 21,600 s | Six-hour job limit | Rerun the action; finished work is kept. |
| A job fails with exit code -9 earlier | Out of memory in the 2 GiB API container | Check that no other long job was running at the same time; rerun. |
| Every answer is `PROVIDER_UNAVAILABLE` | The Hugging Face token has no inference credits (HTTP 402 in the API log as `chat_provider_error`) | Add credits or point `HF_CHAT_BASE_URL` at another OpenAI-compatible endpoint. |
| Collection logs "Government portal unavailable" | The portal timed out | A slow year is skipped after three attempts; the next run lists it again. |
| Ministry collection: `ConnectTimeout` | Run from outside Vietnam | Run it from a Vietnamese network ([design decision](architecture.md#collect-the-ministry-of-finance-database-from-a-machine-in-vietnam)). |
| Laptop run: "Cannot reach the database" | Settings not set in this terminal, or IP not allowed | Set the variables in the same window and add the firewall rule. |
| Laptop run: "Cannot use azure_blob storage" | The Azure SDK is missing | `pip install -e ".[cloud]"`. |
| A document stays `FAILED` | Extraction failed (broken file, unusable scan) | Run `retry_failed_documents` after fixing the cause; the error code is shown on the document page. |
