# ADR 0001: Start with a modular monolith

## Context

TaxLens needs ingestion, legal data, retrieval, intelligence, and an API, but the initial corpus and traffic do not justify distributed services.

## Decision

Implement one Python application with explicit package boundaries. Run long processing through commands first. Once the synchronous/CLI path is proven, use Airflow as the required daily scheduler through an authenticated API job boundary; add a worker or queue only when measured workload requires it.

## Consequences

The project is simpler to run, test, and deploy locally. Module contracts must remain clean so a later worker or scheduler can call the same domain services without copying business logic.

## Revisit trigger

Processing blocks API requests, requires concurrent retries, or multiple
scheduled workflows require backfills and operational visibility. Because
TaxLens must check official sources daily, Airflow is a required scheduler for
the product workflow once the command path is proven; it calls the modular
domain functions rather than replacing them.
