# Collection pipeline

Where documents come from, what is collected, and the Airflow DAGs that collect,
process, and embed them.

TaxLens collects Vietnamese tax law from two official sources. Both were chosen because
they can be filtered to tax **before** anything is downloaded, reach back decades, and are
published by the issuing authorities themselves.

| | Ministry of Finance database | Government portal |
| --- | --- | --- |
| Address | `vbpq.mof.gov.vn` (JSON API) | `vanban.chinhphu.vn` (search form) |
| Holds | Finance circulars, joint circulars, consolidated texts (VBHN) | Laws, decrees, Prime Minister decisions, finance circulars |
| Tax selection | "Quản lý thuế, phí và lệ phí" field (tagged until about 2016) and the tax, tax-policy, and customs drafting departments (later documents) | "Thuế - Lệ phí" category |
| History | 1957 onwards | 1988 onwards |
| Legal status | Yes: in force, expired, partly expired, not yet in force | No (recorded as `DISCOVERED`) |
| Files | About half Word (`.doc`), half PDF | Mostly PDF, some Word |
| Implementation | `taxlens/ingestion/mof.py` | `GovernmentPortalSearch` in `taxlens/ingestion/connectors.py` |

As of October 2026 the ministry selection returns 928 in-force normative tax documents
(858 circulars, 62 joint circulars, plus decrees, a law, and consolidated texts): 484 Word
files and 444 PDFs. The portal's tax category holds about 1,500 documents from 1988.

**Corpus in October 2026**: 2,013 documents and 59,598 passages, all embedded and
searchable except 8 documents whose processing failed. 785 come from the ministry
database and 1,229 from the portal's tax category (one document is held from both),
from 1990 onwards. 771 are recorded as in force; the 1,228 portal documents have no
recorded status. The portal backfill had 18 documents left to collect, plus 3 whose
files the portal no longer serves.

## What is collected

- **Normative documents only.** From the ministry database: circulars, joint circulars,
  decrees, laws, ordinances, resolutions, and consolidated texts. Decisions (mostly
  appointments and procedure lists) and official letters are skipped by default.
- **National documents only.** Provincial decisions and council resolutions (`QĐ-UBND`,
  `NQ-HĐND`) from the portal are dropped.
- **In-force documents first.** Expired documents are skipped unless
  `--include-expired` is given; the ministry's status marks them as expired, and the
  evidence gate already prefers current provisions.
- **One file per document**, preferring DOCX, DOC, RTF, then PDF. Further attachments are
  usually appendix forms, which cost OCR time for little retrieval value.
- **No duplicates.** A source file already ingested is not downloaded again. A portal
  document whose number is already in the corpus is skipped, because the ministry record
  (with status and effective date) is richer.

Consolidated texts restart their numbering every year (`18/VBHN-BTC` exists for 2025 and
2026 with different content), so the ministry connector stores them as
`18/VBHN-BTC (2026)`. Document numbers are normalized for Cyrillic letters that look Latin
(the portal lists `255/2026/NĐ-CР` with a Cyrillic `Р`).

## Cost

Listing is metadata only and cheap. The costs are downloading, OCR, and embedding, all on
the API's single vCPU:

| Step | Word file | Scanned PDF |
| --- | --- | --- |
| Text extraction | well under a second | about 2.5 s per page (Tesseract, 300 DPI) |
| Embedding | about 0.3 s per passage | the same |

Word files therefore cost a small fraction of a scan, and their text is exact. The format
is detected from the file content (`taxlens/document_processing/formats.py`): files named
`.doc` are often RTF. Text in the pre-Unicode TCVN3 encoding (`.VnTime` fonts, common
before about 2005) and RTF runs in the Windows Vietnamese code page are converted to
Unicode. Documents from before about 2011 often have no "Điều" articles; they are split by
their section headings ("PHẦN A", "I. ĐỐI TƯỢNG ÁP DỤNG") instead, and Word documents carry
no page numbers.

## Running collection

`scripts/collect_sources.py` collects from `--source government` (the default), `mof`, or
`all` (ministry first):

```powershell
python scripts/collect_sources.py --since-days 60 --limit 100   # daily (Airflow)
python scripts/collect_sources.py --from-year 1990 --dry-run     # how much is missing
python scripts/collect_sources.py --from-year 1990 --limit 300   # one backfill batch
```

In Azure:

- The daily DAG's first task runs the `--since-days 60` form against the government portal.
- The `taxlens_corpus_maintenance` DAG has `backfill_dry_run` and `backfill_corpus`
  actions (`from_year`, `limit`, `include_expired`). `backfill_corpus` collects up to
  `limit` documents, then processes and embeds them; run it until the dry run reports
  nothing remaining. Listing the portal from 1990 takes five to seven minutes.
- A portal year whose search keeps timing out (three attempts) is skipped with a warning
  and listed again by the next run; only a run where every year fails stops collection.
- The task log shows the job's progress lines as they are written (every 20 seconds),
  not only when the job ends.

## Ministry of Finance access from Azure

`vbpq.mof.gov.vn` appears to accept Vietnamese IP addresses only, so Airflow collects from
the government portal alone. Ministry collection runs from a machine in Vietnam, writing
straight to the Azure database and Blob Storage; it only lists and downloads, and the
`process_and_embed` maintenance action does the rest in Azure. The reasoning is in the
[design decision](architecture.md#collect-the-ministry-of-finance-database-from-a-machine-in-vietnam)
and the procedure in
[operations.md](operations.md#ministry-of-finance-from-a-laptop-in-vietnam).

`collect_sources.py` prints timestamped progress, so a quiet console never means "maybe
stuck":

```text
13:44:15 Ministry of Finance tax department: page 1/4 (100 of 335 records)
13:54:02 Ministry of Finance: kept 928 of 2700 records (normative documents not expired ...)
13:54:03 412 new document(s) to collect; 516 already in the corpus
13:54:05 [1/300] 111/2013/TT-BTC | NEW_DOCUMENT | msword 152 KB | 14m10s left
```

Listing the full ministry selection takes about ten minutes (its API is slow with large
pages) and is cached for 24 hours; each download takes a second or two.

## Not used

- **vbpl.vn** (national legal database): did not respond during evaluation.
- **Commercial legal databases** (thuvienphapluat.vn, luatvietnam.vn): their terms do not
  allow automated collection.
- **Official letters (công văn) of the tax authority**: useful interpretations, but not
  normative and very numerous; a candidate for a later, separate collection.

## Airflow

Airflow schedules TaxLens's long-running work but does none of it itself. Each task
asks the API to start a job (a script in `scripts/`), then polls the job and prints its
output into the task log until it finishes; see
[architecture.md](architecture.md#background-jobs). Airflow has its own Python
environment and never touches the application database or the model.

### Daily DAG: `tax_regulation_discovery_daily`

Runs at 03:00 UTC (10:00 in Vietnam):

| Task | Job | Notes |
| --- | --- | --- |
| `discover_and_ingest_government_sources` | `collect_sources.py --source government --since-days 60` | Up to `TAXLENS_DAILY_SOURCE_LIMIT` (100) new downloads. |
| `process_pending_documents` | `process_corpus.py --limit N` | N = `TAXLENS_PROCESS_BATCH_SIZE` × `TAXLENS_PROCESS_MAX_BATCHES`. |
| `rechunk_outdated_documents` | `process_corpus.py --rechunk-outdated` | Re-chunks versions made by an older `CHUNKER_VERSION` from stored text, without OCR. |
| `embed_pending_chunks` | `embed_corpus.py` | Embeds every passage without a current embedding. |
| `evaluate_tax_retrieval` | `evaluate_tax_retrieval.py` | Writes the retrieval report ([retrieval.md](retrieval.md#evaluation)). |

Processing, re-chunking, and embedding run even when an earlier task fails, so a portal
outage or one bad document does not block the rest. Documents whose processing failed are
not retried automatically; use `retry_failed_documents`.

With the corpus collected, a daily run takes a few minutes plus OCR time for the day's
new scans.

### Maintenance DAG: `taxlens_corpus_maintenance`

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

### Reading the logs

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

### Running locally

```powershell
docker compose --profile airflow up -d airflow-postgres airflow-init airflow-scheduler airflow-webserver
```

Open `http://localhost:8080` with the Airflow credentials from `.env`. Locally the DAGs
call the Compose `api` service; no Docker socket is exposed to Airflow.

### In Azure

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
