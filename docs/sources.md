# Document sources and collection

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

`scripts/collect_sources.py` does both sources in one run, ministry first:

```powershell
python scripts/collect_sources.py --since-days 60 --limit 100   # daily
python scripts/collect_sources.py --from-year 1990 --dry-run     # how much is missing
python scripts/collect_sources.py --from-year 1990 --limit 300   # one backfill batch
```

In Azure:

- The daily DAG's first task runs the `--since-days 60` form (a few requests per source).
- The `taxlens_corpus_maintenance` DAG has `backfill_dry_run` and `backfill_corpus`
  actions (`from_year`, `limit`, `include_expired`). `backfill_corpus` collects up to
  `limit` documents, then processes and embeds them; run it until the dry run reports
  nothing remaining. Listing the full ministry selection takes about ten minutes because
  its API is slow with large pages.

## Ministry of Finance access from Azure

`vbpq.mof.gov.vn` does not accept connections from Azure (the East Asia region, Hong Kong):
TCP connections time out, while the same API answers in seconds from a Vietnamese network
and the government portal is reachable from Azure. The site appears to accept Vietnamese
IP addresses only, and Azure has no region in Vietnam. Scheduled runs therefore collect
from the government portal and report the ministry as unavailable instead of failing.

Ministry collection runs from a machine in Vietnam against the Azure database and Blob
Storage; it only lists and downloads, so it needs no OCR or embedding model:

```powershell
pip install -e ".[cloud]"
$env:DATABASE_HOST = "taxlens-dev-pg.postgres.database.azure.com"
$env:DATABASE_USER = "taxlensadmin"
$env:DATABASE_PASSWORD = "<PostgreSQL admin password>"
$env:DATABASE_SSL_MODE = "require"
$env:OBJECT_STORAGE_BACKEND = "azure_blob"
$env:AZURE_STORAGE_CONNECTION_STRING = "<artifacts storage connection string>"
python scripts/collect_sources.py --source mof --from-year 1990 --dry-run
python scripts/collect_sources.py --source mof --from-year 1990 --limit 300
```

The PostgreSQL firewall must allow the machine's public IP (`postgres_allowed_ip` in
Terraform). Then run the `taxlens_corpus_maintenance` DAG with `process_and_embed` so OCR
and embedding happen in Azure. For unattended collection, the alternative is a small
proxy hosted in Vietnam.

## Not used

- **vbpl.vn** (national legal database): did not respond during evaluation.
- **Commercial legal databases** (thuvienphapluat.vn, luatvietnam.vn): their terms do not
  allow automated collection.
- **Official letters (công văn) of the tax authority**: useful interpretations, but not
  normative and very numerous; a candidate for a later, separate collection.
