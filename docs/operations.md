# Operations

Procedures for the Azure development environment (`taxlens-dev-rg`). Commands assume an
authenticated Azure CLI (`az login`) and PowerShell unless shown otherwise.

## Release

1. Push to `main` and wait for **CI** to pass (backend checks, web build, Terraform
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

## Growing the corpus

### Government portal (from Azure)

Run the `taxlens_corpus_maintenance` DAG with `backfill_dry_run` to see how many documents
are missing, then `backfill_corpus` until none remain. Each run collects up to 300.

### Ministry of Finance (from a laptop in Vietnam)

The Ministry's site rejects connections from Azure ([ADR 0003](adr/0003-ministry-relay.md)).

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
| Pages are slow for a minute, then fine | The API was scaled to zero | None; the web client retries while it starts. |
| "Expired identity" | An API image from before October 2026 accepted identities for only 60 s, less than a cold start | Deploy a current release. |
| A job fails with exit code -9 after about 21,600 s | Six-hour job limit | Rerun the action; finished work is kept. |
| A job fails with exit code -9 earlier | Out of memory in the 2 GiB API container | Check that no other long job was running at the same time; rerun. |
| Every answer is `PROVIDER_UNAVAILABLE` | The Hugging Face token has no inference credits (HTTP 402 in the API log as `chat_provider_error`) | Add credits or point `HF_CHAT_BASE_URL` at another OpenAI-compatible endpoint. |
| Collection logs "Government portal unavailable" | The portal timed out | A slow year is skipped after three attempts; the next run lists it again. |
| Ministry collection: `ConnectTimeout` | Run from outside Vietnam | Run it from a Vietnamese network ([ADR 0003](adr/0003-ministry-relay.md)). |
| Laptop run: "Cannot reach the database" | Settings not set in this terminal, or IP not allowed | Set the variables in the same window and add the firewall rule. |
| Laptop run: "Cannot use azure_blob storage" | The Azure SDK is missing | `pip install -e ".[cloud]"`. |
| A document stays `FAILED` | Extraction failed (broken file, unusable scan) | Run `retry_failed_documents` after fixing the cause; the error code is shown on the document page. |
