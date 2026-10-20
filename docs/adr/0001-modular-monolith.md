# ADR 0001: Start with a modular monolith

## Context

TaxLens needs ingestion, document processing, retrieval, question answering, and an API.
The corpus (thousands of documents) and traffic (a few users) do not justify distributed
services.

## Decision

Build one Python package with explicit module boundaries (`ingestion`,
`document_processing`, `retrieval`, `intelligence`, `legal_data`, `storage`, `api`). Long
work runs as command-line scripts that call the same functions as the API. Airflow
schedules those scripts through an authenticated API job boundary
([ADR 0002](0002-background-jobs-in-the-api.md)) rather than containing its own logic.

## Consequences

The project is simple to run, test, and deploy. Module contracts must stay clean so a
separate worker could later call the same functions without copying business logic.

## Revisit trigger

Processing measurably slows user requests, or the corpus or traffic outgrows one API
replica.
