# Operations

Running TaxLens locally, releasing it, and operating Azure (`taxlens-dev-rg`). Before any slow or paid run,
read [what has been tried](retrieval-experiments.md).

## Local development

Needs Python 3.12 and Docker Desktop; Node.js 22 only to run the web app outside Docker.

```powershell
Copy-Item .env.example .env       # set AUTH_INITIAL_ADMIN_PASSWORD; HF_TOKEN for answers
docker compose up -d postgres api web
docker compose exec -T api alembic upgrade head
docker compose exec -T api python scripts/seed.py
```

Web <http://localhost:3000>, API <http://localhost:8000/docs>. Profiles: `airflow` (port 8080), `llmops`
(MLflow, port 5000). Locally, files live under `data/local`. The API container has Tesseract and the
embedding model, which a host environment usually lacks. A small corpus:

```powershell
docker compose exec -T api python scripts/collect_sources.py --since-days 60 --limit 20
docker compose exec -T api python scripts/process_corpus.py
docker compose exec -T api python scripts/embed_corpus.py
```

**Checks, as in CI.** The laptop's package versions differ from CI's, so read the whole output:

```powershell
python -m pip install -e ".[dev]"
python -m ruff check src tests scripts
python -m mypy src
python -m pytest
cd apps/web; npm ci; npm run build
```

CI type-checks against the newest SQLAlchemy 2.x; write statement annotations as `Select[Any]`.

## Scripts

| Script | Purpose |
| --- | --- |
| `collect_sources.py` | List and download documents ([pipeline](pipeline.md#running-it)) |
| `process_corpus.py` | Extract and chunk. `--rechunk-outdated`, `--retry-failed`, `--reocr`, `--reextract-legacy-text`, `--all` |
| `embed_corpus.py` | Embed passages without a current embedding |
| `evaluate_tax_retrieval.py`, `evaluate_retrieval.py`, `evaluate_qa.py` | Retrieval evaluation, one ad hoc query, answer evaluation ([retrieval](retrieval.md#evaluation)) |
| `freeze_corpus.py`, `compare_retrieval_runs.py` | Record or check a corpus; paired comparison of two reports |
| `extract_repeals.py`, `add_ministry_expiry.py` | Build lists of ended documents |
| `correct_document_numbers.py` | Apply `number-corrections-v2.json`. A dry run unless `--apply` |
| `decompose_issues.py`, `diagnose_retrieval_misses.py`, `measure_reference_reachability.py` | Experiment tools |
| `annotation_agreement.py` | Cohen's kappa between annotators |
| `list_cited_candidates.py`, `list_portal_candidates.py`, `complete_portal_candidates.py`, `resolve_cited_candidates.py`, `select_corpus_v2.py` | Build a corpus selection |
| `benchmark_ocr.py`, `prune_non_tax_documents.py` | OCR comparison; delete non-tax documents with `--apply` |
| `seed.py`, `ingest_manifest.py`, `repair_document_metadata.py`, `ingest_sources.py`, `discover_sources.py` | Sample data and older one-off ingestion |

## Laptop access to Azure

The database allows listed IPs only, and the laptop's IP changes often. Check first:

```powershell
$ip = (Invoke-RestMethod https://api.ipify.org)
az postgres flexible-server firewall-rule list -g taxlens-dev-rg --server-name taxlens-dev-pg -o table
az postgres flexible-server firewall-rule create -g taxlens-dev-rg --server-name taxlens-dev-pg --name laptop-N --start-ip-address $ip --end-ip-address $ip
```

Note `--server-name`. A connection timeout usually means a missing rule. Then, in the same terminal:

```powershell
pip install -e ".[cloud]"
$env:DATABASE_HOST = "taxlens-dev-pg.postgres.database.azure.com"
$env:DATABASE_USER = "taxlensadmin"
$env:DATABASE_PASSWORD = "<PostgreSQL admin password>"
$env:DATABASE_SSL_MODE = "require"
$env:OBJECT_STORAGE_BACKEND = "azure_blob"
$env:AZURE_STORAGE_CONNECTION_STRING = (az storage account show-connection-string -g taxlens-dev-rg -n taxlensdevartifacts -o tsv)
```

## Growing the corpus

**This changes the frozen corpus,** so freeze a new version and repeat baselines afterwards.

**Airflow on and off.** The scheduler costs money while running, so keep both apps stopped between runs. The
site works without them:

```bash
az containerapp start -g taxlens-dev-rg -n taxlens-dev-airflow-scheduler
```

```bash
az containerapp start -g taxlens-dev-rg -n taxlens-dev-airflow-web
```

```bash
az containerapp stop -g taxlens-dev-rg -n taxlens-dev-airflow-scheduler
```

```bash
az containerapp stop -g taxlens-dev-rg -n taxlens-dev-airflow-web
```

**Government portal.** Trigger `taxlens_corpus_maintenance` from the Airflow UI with `backfill_dry_run`, then
`backfill_corpus`, or `collect_selected` for a selection, such as
`{"action": "collect_selected", "limit": 100, "rounds": 10}`. Keep the daily DAG paused, and do not release
during a run. Azure keeps 7 days of point-in-time restore for the database.

### Ministry of Finance from a laptop in Vietnam

Set up [laptop access](#laptop-access-to-azure), then:

```powershell
python scripts/collect_sources.py --source mof --from-year 1990 --dry-run
python scripts/collect_sources.py --source mof --from-year 1990 --limit 300
```

Then run `process_and_embed` in Airflow.

### Freezing a new corpus

```powershell
python scripts/freeze_corpus.py --label corpus-vN --output data/evaluation/corpus/corpus-vN.json
python scripts/extract_repeals.py --output data/evaluation/repeals/corpus-vN.json
```

Check before freezing: failures, TCVN3 words, missing embeddings, and new `DOCUMENT_NUMBER_MISMATCH` flags,
reading a sample of real text rather than only counts. `add_ministry_expiry.py` has fixed paths, so point it
at the new list and manifest. Then repeat the baselines.

## Release

`main` is protected. The owner is on the bypass list and may push directly after running the checks;
otherwise use a pull request.

1. Wait for **CI** to pass. Do not release on a failure.
2. Check no Airflow run is in progress, since a deploy kills its jobs.
3. Run **Release and deploy** on `main`. It builds images tagged with the SHA, then plans and applies Terraform.
   The API applies migrations when it starts.

Untick `build` and enter an `image_tag` to roll back. Untick `apply` for a plan only. See what is live:

```bash
az containerapp show -g taxlens-dev-rg -n taxlens-dev-api --query "properties.template.containers[0].image" -o tsv
```

Do not run `alembic upgrade` on Azure before the release containing the migration: the running image would not
know the revision and could not restart. To prepare an index, build it by hand with
`CREATE INDEX CONCURRENTLY IF NOT EXISTS`, and write the migration with `IF NOT EXISTS`.

**Secrets for the workflow:** `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
`TF_VAR_POSTGRES_ADMIN_PASSWORD`, `TF_VAR_HF_TOKEN`, `TF_VAR_AUTH_INTERNAL_TOKEN`, `TF_VAR_NEXTAUTH_SECRET`,
`TF_VAR_AIRFLOW_ADMIN_PASSWORD`, `TF_VAR_AIRFLOW_INTERNAL_TOKEN`, and optionally `TF_VAR_POSTGRES_ALLOWED_IP`. The
OIDC principal needs `Storage Blob Data Contributor` on the state account, `Contributor` and
`User Access Administrator` on the group, and `Key Vault Secrets Officer` on `taxlensdevkv`.

**Terraform** deploys through the workflow. Locally, for inspection or recovery only: `az login`,
`terraform init`, `terraform plan`, with inputs in an ignored `terraform.tfvars`. State holds secrets, and lives
in the private `terraform-state` container.

## Costs

October 2026: $17.76.

| Resource | Cost | Note |
| --- | --- | --- |
| `taxlensdevacr` | $9.03 | Basic includes 10 GB, and it held 82 GB of old images |
| `CreditScorecardWOEIV` (another project) | $5.16 | Registry in `docker-fastapi-credit-scorecard` |
| `taxlens-dev-api`, `-web` | $2.00 | Scale to zero |
| `taxlens-dev-airflow-*` | $1.29 | Free while stopped |
| Storage, Key Vault | $0.28 | |
| PostgreSQL, Log Analytics | $0.00 | Not billed at present; check before relying on that |

Keep the 3 newest images of each repository, after checking the list. A deleted image can only be rebuilt from
its commit:

```bash
for repo in taxlens-api taxlens-web taxlens-airflow; do
  az acr repository show-tags -n taxlensdevacr --repository "$repo" --orderby time_desc -o tsv | tail -n +4 |
    while read -r tag; do az acr repository delete -n taxlensdevacr --image "$repo:$tag" --yes; done
done
```

## Logs

| What | Where |
| --- | --- |
| A DAG task's job output | Airflow UI → task → **Logs** |
| API requests and job events | `az containerapp logs show -g taxlens-dev-rg -n taxlens-dev-api --type console --tail 300` |
| Older and searchable | Log Analytics, `ContainerAppConsoleLogs_CL` and `ContainerAppSystemLogs_CL`, through `az rest` to `api.loganalytics.io` with a JSON body file |
| Raw Airflow logs | `airflow-logs` share. Colons in run IDs are stored as U+F022, so use the File REST API with `%EF%80%A2` |

`az containerapp exec` splits on spaces, so trigger DAGs with config from the UI. It handles simple commands
such as `airflow dags pause tax_regulation_discovery_daily`. It rate-limits with a 429, and fails with "Could
not find a replica" while scaled to zero.

## Troubleshooting

| Symptom | Cause | Action |
| --- | --- | --- |
| "The service could not be reached" | The browser got no response; usually its own connection | Check the API log. If the question is absent or returned 200, retry on a steady connection |
| "The API service could not be reached" | The web proxy could not reach the API | Read the API and system logs |
| First question takes minutes | The API scaled to zero | Wait. Questions are not retried |
| Every answer `PROVIDER_UNAVAILABLE`, status 400 "not supported by any provider" | The router dropped `HF_CHAT_MODEL` | Choose from `https://router.huggingface.co/v1/models`. Avoid reasoning models |
| Every answer `PROVIDER_UNAVAILABLE`, status 402 | No credits | Add credits |
| Occasional `PROVIDER_UNAVAILABLE`, `ReadTimeout` | Model over 90 s | Retry, or raise the timeout, staying under 240 s |
| Laptop: `ConnectionTimeout` or "Cannot reach the database" | IP not allowed, settings not set, or no internet | [Laptop access](#laptop-access-to-azure) |
| Laptop: "Cannot use azure_blob storage" | SDK missing | `pip install -e ".[cloud]"` |
| Ministry: `ConnectTimeout` | Not on a Vietnamese network | Run from Vietnam |
| Job exit code -9 | Six-hour limit or out of memory | Rerun |
| Document stays `FAILED` | Broken file or unusable scan | Fix the cause, then `retry_failed_documents` |
| No new documents for days | Airflow stopped or DAG paused. Currently intended | Start it only if the corpus should change |
