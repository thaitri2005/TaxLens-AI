# Collection pipeline

Where documents come from and the Airflow DAGs that collect, process, and embed them. **Airflow is
stopped and the corpus frozen** ([status](evaluation-status.md)).

| | Ministry of Finance | Government portal |
| --- | --- | --- |
| Address | `vbpq.mof.gov.vn` (JSON API) | `vanban.chinhphu.vn` (search form) |
| Holds | Finance circulars, joint circulars, consolidated texts | Laws, decrees, decisions, circulars |
| Legal status | Yes | No (`DISCOVERED`) |
| Files | About half Word, half PDF | Mostly PDF |
| Reachable from | **Vietnam only** ([why](architecture.md#design-decisions)) | Azure and anywhere |
| Code | `ingestion/mof.py` | `GovernmentPortalSearch` in `ingestion/connectors.py` |

## What is collected

- Normative, national documents. Decisions, official letters, and provincial documents are skipped.
- In-force documents, unless `--include-expired` is given or the document is in a selection list.
- One file per document, preferring DOCX, DOC, RTF, then PDF.
- No duplicates by source record. A portal document whose number is held is skipped, as the ministry
  record is richer. **The portal's listed numbers can be wrong:** check `DOCUMENT_NUMBER_MISMATCH` flags.
- Consolidated texts restart numbering yearly, so they are stored as `18/VBHN-BTC (2026)`. Cyrillic
  look-alike letters in numbers are normalized.

## Running it

```powershell
python scripts/collect_sources.py --since-days 60 --limit 100   # daily, from the portal
python scripts/collect_sources.py --from-year 1990 --dry-run     # how much is missing
python scripts/collect_sources.py --source mof --from-year 1990 --limit 300
python scripts/collect_sources.py --source mof --selected data/evaluation/corpus/selected-v2.json --limit 40
```

`--cited-by <gold set>` collects what a gold set cites, and `--only <numbers>` limits a run. Listing the
ministry takes about ten minutes and is cached for 24 hours. Laptop steps are in
[operations.md](operations.md#ministry-of-finance-from-a-laptop-in-vietnam).

## Airflow

Each task asks the API to start a job (a script), then polls and prints its output
([how](architecture.md#background-jobs)). Airflow never touches the database or model itself.

**Daily DAG `tax_regulation_discovery_daily`** (03:00 UTC): collect from the portal, process, re-chunk
outdated versions, embed, evaluate. Later tasks run even if an earlier one fails. It changes the corpus, so
keep it paused while the corpus is frozen.

**Maintenance DAG `taxlens_corpus_maintenance`**: no schedule. Trigger with config, one at a time.

| Action | What it does | Time |
| --- | --- | --- |
| `backfill_dry_run`, `backfill_corpus` | Count, then collect up to `limit` (300) from the portal, process, and embed | 5-7 min; up to hours |
| `collect_selected_dry_run`, `collect_selected` | The same for `selected-v2.json`, with `limit` and `rounds` | 1-2 h per 100 |
| `process_and_embed` | Process pending versions, then embed. Use after a laptop run | 0.3 s a passage |
| `retry_failed_documents` | Retry failed versions, then embed | Varies |
| `rechunk_outdated` | Re-chunk older chunker versions from stored text | Minutes, plus embedding |
| `reextract_listed` | Extract `reextract-v2.json` documents again | Depends on pages |
| `reextract_legacy_text` | Extract documents still holding TCVN3 again. Safe to repeat | Minutes |
| `reocr_scanned_documents` | OCR every scanned document again | Many hours |
| `prune_non_tax_dry_run`, `prune_non_tax_apply` | List, then delete, documents not about tax | Minutes |
| `ocr_benchmark` | Compare OCR settings on `document_number` | Minutes |

**Reading task logs.** `exit code -9` is the six-hour limit (about 21,600 s) or out of memory: rerun, as
finished work is kept. `exit code 1` comes with the script's error. A 404 while polling means the API
restarted and Airflow retries. Long scans take 6-9 minutes each, so a slow run is not necessarily stuck.

**Locally:** `docker compose --profile airflow up -d airflow-postgres airflow-init airflow-scheduler airflow-webserver`,
at <http://localhost:8080>.

**In Azure:** the scheduler is one always-on replica, the webserver scales to zero, and both mount the
`airflow-logs` share. DAG changes need a release. Commands are in [operations.md](operations.md).
