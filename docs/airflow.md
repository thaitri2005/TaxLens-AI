# Airflow

Airflow schedules TaxLens's long-running work but does none of it itself. Each task
asks the API to start a job (a script in `scripts/`), then polls the job and prints its
output into the task log until it finishes; see
[architecture.md](architecture.md#background-jobs). Airflow has its own Python
environment and never touches the application database or the model.

## Daily DAG: `tax_regulation_discovery_daily`

Runs at 03:00 UTC (10:00 in Vietnam):

| Task | Job | Notes |
| --- | --- | --- |
| `discover_and_ingest_government_sources` | `collect_sources.py --source government --since-days 60` | Up to `TAXLENS_DAILY_SOURCE_LIMIT` (100) new downloads. |
| `process_pending_documents` | `process_corpus.py --limit N` | N = `TAXLENS_PROCESS_BATCH_SIZE` × `TAXLENS_PROCESS_MAX_BATCHES`. |
| `rechunk_outdated_documents` | `process_corpus.py --rechunk-outdated` | Re-chunks versions made by an older `CHUNKER_VERSION` from stored text, without OCR. |
| `embed_pending_chunks` | `embed_corpus.py` | Embeds every passage without a current embedding. |
| `evaluate_tax_retrieval` | `evaluate_tax_retrieval.py` | Writes the retrieval report ([evaluation.md](evaluation.md)). |

Processing, re-chunking, and embedding run even when an earlier task fails, so a portal
outage or one bad document does not block the rest. Documents whose processing failed are
not retried automatically; use `retry_failed_documents`.

With the corpus collected, a daily run takes a few minutes plus OCR time for the day's
new scans.

## Maintenance DAG: `taxlens_corpus_maintenance`

No schedule. Start it with **Trigger DAG** (with config) and choose an `action`. It runs
one action at a time (`max_active_runs=1`), so a second trigger waits for the first.

| Action | What it does | Typical duration |
| --- | --- | --- |
| `backfill_dry_run` | Lists the government portal by year from `from_year` and counts documents not yet collected. | 5–7 min |
| `backfill_corpus` | Collects up to `limit` (300) of them, then processes and embeds. Repeat until the dry run reports none remaining. | 10 min to several hours, depending on how many long scans need OCR |
| `process_and_embed` | Processes every pending version, then embeds. Use after a laptop Ministry of Finance run. | Embedding: about 0.3 s per new passage |
| `retry_failed_documents` | Retries versions whose processing failed, then embeds. | Varies |
| `reocr_scanned_documents` | Re-runs OCR on every OCR'd document with the current settings, then embeds. | Many hours |
| `prune_non_tax_dry_run` / `prune_non_tax_apply` | Lists, then deletes, documents whose titles are not about tax. | Minutes |
| `ocr_benchmark` | OCRs a few pages of `document_number` at several settings and reports word error rates against its text layer. Use a born-digital PDF. | Minutes |

`include_expired` (off by default) also collects documents the Ministry marks expired.

## Reading the logs

Task logs show the job's own output, a batch of lines about every 20 seconds:

```text
01:39:08 617 new document(s) to collect; 832 already in the corpus
01:39:09 [2/300] 04/2007/QĐ-BTC | NEW_DOCUMENT | msword 112 KB | 2m48s left
[17/595] DONE 137/2016/NĐ-CP | PROCESSED | 167 chunks | ocr | 456.4s
Checked 12000/54802 chunk(s): 4994 embedded, 7006 already current | 22m08s
```

- `exit code -9` means the process was killed: by the six-hour job limit (duration
  about 21,600 s) or by running out of memory. Rerun; the work already done is kept.
- `failed with exit code 1` comes with the script's own error message at the end of the
  output.
- A 404 while polling means the API restarted (usually a deploy) and lost the job.
  Airflow retries the task.
- Long tariff schedules (150+ scanned pages) take 6–9 minutes each to OCR; a run that
  reaches a series of them is slow, not stuck.

## Running locally

```powershell
docker compose --profile airflow up -d airflow-postgres airflow-init airflow-scheduler airflow-webserver
```

Open `http://localhost:8080` with the Airflow credentials from `.env`. Locally the DAGs
call the Compose `api` service; no Docker socket is exposed to Airflow.

## In Azure

- The scheduler runs one always-on replica; the webserver scales to zero and starts when
  the UI is opened.
- Both mount the `airflow-logs` Azure Files share at `/opt/airflow/logs`, because the two
  Container Apps cannot reach each other's log server.
- The DAG image (`airflow/Dockerfile`) contains the DAG files; deploying a DAG change
  means publishing and deploying a new image.
- Pause or unpause a DAG with the toggle in the UI, or from a shell:
  `az containerapp exec -g taxlens-dev-rg -n taxlens-dev-airflow-scheduler --command "airflow dags pause tax_regulation_discovery_daily"`.

Operating procedures, including how to trigger DAGs from the command line and read logs
from the file share, are in [operations.md](operations.md).
