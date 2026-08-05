# Local Development

## Prerequisites

- Python 3.12
- Docker Desktop with Docker Compose

## Start the application

1. Copy `.env.example` to `.env`.
2. Run `docker compose up --build`.
3. Run `docker compose exec api alembic upgrade head`.
4. Open `http://localhost:8000/health`.

## Run quality checks locally

Install the project with `python -m pip install -e ".[dev]"`, then run:

```powershell
$env:PYTHONPATH = "src"
pytest
ruff check .
mypy src
```

The initial Compose profile runs PostgreSQL/pgvector and the API only. Workers, Airflow, MLflow, and monitoring are added in later phases.

## Seed, process, and search the sample corpus

```powershell
docker compose exec -T api alembic upgrade head
docker compose exec -T api python scripts/seed.py
docker compose exec -T api python scripts/process_corpus.py
docker compose exec -T api python scripts/embed_corpus.py
Invoke-RestMethod 'http://localhost:8000/search?q=invoice&legal_status=EFFECTIVE' |
  ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post 'http://localhost:8000/comparisons' `
  -ContentType 'application/json' `
  -Body '{"before_document_number":"02/2024/TT-BTC","after_document_number":"31/2025/TT-BTC"}' |
  ConvertTo-Json -Depth 8

Invoke-RestMethod -Method Post 'http://localhost:8000/comparisons/summary' `
  -ContentType 'application/json' `
  -Body '{"before_document_number":"02/2024/TT-BTC","after_document_number":"31/2025/TT-BTC"}' |
  ConvertTo-Json -Depth 8
```

The search endpoint supports `document_number`, `document_type`, `legal_status`,
`issuing_agency`, `effective_from`, `effective_to`, and `limit` filters.

# Hugging Face inference

For the intelligence-workflow milestone, set `HF_TOKEN=hf_...` in your local `.env` file. Do not commit it or place it in `.env.example`. `HF_CHAT_MODEL` and `HF_CHAT_ROUTING_POLICY` select the model and routed provider policy independently, so changing either never requires a code change.

The next cited-Q&A endpoint will call the chat provider only when query planning and evidence-sufficiency checks pass. Queries with no evidence, conflicting document statuses, or missing structural locators return an evidence-only/unsupported response instead.

## Discover official sources

Discovery is read-only and does not download or ingest documents:

```powershell
python scripts/discover_sources.py --source mof
python scripts/discover_sources.py --source government
```

To persist a small batch of discovered official PDFs, use an explicit limit:

```powershell
python scripts/ingest_sources.py --source government --limit 1 --download
python scripts/process_corpus.py
```

The command is read-only unless `--download` is provided. Downloaded PDFs are
stored under local object storage and remain idempotent by content hash. The
Ministry of Finance portal currently renders its catalog dynamically, so its
connector is retained for safe official URL fetching while catalog discovery
will need a portal-specific endpoint or export in a later iteration.

For a repeatable development corpus, ingest a small Government Portal batch:

```powershell
docker compose exec -T api python scripts/ingest_sources.py --source government --limit 4 --download
docker compose exec -T api python scripts/process_corpus.py
docker compose exec -T api python scripts/embed_corpus.py
```

This is intentionally a bounded demo corpus, not a production crawl.

Some official PDFs are image-only scans. The processor does not create empty
search chunks for these files. The API first tries native PDF extraction and
then uses local Tesseract with Vietnamese and English language data when the
native text is empty or unusable. If Tesseract is unavailable or still finds
no usable text, it records an `OCR_REQUIRED` processing failure.

The curated tax manifest is the preferred development workflow:

```powershell
docker compose exec -T api python scripts/ingest_manifest.py --download
docker compose exec -T api python scripts/process_corpus.py
docker compose exec -T api python scripts/embed_corpus.py
```

Edit `data/corpus/tax_documents.json` to add or remove explicitly reviewed
official tax documents. Keep the manifest small and topical during development.

For a portal with dynamic catalog rendering, ingest an explicitly selected
official PDF instead:

```powershell
docker compose exec -T api python scripts/ingest_sources.py --source mof `
  --url https://vbpq.mof.gov.vn/DKC.FileManagement/FileStorage/File/247067 `
  --document-number 11/2024/TT-BTC `
  --title "Quy định mức thu, chế độ thu, nộp, quản lý và sử dụng phí khai thác và sử dụng tài liệu địa chất, khoáng sản" `
  --issue-date 2024-02-05 --download
```

The explicit URL path is also bounded and idempotent.

Processing now extracts basic document type, issuing agency, and issue date
when the official catalog exposes them. PDF chunks retain page start/end
metadata, and extraction failures are recorded on the processing job so one
bad document does not terminate the whole batch.

After processing, generate embeddings and run retrieval smoke checks:

```powershell
python scripts/embed_corpus.py
python scripts/evaluate_retrieval.py --query "thuế suất giá trị gia tăng"
python scripts/evaluate_tax_retrieval.py
```

The evaluation output includes fused ranking scores and stored official source
URLs so retrieval quality and provenance can be inspected together.
Document-level evaluation de-duplicates chunks from the same document while
preserving their first-ranked order.

The labeled tax baseline currently reports `Hit@5`, Recall@5, and MRR for four
queries. Treat these numbers as a regression baseline, not a quality claim: the
current corpus contains sparse text-extractable tax content and several
official scanned PDFs marked `OCR_REQUIRED`.

Search accepts `source_name`, `document_type`, `legal_status`, and
`issuing_agency` filters. The document library accepts the same source,
document-type, and agency filters, and returns the stored source name with each
document summary.

The web search view presents a deterministic, query-focused preview capped at
260 characters instead of rendering the full indexed passage. Full passage
text is available in the document view, while official source links remain the
preferred way to read the complete regulation.
Each result also shows the stored document title and article heading. The
snippet is not generated by an LLM: it selects the most query-relevant sentence
from the indexed passage to keep latency and inference cost predictable.

## Web workspace

The web client runs as a separate Next.js container and proxies
browser requests to the API. Start it with:

```powershell
docker compose up --build -d web
```

Open `http://localhost:3000`. The workspace includes search, cited Q&A,
document browsing, and article-level version comparison. The web container can
be rebuilt independently of the slower API image.

Selecting a document opens its indexed detail view, including stored versions,
article headings, passage text, and page ranges when available.
Each version also reports its latest processing status, error code when
available, and indexed chunk count. `OCR_REQUIRED` indicates that native
extraction and the local Tesseract fallback both failed or that OCR is disabled.
```
