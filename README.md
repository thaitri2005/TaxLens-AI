# TaxLens AI

**Cloud-native regulatory intelligence for Vietnamese tax professionals.**

TaxLens continuously discovers official Vietnamese tax documents, extracts and
indexes their contents, retrieves relevant provisions, and answers questions
with article-level citations that link back to the government source.

This is a portfolio project focused on practical AI platform engineering—not a
generic PDF chatbot. It demonstrates how to build, evaluate, secure, deploy,
and operate an evidence-first RAG system under a constrained budget.

## Live demo

The development deployment is available at:

**Web application:**
`https://taxlens-dev-web.wonderfulfield-8256aab7.eastasia.azurecontainerapps.io`

The application includes authentication, hybrid regulation search, cited Q&A,
document browsing, and document comparison. The Airflow UI is deployed
separately and remains protected/paused unless a scheduled ingestion run is
intentionally enabled.

## Why this project matters

Tax professionals need more than a keyword search box. They need to know:

- Which official document contains the applicable rule?
- Which article and page support the answer?
- Is the document current, superseded, or amended?
- What changed between two versions?
- What should be reviewed next?

TaxLens addresses those needs with source discovery, versioned legal metadata,
hybrid retrieval, grounded generation, citation validation, and scheduled
ingestion.

## Architecture: from official source to defensible answer

The central design is a controlled evidence pipeline, not a chatbot bolted onto
a PDF folder:

```mermaid
flowchart LR
    Source[Official government portals]
    Discover[Discover and deduplicate sources]
    Process[Extract text and legal structure]
    Store[(PostgreSQL metadata<br/>+ Blob artifacts)]
    Index[Chunk, embed, and index]
    Search[Hybrid retrieval]
    Evidence{Evidence gate}
    Answer[Grounded answer<br/>with article/page citations]
    Review[Human review and evaluation]

    Source --> Discover --> Process --> Store --> Index --> Search --> Evidence
    Evidence -->|sufficient and consistent| Answer
    Evidence -->|missing, ambiguous, or conflicting| Safe[Safe fallback:<br/>abstain or request review]
    Answer --> Review
    Safe --> Review
    Review -. improves labels and source coverage .-> Discover

    classDef boundary fill:#eef2ff,stroke:#6366f1,color:#111827;
    classDef gate fill:#fff7ed,stroke:#ea580c,color:#111827;
    class Source,Discover,Process,Store,Index,Search,Answer,Review boundary;
    class Evidence,Safe gate;
```

The beauty of TaxLens is the boundary between retrieval and generation. The
language model is never the authority: official documents are collected and
versioned first, retrieval finds inspectable passages, and an evidence gate can
stop the answer before inference when the support is absent or contradictory.
That makes the system safer, easier to evaluate, and easier to debug than a
single opaque `retrieve → prompt → answer` chain.

### Runtime request path

The public web application and private API have different responsibilities. The
browser never receives database credentials, and Airflow never writes directly
to application tables.

```mermaid
flowchart TB
    User[Authenticated user] --> Web[Next.js web app]
    Web --> Proxy[Next.js API proxy<br/>adds signed identity headers]
    Proxy --> API[Private FastAPI API]

    subgraph Q[LangGraph-controlled Q&A]
        Plan[Plan query and intent]
        Retrieve[Retrieve hybrid evidence]
        Assess[Assess legal status<br/>and article/page support]
        Route{Enough evidence?}
        Generate[Call provider through<br/>LangChain adapter]
        Validate[Parse structured output<br/>and validate citations]
        Fallback[Return unsupported/<br/>insufficient-evidence response]
        Plan --> Retrieve --> Assess --> Route
        Route -->|yes| Generate --> Validate
        Route -->|no| Fallback
    end

    API --> Plan
    Validate --> Response[Cited response]
    Fallback --> Response
    Response --> Web

    Retrieve --> DB[(PostgreSQL FTS<br/>+ pgvector)]
    Generate --> Model[Configurable chat provider]
```

LangGraph is deliberately used as an orchestration and policy layer. Its value
is the explicit state transition—plan, retrieve, assess, route—not autonomous
tool wandering. LangChain stays at the model integration boundary, so changing
the chat provider does not rewrite legal metadata, retrieval, or citation logic.

### Ingestion, indexing, and evaluation loop

The daily workflow is also part of the product architecture. It turns new
government publications into measurable, searchable knowledge while keeping
long-running work outside the user request path.

```mermaid
flowchart LR
    Airflow[Airflow DAG]
    Boundary[Authenticated internal API jobs]
    Discover[Discover official sources]
    Process[Process bounded batches<br/>native extraction → OCR fallback]
    Embed[Embed pending chunks]
    Evaluate[Evaluate retrieval<br/>and persist report]
    Corpus[(Versioned corpus)]
    Report[(Immutable evaluation reports)]
    MLflow[(Optional MLflow runs)]

    Airflow --> Boundary
    Boundary --> Discover --> Process --> Embed --> Evaluate
    Discover --> Corpus
    Process --> Corpus
    Embed --> Corpus
    Evaluate --> Report
    Evaluate -. optional tracking .-> MLflow
    Report -. coverage and ranking findings .-> Discover
```

Airflow is an orchestrator, not a second application backend. It calls
allowlisted internal endpoints; the API executes the same idempotent scripts
used locally. Processing is bounded because cloud ingress has time limits, and
evaluation records corpus coverage separately from ranking quality so a missing
document cannot masquerade as a bad retriever.

### Why the boundaries matter

| Boundary | Responsibility | Why it is valuable |
| --- | --- | --- |
| Ingestion → legal data | Discover official sources and preserve document/version identity | The corpus remains traceable and refreshable |
| Processing → retrieval | Extract, OCR, structure, chunk, and embed | Search operates on inspectable passages, not raw PDFs |
| Retrieval → generation | Assess consistency and structural support | The model cannot invent evidence that retrieval did not provide |
| Web → API | Proxy authenticated requests to a private service | Credentials and database access stay server-side |
| Airflow → API jobs | Orchestrate bounded, idempotent work | Scheduling is replaceable without duplicating domain logic |
| Evaluation → operations | Persist metrics, coverage, fingerprints, and history | A score can be reproduced and diagnosed |

## Engineering highlights

- **Hybrid legal retrieval:** PostgreSQL full-text search, pgvector semantic
  search, metadata filters, and lightweight score blending.
- **Grounded Q&A:** LangGraph controls retrieval, evidence validation,
  generation, citation validation, and safe fallback behavior.
- **Replaceable providers:** LangChain is used at the adapter boundary;
  Hugging Face model and routing policy are configuration-driven.
- **Vietnamese document processing:** native PDF extraction runs first, with
  Vietnamese/English Tesseract OCR for image-only or unusable PDFs.
- **Scheduled ingestion:** Airflow runs discovery, processing, OCR, embedding,
  and retrieval evaluation as idempotent tasks.
- **LLMOps workflow:** MLflow tracks evaluation runs and deterministic
  RAG-style metrics measure retrieval and answer behavior.
- **Security:** Auth.js credentials login, Argon2id password hashing,
  admin/user roles, private FastAPI ingress, Key Vault secrets, managed
  identity, and rate limiting for inference-backed Q&A.
- **Cloud delivery:** Terraform-managed Azure resources, remote Blob state,
  GitHub OIDC, immutable image tags, protected plans, and human-approved apply.

## Technology stack

| Area | Technology |
| --- | --- |
| Frontend | Next.js, TypeScript, Auth.js |
| API | FastAPI, Python 3.12, SQLAlchemy, Alembic |
| Retrieval | PostgreSQL full-text search, pgvector, reranking boundary |
| Embeddings | `intfloat/multilingual-e5-small`, CPU inference |
| Chat inference | Hugging Face Inference Providers, configurable routing |
| LLM workflow | LangGraph, LangChain adapter |
| Evaluation | MLflow, RAGAS-style deterministic metrics |
| Ingestion | Apache Airflow, idempotent API jobs |
| OCR | Tesseract with `vie` and `eng` language data |
| Cloud | Azure Container Apps, PostgreSQL Flexible Server, Blob Storage, Key Vault, ACR |
| Infrastructure | Terraform, GitHub Actions, Azure OIDC |

## Run locally

Prerequisites: Python 3.12 and Docker Desktop with Compose.

```powershell
Copy-Item .env.example .env
docker compose up -d postgres api web
docker compose exec -T api alembic upgrade head
docker compose exec -T api python scripts/seed.py
```

Open:

| Service | URL |
| --- | --- |
| Web app | `http://localhost:3000` |
| API docs | `http://localhost:8000/docs` |
| Airflow | `http://localhost:8080` |
| MLflow | `http://localhost:5000` |

Authentication is enabled locally. Configure the development values described
in `docs/authentication.md`, then sign in at `http://localhost:3000/login`.

Start optional LLMOps services when needed:

```powershell
docker compose --profile airflow --profile llmops up -d
```

The daily DAG is intentionally paused by default. Unpause and trigger
`tax_regulation_discovery_daily` only when you want to run discovery,
processing/OCR, embedding, and evaluation.

## Development checks

Run the same checks used by CI before pushing:

```powershell
python -m ruff check src tests scripts
python -m mypy src
python -m pytest
```

The current test suite covers authentication, protected routes, role-based
authorization, retrieval, citations, ingestion, document processing, and API
contracts.

## Deployment workflow

Azure deployment is intentionally controlled rather than automatic:

1. `release-images.yml` builds and publishes API, web, and Airflow images under
   an immutable commit-SHA tag.
2. `deploy.yml` generates a Terraform plan using the remote Azure Blob state.
3. A human reviews the plan.
4. The protected deployment environment applies the reviewed plan.

Production secrets remain in GitHub Actions secrets and Azure Key Vault. Azure
authentication uses GitHub OIDC rather than stored cloud passwords.

See:

- `docs/local-development.md` — local API, ingestion, and processing workflow
- `docs/authentication.md` — local authentication setup and security contract
- `docs/llmops-local.md` — LangGraph, MLflow, and evaluation workflow
- `docs/airflow-local.md` — local Airflow profile and DAG operations
- `docs/deployment.md` — Azure topology, smoke checks, and operations
- `docs/ci-cd.md` — GitHub Actions, OIDC, remote state, and approvals
- `IMPLEMENTATION_PLAN.md` — detailed development blueprint and milestone status
- `projectstructure.txt` — full system structure and design rationale

## Cost-conscious design

- The small multilingual embedding model is baked into the API image and runs
  on CPU, avoiding a managed embedding endpoint for every chunk.
- Native extraction runs before Tesseract, so OCR is used only when necessary.
- Hugging Face routing is configurable and defaults to the cheapest policy.
- PostgreSQL and pgvector consolidate relational, metadata, full-text, and
  vector storage into one managed database.
- Airflow and MLflow are separated from the request path and can be stopped or
  scaled down during development.
- Azure resources use small development SKUs and immutable image revisions.

## Portfolio scope and limitations

TaxLens is a working development deployment and resume project, not legal or
tax advice. The initial corpus is intentionally small and source coverage is
still curated. OCR quality varies with scanned document quality, and the
development deployment prioritizes a demonstrable architecture over production
scale.

## Screenshots

### Search workspace

![TaxLens search workspace](docs/assets/pic1.png)

![TaxLens search results](docs/assets/pic2.png)

### Ask TaxLens

![Ask TaxLens cited response](docs/assets/pic3.png)
