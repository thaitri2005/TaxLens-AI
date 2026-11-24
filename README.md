<p align="center"><img src="docs/assets/logo.svg" width="72" alt="TaxLens logo"></p>

# TaxLens AI

**Search Vietnamese tax law and get answers cited to the exact article.**

TaxLens collects official tax documents back to 1990 (2,986 documents, 144,279 passages),
splits them by article and clause, and answers only from those passages. Each answer cites the
document, article and clause, applies the law in force on the date asked about, and says so
when the documents do not answer the question.

**Live development site:**
[taxlens-dev-web…azurecontainerapps.io](https://taxlens-dev-web.wonderfulfield-8256aab7.eastasia.azurecontainerapps.io)
(sign-in required; the first question after 10 idle minutes takes about a minute)

| Ask | Search |
| --- | --- |
| <img src="docs/assets/ask.png" width="400" alt="Ask TaxLens: a cited answer to a VAT refund question"> | <img src="docs/assets/search.png" width="400" alt="Search: filters by source, kind and status, then matching passages with citations"> |

## Features

- **Cited answers** in the question's language, with verbatim excerpts and official links;
  facts not supported by their cited passage are removed.
- **The law of the right date**: ended documents are left out and tagged; those that may
  have ended are flagged and used last.
- **Refusals instead of guesses** when a question is out of scope or the evidence is missing.
- **Search** by number, title or content, filtered by source, kind and status; tolerates missing
  diacritics and OCR errors.
- **Measured**: a clause-labelled gold set, frozen corpus versions, an answer grader, and a
  record of every experiment.

## How it works

```mermaid
flowchart LR
    Doc[Official file] --> Text[Word/RTF text,<br/>PDF text, or OCR]
    Text --> Chunk[Split by article<br/>and clause]
    Chunk --> Index[(Keyword + vector index)]
    Question --> Search[Hybrid search over<br/>the law in force]
    Index --> Search
    Search --> Gate{Evidence?}
    Gate -->|yes| LLM[Language model]
    Gate -->|no| Refuse[Refuse]
    LLM --> Check[Check citations] --> Answer[Cited answer]
```

Keyword ranking and `multilingual-e5-small` vectors in PostgreSQL are fused by reciprocal rank
fusion; the five best passages become the evidence. Details: [retrieval.md](docs/retrieval.md),
[architecture.md](docs/architecture.md).

**Stack:** Next.js 15 and Auth.js · FastAPI and PostgreSQL (full-text + pgvector) · Hugging Face
Inference Providers · Tesseract OCR · Airflow · Azure Container Apps, Terraform, GitHub Actions.

## Results so far

On 30 scored gold cases (`corpus-v2.1`):

| Measure | Result |
| --- | --- |
| Essential provisions in the top 5 / 10 / 20 passages | 0.31 / 0.47 / 0.53 |
| Answers to 15 gold questions | 8 correct, 2 wrong, 5 refused |
| Warm answer time | about 5.5 s |

Details and known problems: [evaluation-status.md](docs/evaluation-status.md).

## Run locally

Requires Python 3.12 and Docker Desktop.

```powershell
Copy-Item .env.example .env          # set AUTH_INITIAL_ADMIN_PASSWORD, and HF_TOKEN for answers
docker compose up -d postgres api web
docker compose exec -T api alembic upgrade head
docker compose exec -T api python scripts/seed.py
```

Open <http://localhost:3000>. Building a corpus, checks, release and deploy:
[operations.md](docs/operations.md).

## Documentation

| Document | Contents |
| --- | --- |
| [evaluation-status.md](docs/evaluation-status.md) | **Start here:** what is live, results, known problems, to do |
| [retrieval-experiments.md](docs/retrieval-experiments.md) | Everything already tried; read before any run |
| [architecture.md](docs/architecture.md) | Components, data model, authentication, Azure |
| [retrieval.md](docs/retrieval.md) | Extraction, search, ended documents, answers |
| [pipeline.md](docs/pipeline.md) | Sources and Airflow DAGs |
| [operations.md](docs/operations.md) | Local development, corpus, release, troubleshooting |
| [changelog.md](docs/changelog.md) | Changes by working stint |
| [corpus-inclusion.md](docs/corpus-inclusion.md), [annotation-guideline.md](docs/annotation-guideline.md) | What enters the corpus; how gold cases are labelled |

## Limitations

A research tool, **not legal or tax advice**. Official letters (*công văn*) and provincial
documents are not collected, many sources are OCR'd scans, and accuracy is measured on few
cases. More in [evaluation-status.md](docs/evaluation-status.md).
