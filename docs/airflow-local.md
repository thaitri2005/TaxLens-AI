# Airflow local profile

Airflow is the scheduled-ingestion component for TaxLens. The daily DAG calls
the existing idempotent commands in order:

```text
discover and ingest → process and OCR → embed pending chunks → evaluate retrieval
```

The normal PostgreSQL/API/web profile remains unchanged. Start the scheduler
profile explicitly after the API image has been built:

```powershell
docker compose --profile airflow up -d airflow-postgres airflow-init airflow-scheduler airflow-webserver
```

Open `http://localhost:8080` and sign in with the credentials in `.env` or the
Compose defaults. Trigger `tax_regulation_discovery_daily` manually for a
smoke test, then inspect task logs and retry behavior.

Airflow has its own Python environment because Airflow and the API use
different SQLAlchemy compatibility ranges. The DAG discovers sources (keeping
only tax-related titles), processes new documents, re-chunks documents indexed by an
older chunker version, embeds pending passages, and evaluates retrieval by calling
allowlisted internal API job endpoints over the Compose network using
`X-TaxLens-Internal-Token`; the API executes the existing scripts in its own
runtime, preserving Tesseract and the baked-in embedding model.

Jobs run in the background on the API. Each task starts its job with one short
POST, which returns a job ID, and then polls `GET /internal/airflow/jobs/{id}`
every 20 seconds until the job completes or fails (`airflow/dags/taxlens_jobs.py`).
Azure Container Apps ends HTTP requests after 240 seconds and OCR of one long scan
takes several minutes, so the earlier design that held the request open for the
whole job failed on such documents; the polling also keeps the scale-to-zero API
awake while a job runs. A retried task reattaches to its still-running job rather
than starting a duplicate. Jobs are limited to six hours, and an API restart loses
running jobs (the poll then gets 404 and Airflow retries). `TAXLENS_PROCESS_BATCH_SIZE`
× `TAXLENS_PROCESS_MAX_BATCHES` sets how many new documents one run processes.
Processing, re-chunking, and embedding still run when an earlier task fails, so a
portal outage or one bad document does not block the rest. No Docker socket is
exposed to Airflow.

Documents that fail processing, such as image-only PDFs that produce
`OCR_REQUIRED`, are skipped on later scheduled runs.

## Maintenance DAG

`taxlens_corpus_maintenance` has no schedule. Start it with **Trigger DAG w/ config**
and choose an `action`:

| Action | What it does |
| --- | --- |
| `ocr_benchmark` | OCRs a few pages of `document_number` with several DPI and page-segmentation settings and prints word error rates against the PDF's text layer. Use a born-digital PDF. |
| `reocr_scanned_documents` | Re-runs OCR for every OCR'd document with the current settings, then embeds. Slow: several minutes per long scan. |
| `retry_failed_documents` | Retries versions whose processing failed, then embeds. |
