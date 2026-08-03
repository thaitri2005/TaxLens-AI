# TaxLens AI — Detailed Implementation Plan

**Document status:** Initial execution plan  
**Version:** 1.0  
**Related blueprint:** `projectstructure.txt`  
**Planning rule:** The blueprint describes the target system; this document describes the order in which to build it.

This plan is designed for implementation by one developer or multiple contributors working against stable module interfaces. It focuses on code structure, build order, technical dependencies, test coverage, and executable acceptance criteria.

---

## 1. Delivery Strategy

### 1.1 Product objective

Deliver a working regulatory-intelligence vertical slice that can:

1. load Vietnamese tax documents;
2. preserve source provenance and document versions;
3. extract article-aware evidence;
4. retrieve relevant legal passages;
5. answer questions with citations and uncertainty;
6. compare two document versions;
7. measure retrieval, citation, latency, and cost quality;
8. run locally before optional Azure deployment.

### 1.2 Implementation principles

- Build a modular monolith before splitting services.
- Make every processing step deterministic and rerunnable.
- Keep raw documents and provenance immutable.
- Use PostgreSQL and pgvector before adding another database.
- Use native extraction before paid OCR.
- Use an LLM for interpretation and drafting, not as the source of truth.
- Make citations first-class objects and validate them before responding.
- Test each layer with fixtures before connecting the next layer.
- Keep cloud services optional until the local vertical slice works.
- Record architectural decisions and update this plan after each milestone.

### 1.3 Delivery gates

| Gate | Required outcome | No-go condition |
|---|---|---|
| Gate A | Clean local startup | Cannot start from a clean checkout |
| Gate B | Searchable legal corpus | Documents cannot be reprocessed idempotently |
| Gate C | Evidence retrieval | Results lack article/page provenance |
| Gate D | Cited Q&A and comparison | Answers cannot refuse unsupported questions |
| Gate E | Measured quality | No reviewed evaluation set exists |
| Gate F | Cloud deployment | Deployment depends on manual undocumented steps |

Do not begin the next gate by hiding failures in the previous one.

---

## 2. Engineering Execution Rules

Every work package must have:

- a short design note before implementation;
- a defined input/output contract;
- unit tests for business rules;
- integration tests at its persistence or API boundary;
- sample data or fixtures;
- documentation of failure behavior;
- a review against the dependent package’s interface and tests.

---

## Repository Layout

The implementation should follow the structure already described in `projectstructure.txt`. The first milestone may simplify the physical layout, but the logical module boundaries must remain visible.

```text
taxlens-ai/
├── apps/
│   ├── api/                    # HTTP composition and route handlers
│   ├── worker/                 # optional asynchronous entry point
│   └── web/                    # Next.js interface
├── packages/
│   ├── shared/                 # settings, IDs, errors, events
│   ├── legal_data/             # documents, versions, relationships, taxonomy
│   ├── ingestion/              # source connectors and change detection
│   ├── document_processing/    # extraction, OCR, normalization, parsing
│   ├── retrieval/              # FTS, vectors, fusion, reranking, citations
│   ├── intelligence/           # Q&A, comparison, prompts, model adapters
│   ├── evaluation/             # datasets, metrics, reports
│   ├── notifications/          # later release
│   └── observability/          # logs, usage, tracing adapters
├── database/                   # migrations, seed data, queries
├── scripts/                    # repeatable developer/operator commands
├── tests/                      # cross-package and end-to-end tests
├── data/                       # local ignored artifacts and fixtures
├── docs/                       # decisions, operations, source policy
└── infra/                      # Terraform and later deployment manifests
```

### 3.1 Dependency direction

```text
shared
  ↓
legal_data ← ingestion ← document_processing
  ↓                         ↓
retrieval ← intelligence ← API
  ↓                         ↓
evaluation                web
```

Domain packages must not import FastAPI route modules. UI code must not call the database directly. The model adapter must be replaceable behind an interface.

---

## 3. Phase 0 — Technical Scope and Decisions

**Estimated effort:** 1–2 days  
**Dependencies:** none

### Work package 0.1 — Scope lock

Define the first supported categories, document types, supported languages, source policy, and demo workflows.

**Deliverables:**

- accepted scope statement;
- list of 30–75 seed documents or a smaller first fixture set;
- five initial questions and two comparison scenarios;
- out-of-scope list;
- legal/republication review notes for corpus sources.

**Acceptance criteria:** a contributor can tell whether a proposed feature belongs in the core MVP without a meeting.

### Work package 0.2 — Architecture decision records

Create short records for:

- modular monolith first;
- PostgreSQL plus pgvector;
- local object storage adapter plus Azure Blob adapter;
- CLI processing before Airflow;
- native extraction before OCR;
- deterministic diff before LLM summary;
- self-hosted embedding adapter with an optional future managed-provider adapter;
- citation and no-answer policy.

**Acceptance criteria:** each decision states context, decision, alternatives, consequences, and revisit trigger.

### Work package 0.3 — Definition of done

Document coding, testing, security, review, migration, and release requirements. Include a rule that no benchmark number may appear in project claims until generated by the evaluation runner.

---

## 4. Phase 1 — Repository and Local Foundation

**Estimated effort:** 2–4 days  
**Dependencies:** Phase 0

### Work package 1.1 — Python backend skeleton

Implement:

- `pyproject.toml`;
- Python version policy;
- Ruff, mypy, pytest configuration;
- typed settings with `.env.example`;
- FastAPI application factory;
- `/health` and `/ready` endpoints;
- structured error format;
- request ID middleware;
- application logging.

**Acceptance criteria:** the API starts locally, reports dependency readiness, and has a test for healthy and unhealthy states.

### Work package 1.2 — Database runtime

Implement:

- Docker Compose PostgreSQL with pgvector;
- SQLAlchemy or equivalent database access layer;
- Alembic configuration;
- connection pooling and transaction boundaries;
- migration command;
- test database configuration.

**Acceptance criteria:** a fresh database can be created and migrated from zero; tests do not depend on a developer’s personal database.

### Work package 1.3 — Local object storage

Define an object-storage interface with local and Azure implementations.

Required operations:

```text
put_bytes(key, content, content_type)
get_bytes(key)
exists(key)
delete(key)
get_metadata(key)
```

**Acceptance criteria:** processing code uses the interface, not filesystem paths or Azure SDK calls directly.

### Work package 1.4 — Developer workflow

Provide:

```text
docker compose up --build
make test
make lint
make migrate
make seed
```

If Make is not used on Windows, provide equivalent PowerShell commands in `README.md`.

**Acceptance criteria:** a new contributor can start the API and database using documented commands only.

### Work package 1.5 — Initial CI

Run on pull requests:

- format/lint;
- type check;
- unit tests;
- migration validation;
- frontend checks once the frontend exists.

Do not add deployment to CI until the local checks are reliable.

---

## 5. Phase 2 — Legal Data Foundation

**Estimated effort:** 3–5 days  
**Dependencies:** Phase 1

### Work package 2.1 — Taxonomy

Define controlled values for:

- tax category;
- document type;
- legal status;
- affected taxpayer group;
- business process;
- relationship type;
- processing status;
- confidence level.

Store taxonomy values as validated enums or reference tables. Do not allow arbitrary labels in the first release.

### Work package 2.2 — Core schema

Implement tables for:

```text
source_record
legal_document
document_version
legal_relationship
document_chunk
processing_job
```

Add UUID primary keys, timestamps, source URLs, raw and normalized hashes, status fields, and foreign-key constraints.

**Acceptance criteria:** the schema represents two versions of one document, an amendment relationship, and a consolidated document without duplicated identity records.

### Work package 2.3 — Provenance contract

Every derived record must be traceable to:

```text
source URI → raw artifact → extraction run → normalized text → chunk → embedding → answer citation
```

Implement provenance fields and a human-readable provenance response for the API.

### Work package 2.4 — Seed manifest

Create a manifest containing document number, title, type, source, dates, category, local artifact key, and review status. Keep restricted or copyrighted files out of Git unless redistribution is permitted.

**Acceptance criteria:** seed loading can be run twice without duplicate documents, versions, or artifacts.

---

## 6. Phase 3 — Ingestion and Artifact Management

**Estimated effort:** 4–7 days  
**Dependencies:** Work packages 1.3 and 2.2

### Work package 3.1 — Connector protocol

Implement the connector interface from the blueprint:

```python
list_documents(since) -> list[SourceDocument]
fetch_document(document) -> bytes
fetch_metadata(document) -> dict
```

First implementations:

1. seed-corpus connector;
2. one real source connector;
3. fake connector for tests.

The connector must implement timeout, retry, rate limiting, user-agent policy, and clear error reporting.

### Work package 3.2 — Discovery and download

Implement:

- discovery normalization;
- URL and document-number normalization;
- MIME and file-signature validation;
- checksum calculation;
- raw artifact storage;
- crawl attempt logging;
- retry classification.

### Work package 3.3 — Idempotent change detection

Support these outcomes:

```text
NEW_DOCUMENT
UNCHANGED
NEW_SOURCE_COPY
CONTENT_UPDATED
METADATA_UPDATED
RETRY_REQUIRED
FAILED
```

**Acceptance criteria:** running the same ingestion twice does not create duplicate legal records or duplicate artifacts.

### Work package 3.4 — Processing command

Create a command that accepts one document or a batch:

```text
python scripts/process_corpus.py --document-id ...
python scripts/process_corpus.py --pending
```

Persist status transitions and errors. A failed document must be retryable without restarting the entire corpus.

### Work package 3.5 — Airflow adapter, later in this phase

Only after the command path is stable, wrap discovery and processing functions in the DAGs described in `projectstructure.txt`. DAG tasks should call package functions rather than contain business logic.

---

## 7. Phase 4 — Document Processing

**Estimated effort:** 5–8 days  
**Dependencies:** Phase 3

### Work package 4.1 — Native extraction

Support text-readable PDF and HTML first. Preserve:

- page numbers;
- source format;
- extraction method;
- extraction warnings;
- character and page counts.

### Work package 4.2 — Quality scoring and OCR fallback

Calculate extraction quality using character count, alphabetic ratio, broken-character ratio, empty-page ratio, and expected page count. Invoke Azure Document Intelligence only when the score is below a documented threshold.

**Acceptance criteria:** tests prove that good PDFs do not call the OCR adapter and scanned fixtures do.

### Work package 4.3 — Normalization

Normalize encoding, whitespace, headers, footers, page breaks, and repeated source boilerplate without destroying legal numbering. Store both the normalized text and a processing report.

### Work package 4.4 — Metadata extraction

Use this order:

1. source metadata;
2. deterministic patterns;
3. validated LLM structured extraction for unresolved fields;
4. manual-review status for low-confidence records.

Required fields include number, title, type, agency, signing authority, issue date, effective date, language, status, categories, and source URL.

### Work package 4.5 — Legal structure parser

Parse chapters, sections, articles, clauses, and points. Preserve offsets and page ranges. Add fixtures for Vietnamese numbering and malformed documents.

### Work package 4.6 — Version and relationship resolution

Resolve explicit phrases and known metadata first. Store relationship confidence and resolution method. Never silently merge two documents because their titles look similar.

### Work package 4.7 — Article-aware chunking

Create article-level chunks, split long articles by clause, and use token fallback only when necessary. Every chunk must retain version, article, clause, heading, page range, legal status, and effective date.

---

## 8. Phase 5 — Retrieval Platform

**Estimated effort:** 4–7 days  
**Dependencies:** Phase 4

### Work package 5.1 — Keyword search

Implement PostgreSQL full-text search with Vietnamese-aware normalization as far as practical. Add exact boosts for document numbers, titles, article numbers, and headings.

### Work package 5.2 — Embeddings

Implement a self-hosted embedding adapter using `intfloat/multilingual-e5-small`, pinned to a specific Hugging Face revision and packaged into the FastAPI image during Docker build. Do not download model files at runtime.

Implement:

- `embed_passages()` and `embed_query()` methods with the required `passage: ` and `query: ` prefixes;
- CPU-only model loading once per application process;
- 512-token maximum input handling with truncation metrics;
- a `document_embeddings` table storing chunk ID, model ID, revision, vector dimension, content hash, vector, and timestamp;
- pgvector cosine-similarity search and a vector index chosen from measured corpus size;
- an idempotent `scripts/embed_corpus.py` command that skips unchanged chunk/model-revision pairs;
- Docker build steps that snapshot the model into the image and an offline-mode test proving requests do not require Hugging Face access.

The initial model is intentionally small and CPU-friendly. Treat embedding latency, container memory, image size, cold-start time, and retrieval metrics as acceptance criteria; upgrade to a larger or managed model only if the evaluation dataset justifies the cost.

### Work package 5.3 — Hybrid retrieval

Implement:

```text
query parsing → metadata filters → FTS + vector candidates
              → reciprocal-rank fusion → deduplication
```

Return a stable result schema with score components and provenance.

Start with reciprocal-rank fusion (RRF) of the existing full-text rank and pgvector cosine results. Return separate keyword, vector, and fused scores so tuning remains observable.

### Work package 5.4 — Reranking

Start without an external reranker. Add one only if evaluation shows a measurable ranking gap. Keep reranking behind an interface and record latency/cost.

### Work package 5.5 — Citation builder

Construct citations from stored metadata, never from model-generated text. A citation must identify document number, version/status, article or clause, page, and source link or artifact key.

**Acceptance criteria:** retrieval tests assert both ranking and citation completeness.

---

## 9. Phase 6 — Intelligence Workflows

**Estimated effort:** 5–8 days  
**Dependencies:** Phase 5

### Work package 6.1 — Model adapter

Define a provider-neutral interface for chat and structured output. Record model deployment, prompt version, token counts, latency, and estimated cost. Do not hard-code a model name. This interface is separate from the local embedding adapter.

### Work package 6.2 — Intent and query planning

Support these intents:

```text
DOCUMENT_LOOKUP
REGULATORY_QUESTION
CHANGE_SUMMARY
DOCUMENT_COMPARISON
IMPACT_ANALYSIS
UNSUPPORTED
```

Extract filters such as tax category, dates, document number, status, and affected entity. Validate structured output before retrieval.

### Work package 6.3 — Evidence sufficiency

Define rules for:

- no retrieved evidence;
- conflicting versions;
- historical versus current questions;
- insufficient article-level support;
- ambiguous user scope.

The system must ask for clarification or decline a conclusion when evidence is insufficient.

### Work package 6.4 — Cited Q&A

Generate a structured response containing:

```text
answer
confirmed_facts
interpretation
uncertainties
citations
review_actions
disclaimer
```

Validate that each factual claim is linked to retrieved evidence before returning the answer.

### Work package 6.5 — Comparison workflow

Implement deterministic structural diff first. Classify added, removed, modified, and unchanged articles. Use the LLM only to summarize the diff and explain practical impact, with citations to both versions.

### Work package 6.6 — Optional LangGraph integration

Introduce LangGraph only after the ordinary service workflow passes tests. Nodes should wrap existing functions; no node should bypass evidence or citation validation.

---

## 10. Phase 7 — API and Frontend

**Estimated effort:** 5–8 days  
**Dependencies:** Phases 2, 5, and 6

### Work package 7.1 — API routes

Implement and document:

```text
GET  /health
GET  /ready
GET  /documents
GET  /documents/{id}
GET  /documents/{id}/versions
GET  /search
POST /questions
POST /comparisons
GET  /conversations/{id}
GET  /admin/jobs
```

Use pagination, validation, consistent errors, request IDs, and bounded result sizes.

### Work package 7.2 — Authentication boundary

Use a local development identity first. Add password hashing, JWT rotation, and role checks before cloud exposure. Keep organization-scoped tables ready, but defer billing and plan enforcement.

### Work package 7.3 — Search and document UI

Build:

- search box and filters;
- result cards;
- document detail and metadata;
- version timeline;
- processing status;
- source/artifact links.

### Work package 7.4 — Q&A UI

Show answer, evidence status, citations, retrieved sources, uncertainty, and feedback. Make citations clickable and preserve the question/answer history.

### Work package 7.5 — Comparison UI

Show selected versions, article-level diff, added/removed/modified labels, source passages, and effective-date notes.

**Acceptance criteria:** a reviewer can complete the primary demo without using API tools.

---

## 11. Phase 8 — Evaluation and LLMOps

**Estimated effort:** 4–6 days initially, ongoing afterward  
**Dependencies:** Phases 5 and 6

### Work package 8.1 — Evaluation dataset

Start with 50 reviewed questions, growing toward 75–150. Include direct lookup, effective dates, amendment identification, comparisons, multi-document synthesis, applicability, unsupported questions, and adversarial wording.

Each item should record expected documents/articles, answerability, category, difficulty, and reference answer where feasible.

### Work package 8.2 — Retrieval metrics

Implement Recall@K, Precision@K, MRR, nDCG, empty-retrieval rate, and citation coverage.

### Work package 8.3 — Answer metrics

Track answer relevance, factual correctness, citation correctness, citation completeness, faithfulness, no-answer accuracy, latency, and estimated cost. Human review remains the source of truth for legal correctness.

### Work package 8.4 — Baselines and regression

Compare:

1. metadata plus keyword;
2. vector-only;
3. hybrid retrieval;
4. hybrid plus optional reranking.

Store configuration snapshots and fail CI or scheduled evaluation when a protected metric regresses beyond a documented tolerance.

### Work package 8.5 — MLflow, later

Log experiments to MLflow when multiple retrieval or prompt experiments need central comparison. Do not make MLflow a dependency of the core application.

---

## 12. Phase 9 — Security, Observability, and Operations

**Estimated effort:** 4–6 days  
**Dependencies:** Phases 1, 6, and 7

### Work package 9.1 — Security baseline

Implement:

- file type and size validation;
- safe HTML/text rendering;
- parameterized queries;
- secret management through environment variables locally;
- no secrets in Git;
- redacted logs;
- API rate limits;
- audit events for administrative operations;
- organization isolation before multi-user production use.

### Work package 9.2 — Application observability

Record structured events for API requests, processing jobs, retrieval stages, model calls, citation validation, errors, and cost. Include correlation IDs.

### Work package 9.3 — Operational dashboard

Track ingestion success, processing backlog, OCR rate, retrieval latency, empty retrievals, citation failures, token usage, and model errors. Start with logs and database queries; add Prometheus/Grafana or Azure Monitor later.

### Work package 9.4 — Failure recovery

Document retry and recovery for connector failures, OCR failures, model timeouts, invalid structured output, migration failures, and partial processing. Every failed job needs a visible reason and retry path.

---

## 13. Phase 10 — Azure Deployment

**Estimated effort:** 3–6 days  
**Dependencies:** Gates A–E

### Work package 10.1 — Terraform modules

Start with development resources:

- resource group;
- storage account/container;
- PostgreSQL Flexible Server;
- Container Registry;
- Container Apps or App Service;
- Key Vault;
- monitoring hooks.

Every resource must have tags, outputs, and a destroy/cleanup procedure.

### Work package 10.2 — Container images

Build reproducible API, worker, and frontend images only when the corresponding runtime exists. Use immutable Git SHA tags and a minimal base image.

### Work package 10.3 — Secrets and identity

Use managed identity or Key Vault references in Azure. Keep local `.env` support separate from production configuration.

### Work package 10.4 — Deployment workflow

Implement:

```text
pull request → checks
main merge → build/test/image
manual dev deploy → migration → smoke test
release tag → approval → production-like deployment
```

Never run destructive production changes automatically from a pull request.

### Work package 10.5 — Cloud smoke tests

Verify health, authentication, search, question answering, citations, Blob access, database migrations, and model connectivity after deployment.

### Work package 10.6 — AKS stretch

Add AKS, Helm, ingress, autoscaling, and Service Bus only after the lower-cost deployment is reproducible and the stretch objective is explicit.

---

## 14. Phase 11 — Post-MVP Modules

Implement these independently after the core release.

### Module A — Monitoring and alerts

Saved topics, topic matching, effective-date reminders, in-app alerts, email digests, and processing administration.

**Dependency:** stable ingestion events and user preferences.

### Module B — Version intelligence

Predecessor resolution, document timelines, relationship review, structured change reports, and comparison exports.

**Dependency:** reliable version and relationship data.

### Module C — Professional impact analysis

Company profiles, client profiles, affected-entity rules, review checklists, and saved reports.

**Dependency:** strong evidence policy and explicit separation between legal facts and business interpretation.

### Module D — Multi-tenant SaaS

Organizations, members, roles, quotas, audit logs, usage limits, and plan enforcement.

**Dependency:** authentication, authorization, usage events, and a real need for team isolation.

### Module E — Integrations and exports

PDF/Word reports, Teams, Slack, webhooks, and external identity.

**Dependency:** stable response and notification schemas.

---

## 15. Cross-Cutting Contracts

### 16.1 Document status contract

```text
DISCOVERED → DOWNLOADED → EXTRACTED → NORMALIZED → METADATA_VALIDATED
           → STRUCTURED → CHUNKED → EMBEDDED → READY
```

Any state may transition to `FAILED` with an error code and retry count. State transitions must be persisted atomically.

### 16.2 Retrieval result contract

```json
{
  "chunk_id": "...",
  "document_id": "...",
  "version_id": "...",
  "article": "...",
  "clause": "...",
  "page_start": 1,
  "page_end": 2,
  "text": "...",
  "keyword_score": 0.0,
  "vector_score": 0.0,
  "combined_score": 0.0,
  "source_uri": "..."
}
```

### 16.3 Answer contract

```json
{
  "answer": "...",
  "intent": "REGULATORY_QUESTION",
  "evidence_status": "SUPPORTED",
  "confirmed_facts": [],
  "uncertainties": [],
  "citations": [],
  "review_actions": [],
  "model_metadata": {}
}
```

### 16.4 Event contract

Events should include event type, entity ID, correlation ID, timestamp, actor, status, duration, and error details where relevant. This supports Airflow, queues, notifications, and observability without redesigning the domain later.

---

## 16. Testing Plan

### Unit tests

- checksum and idempotency;
- date and document-number parsing;
- normalization;
- legal section parsing;
- relationship classification;
- chunk boundaries;
- query filter extraction;
- rank fusion;
- citation validation;
- deterministic comparison;
- cost calculation.

### Integration tests

- migrations from empty database;
- seed loading twice;
- object storage round trip;
- processing a text-readable PDF;
- OCR fallback with a scanned fixture;
- FTS and vector retrieval;
- API route behavior;
- authorization boundaries;
- model adapter timeout and malformed output.

### End-to-end tests

1. seed a document;
2. process it;
3. search for an article;
4. ask a supported question;
5. verify citations;
6. ask an unsupported question;
7. compare two versions;
8. inspect processing and usage records.

### Release test gates

Every release must pass formatting, type checks, unit tests, integration tests, migration checks, security checks, and a smoke evaluation. Cloud releases must additionally pass deployment smoke tests.

---

## 17. Cost Controls and Resource Policy

### Local development

The default local profile should contain only PostgreSQL/pgvector, API, frontend, and required local storage. Redis, Airflow, MLflow, monitoring, and mail services belong to optional profiles.

### Model usage

- use deterministic parsing before LLM extraction;
- cache embeddings by normalized-text hash and model name;
- package the pinned embedding model into the image and monitor image size, memory, CPU, and cold starts;
- cache safe metadata and summary results;
- cap document context and output tokens;
- use a small model for classification and a stronger model only where evaluation shows value;
- log estimated cost per job and query.

### Azure lifecycle

- tag all resources with environment, project, and expiry;
- use a dev resource group that can be destroyed and recreated;
- configure budgets and alerts;
- avoid high-availability SKUs for portfolio development;
- stop or delete nonessential dev resources outside demonstrations;
- do not keep AKS running merely to display Kubernetes on a résumé.

### Effectiveness metrics

Track quality beside cost:

```text
cost per processed document
cost per answered query
retrieval Recall@K
citation correctness
no-answer accuracy
median and P95 latency
processing failure rate
OCR percentage
```

---

## 18. Suggested Milestone Schedule

These estimates assume one developer working part-time to full-time and a prepared seed corpus. Data cleanup and source-site changes can extend them.

| Milestone | Scope | Target |
|---|---|---|
| M0 | scope, source policy, decisions | end of week 1 |
| M1 | local foundation and schema | end of week 2 |
| M2 | ingestion and processing | end of week 3 |
| M3 | self-hosted embeddings, hybrid retrieval, and citations | end of week 4 |
| M4 | Q&A, comparison, API, UI | end of week 6 |
| M5 | evaluation and hardening | end of week 7 |
| M6 | low-cost Azure deployment | end of week 8 |
| M7 | one post-MVP differentiator | after core release |

Do not treat dates as promises. Treat the acceptance criteria as the schedule authority.

---

## 19. Technical Change Management

When the blueprint or implementation changes, update this file in the same change set.

### Change record format

```text
Date:
Change:
Reason:
Affected phase/module:
Migration or compatibility impact:
Cost impact:
```

### Change review questions

1. Does this improve the primary regulatory workflow?
2. Does it introduce a new always-on service?
3. Can it be implemented behind an existing interface?
4. What test proves it is useful?
5. What is the rollback or removal path?
6. Does it alter legal provenance or citation behavior?
7. Does it change security, privacy, or source licensing assumptions?

### 2026-08-04 — Self-hosted embedding default

```text
Change: Replace Azure OpenAI embeddings with a pinned intfloat/multilingual-e5-small model in the FastAPI image.
Reason: Avoid per-vector API cost and keep Vietnamese/English retrieval available without external inference calls.
Affected phase/module: Phase 5 embeddings and hybrid retrieval; Docker image; pgvector schema.
Migration or compatibility impact: Add a versioned embedding table and re-embed all chunks when model ID or revision changes.
Cost impact: Higher image size, CPU/memory use, and cold-start cost; no per-vector provider charge.
```

### Current assumptions to revisit

- the seed corpus is legally usable for the intended demo;
- one source connector is sufficient for the first release;
- PostgreSQL remains sufficient for the initial corpus size;
- article parsing quality is adequate for the selected document types;
- the pinned `multilingual-e5-small` model revision remains available under its MIT license and meets Vietnamese/English retrieval quality targets;
- local Docker Compose remains the fastest contributor workflow.

---

## 20. First Ten Implementation Tasks

These are the recommended first tickets:

1. Create the package and application skeleton.
2. Add typed settings and `.env.example`.
3. Add Docker Compose PostgreSQL with pgvector.
4. Add FastAPI factory, health, and readiness endpoints.
5. Add Alembic and the first migration.
6. Define document, version, relationship, chunk, and processing-job models.
7. Add local object-storage adapter and seed manifest.
8. Implement seed loading with checksum-based idempotency.
9. Add native PDF extraction and normalized artifact persistence.
10. Add article-aware chunks and a document-detail API.

After task 10, stop and verify the first vertical data slice before adding embeddings, agents, Airflow, or Azure.

---

## 21. Completion Checklist

The core MVP is complete when:

- a clean checkout starts locally;
- seed data loads repeatedly without duplicates;
- source artifacts and provenance are inspectable;
- text extraction and article parsing have fixtures;
- PostgreSQL FTS and pgvector retrieval return ranked chunks;
- Q&A answers contain validated citations;
- unsupported questions are handled safely;
- two versions can be compared;
- the UI supports search, Q&A, and comparison;
- evaluation reports show quality, latency, and cost;
- tests and documentation pass in CI.

The portfolio deployment is complete only when the same workflows run in Azure through reproducible infrastructure and smoke-tested deployment steps.
